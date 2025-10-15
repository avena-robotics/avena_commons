"""GPU-accelerated PepperCamera Connector and Worker for high-performance fragment processing.

Based on the working Orbec implementation but with GPU batch processing for:
- Frame fragmentation on GPU (zero-copy slicing)
- Batch processing of all fragments simultaneously
- Minimized CPU-GPU transfers

Provides significant performance improvements over CPU version while maintaining
compatibility with existing architecture.
"""

import asyncio
import base64
import os
import traceback
from typing import Any, Dict, Optional

import cv2
import numpy as np
from pyorbbecsdk import (
    AlignFilter,
    Config,
    Context,
    Device,
    OBAlignMode,
    OBFormat,
    OBPermissionType,
    OBPropertyID,
    OBSensorType,
    OBStreamType,
    Pipeline,
    SpatialAdvancedFilter,
    TemporalFilter,
)

from avena_commons.camera.driver.general import (
    CameraState,
    GeneralCameraConnector,
    GeneralCameraWorker,
)
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.gpu_utils import GPUBatchProcessor, check_gpu_available
from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
    debug,
    error,
    info,
)


class PepperCameraGPUWorker(GeneralCameraWorker):
    """GPU-accelerated Pepper Camera Worker with batch fragment processing.

    Features:
    - GPU-based frame fragmentation (zero-copy slicing)
    - Batch processing of all fragments
    - Minimized CPU-GPU data transfers
    - Automatic fallback to CPU if GPU unavailable
    """

    def __init__(self, camera_ip: str, message_logger: Optional[MessageLogger] = None):
        """Initialize PepperCamera GPU worker.

        Args:
            camera_ip (str): IP address of the Orbec camera
            message_logger (Optional[MessageLogger]): Logger for messages
        """
        self.__camera_ip = camera_ip
        self._message_logger = None  # Will be set in worker process
        self.device_name = f"PepperCameraGPU_{camera_ip}"
        super().__init__(message_logger=None)

        # Camera filters (from Orbec implementation)
        self.align_filter = None
        self.spatial_filter = None
        self.temporal_filter = None
        self.frame_number = 0

        # Pepper-specific additions
        self.pipeline_config = None  # For fragment configuration
        self.last_fragments = None  # Store serialized fragments

        # GPU processor
        self.gpu_processor = None
        self.gpu_enabled = False

        # Performance metrics tracking
        self.performance_metrics = {
            "frame_grab_times": [],
            "gpu_upload_times": [],
            "fragmentation_times": [],
            "serialization_times": [],
            "total_processing_times": [],
        }

    def set_int_property(self, device: Device, property_id: OBPropertyID, value: int):
        """Set integer device property."""
        try:
            device.set_int_property(property_id, value)
            debug(f"Set property {property_id} to {value}", self._message_logger)
        except Exception as e:
            error(f"Error setting property {property_id}: {e}", self._message_logger)
            raise e

    def set_bool_property(self, device: Device, property_id: OBPropertyID, value: bool):
        """Set boolean device property."""
        try:
            device.set_bool_property(property_id, value)
            debug(f"Set property {property_id} to {value}", self._message_logger)
        except Exception as e:
            error(f"Error setting property {property_id}: {e}", self._message_logger)
            raise e

    async def init(self, camera_settings: dict):
        """Initialize camera connection and GPU processor."""
        try:
            self.state = CameraState.INITIALIZING
            debug(f"{self.device_name} - Initializing GPU camera", self._message_logger)

            # Store pipeline configuration for fragmentation
            self.pipeline_config = camera_settings.get("camera_pipeline", {})
            debug(f"Pipeline config: {self.pipeline_config}", self._message_logger)

            # Initialize GPU processor
            gpu_config = camera_settings.get("gpu_acceleration", {})
            gpu_enabled = gpu_config.get("enabled", True)
            
            if gpu_enabled:
                # IMPORTANT: Use init_device=True since we're in worker process (after fork)
                # This safely initializes CUDA in the worker process, not the parent
                gpu_available, gpu_info = check_gpu_available(init_device=True)
                if gpu_available:
                    self.gpu_processor = GPUBatchProcessor(
                        num_streams=gpu_config.get("num_streams", 4),
                        use_cupy=gpu_config.get("use_cupy", True)
                    )
                    self.gpu_enabled = True
                    info(f"GPU acceleration enabled in worker: {gpu_info}", self._message_logger)
                else:
                    info(f"GPU not available: {gpu_info}, will use CPU", self._message_logger)
                    self.gpu_enabled = False
            else:
                info("GPU acceleration disabled by configuration", self._message_logger)
                self.gpu_enabled = False

            # Rest of camera initialization (same as CPU version)
            color_settings = camera_settings.get("color", {})
            depth_settings = camera_settings.get("depth", {})

            # Create camera context and device
            ctx = Context()
            try:
                dev = ctx.create_net_device(self.__camera_ip, 8090)
            except Exception as e:
                error(
                    f"Error opening camera at {self.__camera_ip}: {e}",
                    self._message_logger,
                )
                raise e

            # Disparity Settings (same as CPU version)
            try:
                disparity_settings = camera_settings.get("disparity", {})
                if disparity_settings:
                    disparity_pid = OBPropertyID.OB_STRUCT_DISPARITY_RANGE_MODE
                    if not dev.is_property_supported(
                        disparity_pid, OBPermissionType.PERMISSION_READ_WRITE
                    ):
                        error(
                            f"Disparity range mode change not supported. Check firmware version.",
                            self._message_logger,
                        )
                    else:
                        desired_mode_name = disparity_settings.get("range_mode")
                        if desired_mode_name:
                            current_mode = dev.get_disparity_range_mode()
                            debug(
                                f"Current disparity range mode: {current_mode.name}",
                                self._message_logger,
                            )

                            available_modes = dev.get_disparity_range_mode_list()
                            is_mode_set = False
                            available_mode_names = []
                            for i in range(available_modes.get_count()):
                                mode = (
                                    available_modes.get_disparity_range_mode_by_index(i)
                                )
                                available_mode_names.append(mode.name)
                                if mode.name == desired_mode_name:
                                    dev.set_disparity_range_mode(mode.name)
                                    debug(
                                        f"Set disparity range mode to {mode.name}",
                                        self._message_logger,
                                    )
                                    is_mode_set = True
                                    break

                            if not is_mode_set:
                                error(
                                    f"Requested disparity range mode '{desired_mode_name}' not found. Available: {available_mode_names}. Using current: {current_mode.name}",
                                    self._message_logger,
                                )

                offset_pid = OBPropertyID.OB_STRUCT_DISPARITY_SEARCH_OFFSET
                if not dev.is_property_supported(
                    offset_pid, OBPermissionType.PERMISSION_READ_WRITE
                ):
                    debug(
                        f"Disparity search offset not supported",
                        self._message_logger,
                    )
                else:
                    disparity_offset = disparity_settings.get("search_offset")
                    if disparity_offset and disparity_offset > 0:
                        dev.set_int_property(offset_pid, disparity_offset)
                        debug(
                            f"Set disparity search offset to {disparity_offset}",
                            self._message_logger,
                        )
            except AttributeError as e:
                error(
                    f"pyorbbecsdk version doesn't support disparity mode change. Required >= 2.2.x. Skipping. Error: {e}",
                    self._message_logger,
                )

            self.camera_pipeline = Pipeline(dev)
            self.camera_config = Config()

            # Configure camera properties
            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_COLOR_EXPOSURE_INT,
                color_settings.get("exposure", 500),
            )
            self.set_int_property(
                dev, OBPropertyID.OB_PROP_COLOR_GAIN_INT, color_settings.get("gain", 10)
            )
            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_COLOR_WHITE_BALANCE_INT,
                color_settings.get("white_balance", 4000),
            )

            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_DEPTH_EXPOSURE_INT,
                depth_settings.get("exposure", 500),
            )
            self.set_int_property(
                dev, OBPropertyID.OB_PROP_DEPTH_GAIN_INT, depth_settings.get("gain", 10)
            )
            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_LASER_POWER_LEVEL_CONTROL_INT,
                depth_settings.get("laser_power", 5),
            )

            self.set_bool_property(
                dev,
                OBPropertyID.OB_PROP_DISPARITY_TO_DEPTH_BOOL,
                camera_settings.get("disparity_to_depth", True),
            )

            # Configure stream profiles
            color_profile_list = self.camera_pipeline.get_stream_profile_list(
                OBSensorType.COLOR_SENSOR
            )

            match color_settings.get("format", "BGR"):
                case "BGR":
                    color_format = OBFormat.BGR
                case "RGB":
                    color_format = OBFormat.RGB
                case "MJPG":
                    color_format = OBFormat.MJPG
                case _:
                    error(
                        f"Unknown color format: {color_settings.get('format', 'BGR')} - using BGR",
                        self._message_logger,
                    )
                    color_format = OBFormat.BGR

            width = color_settings.get("width", 1280)
            height = color_settings.get("height", 800)
            fps = color_settings.get("fps", 30)

            color_profile = color_profile_list.get_video_stream_profile(
                width, height, color_format, fps
            )
            if not color_profile:
                error(
                    f"No matching color profile for {width}x{height}@{fps} {color_format}",
                    self._message_logger,
                )
                self.state = CameraState.ERROR
                raise ValueError("Color profile configuration error")

            debug(
                f"Set color profile for {width}x{height}@{fps} {color_format}",
                self._message_logger,
            )

            # Alignment logic
            match camera_settings.get("align", None):
                case "d2c":
                    hw_d2c_profile_list = (
                        self.camera_pipeline.get_d2c_depth_profile_list(
                            color_profile, OBAlignMode.HW_MODE
                        )
                    )
                    if not hw_d2c_profile_list or len(hw_d2c_profile_list) == 0:
                        error(
                            f"Requested profile {width}x{height}@{fps} {color_format} doesn't support hardware alignment. Switching to software.",
                            self._message_logger,
                        )
                        sw_d2c_profile_list = (
                            self.camera_pipeline.get_d2c_depth_profile_list(
                                color_profile, OBAlignMode.SW_MODE
                            )
                        )
                        depth_profile = sw_d2c_profile_list[0]
                        self.align_filter = AlignFilter(
                            align_to_stream=OBStreamType.COLOR_STREAM
                        )
                    else:
                        depth_profile = hw_d2c_profile_list[0]
                    debug(
                        f"Enabled alignment for depth stream: {depth_profile}",
                        self._message_logger,
                    )
                case "c2d":
                    depth_profile_list = self.camera_pipeline.get_stream_profile_list(
                        OBSensorType.DEPTH_SENSOR
                    )
                    depth_profile = (
                        depth_profile_list.get_default_video_stream_profile()
                    )
                case _:
                    depth_profile_list = self.camera_pipeline.get_stream_profile_list(
                        OBSensorType.DEPTH_SENSOR
                    )
                    depth_profile = (
                        depth_profile_list.get_default_video_stream_profile()
                    )

            self.camera_config.enable_stream(depth_profile)
            debug(
                f"Enabled depth stream: {depth_profile.get_width()}x{depth_profile.get_height()}@{depth_profile.get_fps()} {depth_profile.get_format()}",
                self._message_logger,
            )
            self.camera_config.enable_stream(color_profile)
            debug(
                f"Enabled color stream: {color_profile.get_width()}x{color_profile.get_height()}@{color_profile.get_fps()} {color_profile.get_format()}",
                self._message_logger,
            )

            # Setup filters
            filter_settings = camera_settings.get("filters", {})
            if filter_settings.get("spatial", False):
                self.spatial_filter = SpatialAdvancedFilter()
                debug("Spatial filter enabled", self._message_logger)
            if filter_settings.get("temporal", False):
                self.temporal_filter = TemporalFilter()
                debug("Temporal filter enabled", self._message_logger)

            info("PepperCameraGPU configuration completed", self._message_logger)
            self.state = CameraState.INITIALIZED
            return True

        except Exception as e:
            error(f"{self.device_name} - Init failed: {e}", self._message_logger)
            self.state = CameraState.ERROR
            return False

    async def start(self):
        """Start camera pipeline."""
        try:
            debug(f"{self.device_name} - Starting camera", self._message_logger)

            if self.camera_pipeline is None:
                error("Pipeline not initialized", self._message_logger)
                raise ValueError("Pipeline not initialized")

            if self.camera_config is None:
                error("Config not initialized", self._message_logger)
                raise ValueError("Config not initialized")

            self.camera_pipeline.start(self.camera_config)
            return True

        except Exception as e:
            error(f"{self.device_name} - Starting failed: {e}", self._message_logger)
            return False

    async def stop(self):
        """Stop camera pipeline and cleanup GPU resources."""
        try:
            debug(f"{self.device_name} - Stopping camera", self._message_logger)
            self.camera_pipeline.stop()
            
            # Cleanup GPU resources
            if self.gpu_processor:
                self.gpu_processor.cleanup()
            
            return True
        except Exception as e:
            error(f"{self.device_name} - Stopping failed: {e}", self._message_logger)
            return False

    async def grab_frames_from_camera(self):
        """Grab and process frames from camera (same as CPU version)."""
        with Catchtime() as grab_timer:
            try:
                frames = self.camera_pipeline.wait_for_frames(3)

                if frames is None:
                    return None

                # Get frames from original FrameSet BEFORE filters
                frame_color = frames.get_color_frame()
                frame_depth = frames.get_depth_frame()

                if frame_color is None or frame_depth is None:
                    debug("Missing one of the frames. Skip...", self._message_logger)
                    return None

                self.frame_number += 1

                # Apply filters on copy
                if self.align_filter:
                    aligned_frames = self.align_filter.process(frames)
                    aligned_frames = aligned_frames.as_frame_set()
                    frame_depth = aligned_frames.get_depth_frame()
                    debug("Alignment filter applied", self._message_logger)

                if self.spatial_filter and frame_depth:
                    frame_depth = self.spatial_filter.process(frame_depth)
                    debug("Spatial filter applied", self._message_logger)

                if self.temporal_filter and frame_depth:
                    frame_depth = self.temporal_filter.process(frame_depth)
                    debug("Temporal filter applied", self._message_logger)

                if frame_color is None or frame_depth is None:
                    debug(
                        "One of the frames is None after filters", self._message_logger
                    )
                    return None

                # Process color frame
                color_image = None
                if frame_color.get_format() == OBFormat.MJPG:
                    debug(
                        f"Decoding MJPG color frame {frame_color.get_width()}x{frame_color.get_height()}",
                        self._message_logger,
                    )

                    color_data = frame_color.get_data()
                    color_image = cv2.imdecode(
                        np.frombuffer(color_data, np.uint8), cv2.IMREAD_COLOR
                    )

                    if color_image is None:
                        error(f"Error decoding MJPG color frame", self._message_logger)
                        return None
                else:
                    color_data = frame_color.get_data()
                    color_image = np.frombuffer(color_data, dtype=np.uint8).reshape((
                        frame_color.get_height(),
                        frame_color.get_width(),
                        3,
                    ))

                    if frame_color.get_format() == OBFormat.RGB:
                        color_image = cv2.cvtColor(color_image, cv2.COLOR_RGB2BGR)

                # Process depth frame
                depth_data = frame_depth.get_data()

                try:
                    depth_image = np.frombuffer(depth_data, dtype=np.uint16).reshape((
                        frame_depth.get_height(),
                        frame_depth.get_width(),
                    ))

                    debug(
                        f"Successfully created depth frame {frame_depth.get_width()}x{frame_depth.get_height()}",
                        self._message_logger,
                    )

                except ValueError as reshape_error:
                    error(
                        f"REJECTING FRAME - depth frame reshape error: {reshape_error}",
                        self._message_logger,
                    )
                    return None

                debug(
                    f"Created images - color: {color_image.shape if color_image is not None else None}, depth: {depth_image.shape}",
                    self._message_logger,
                )

                result = {
                    "timestamp": frame_color.get_timestamp(),
                    "number": self.frame_number,
                    "color": color_image,
                    "depth": depth_image,
                }

                # Record frame grab timing
                self.performance_metrics["frame_grab_times"].append(grab_timer.ms)
                return result

            except Exception as e:
                error(f"Error processing frames: {e}", self._message_logger)
                error(f"Traceback: {traceback.format_exc()}", self._message_logger)
                return None

    def fragment_image_gpu(
        self, color_image: np.ndarray, depth_image: np.ndarray
    ) -> Dict[str, Dict]:
        """Fragment images on GPU using zero-copy slicing.

        Args:
            color_image: Color image array
            depth_image: Depth image array

        Returns:
            Dictionary with GPU fragments
        """
        with Catchtime() as frag_timer:
            try:
                fragments = {}

                if not self.gpu_enabled or not self.gpu_processor:
                    # Fallback to CPU fragmentation
                    return self._fragment_image_cpu(color_image, depth_image)

                # Upload to GPU ONCE
                with Catchtime() as upload_timer:
                    gpu_color = cv2.cuda.GpuMat()
                    gpu_depth = cv2.cuda.GpuMat()
                    gpu_color.upload(color_image)
                    gpu_depth.upload(depth_image)
                
                self.performance_metrics["gpu_upload_times"].append(upload_timer.ms)

                # Fragment using GPU slicing (zero-copy)
                if (
                    hasattr(self, "pipeline_config")
                    and self.pipeline_config
                    and "fragments" in self.pipeline_config
                ):
                    fragment_configs = self.pipeline_config["fragments"]
                    debug(
                        f"GPU fragmenting into {len(fragment_configs)} parts",
                        self._message_logger,
                    )

                    for fragment_config in fragment_configs:
                        fragment_id = fragment_config.get("fragment_id", 0)
                        fragment_name = fragment_config.get(
                            "name", f"fragment_{fragment_id}"
                        )
                        roi = fragment_config.get("roi", {})

                        if "x" in roi and "y" in roi:
                            x_range = roi["x"]  # [x_min, x_max]
                            y_range = roi["y"]  # [y_min, y_max]

                            x_min, x_max = (
                                max(0, x_range[0]),
                                min(color_image.shape[1], x_range[1]),
                            )
                            y_min, y_max = (
                                max(0, y_range[0]),
                                min(color_image.shape[0], y_range[1]),
                            )

                            # GPU slicing - creates view, not copy
                            color_fragment_gpu = gpu_color.rowRange(y_min, y_max).colRange(x_min, x_max)
                            depth_fragment_gpu = gpu_depth.rowRange(y_min, y_max).colRange(x_min, x_max)

                            fragments[fragment_name] = {
                                "color_gpu": color_fragment_gpu,
                                "depth_gpu": depth_fragment_gpu,
                                "fragment_id": fragment_id,
                                "position": fragment_config.get("position", ""),
                                "roi": roi,
                                "on_gpu": True,
                            }

                            debug(
                                f"GPU Fragment {fragment_name}: ROI ({x_min},{y_min})-({x_max},{y_max})",
                                self._message_logger,
                            )
                        else:
                            error(
                                f"Invalid ROI config for fragment {fragment_name}: {roi}",
                                self._message_logger,
                            )
                else:
                    # Fallback to default 4-part fragmentation on GPU
                    debug(
                        f"No pipeline config, using default GPU 4-part fragmentation",
                        self._message_logger,
                    )
                    h, w = color_image.shape[:2]
                    mid_h, mid_w = h // 2, w // 2

                    fragments = {
                        "top_left": {
                            "color_gpu": gpu_color.rowRange(0, mid_h).colRange(0, mid_w),
                            "depth_gpu": gpu_depth.rowRange(0, mid_h).colRange(0, mid_w),
                            "fragment_id": 0,
                            "position": "top-left",
                            "on_gpu": True,
                        },
                        "top_right": {
                            "color_gpu": gpu_color.rowRange(0, mid_h).colRange(mid_w, w),
                            "depth_gpu": gpu_depth.rowRange(0, mid_h).colRange(mid_w, w),
                            "fragment_id": 1,
                            "position": "top-right",
                            "on_gpu": True,
                        },
                        "bottom_left": {
                            "color_gpu": gpu_color.rowRange(mid_h, h).colRange(0, mid_w),
                            "depth_gpu": gpu_depth.rowRange(mid_h, h).colRange(0, mid_w),
                            "fragment_id": 2,
                            "position": "bottom-left",
                            "on_gpu": True,
                        },
                        "bottom_right": {
                            "color_gpu": gpu_color.rowRange(mid_h, h).colRange(mid_w, w),
                            "depth_gpu": gpu_depth.rowRange(mid_h, h).colRange(mid_w, w),
                            "fragment_id": 3,
                            "position": "bottom-right",
                            "on_gpu": True,
                        },
                    }

                debug(
                    f"GPU fragmented {color_image.shape[1]}x{color_image.shape[0]} into {len(fragments)} parts in {frag_timer.ms:.2f}ms",
                    self._message_logger,
                )

                self.performance_metrics["fragmentation_times"].append(frag_timer.ms)
                return fragments

            except Exception as e:
                error(f"Error GPU fragmenting image: {e}", self._message_logger)
                error(f"Traceback: {traceback.format_exc()}", self._message_logger)
                # Fallback to CPU
                return self._fragment_image_cpu(color_image, depth_image)

    def _fragment_image_cpu(
        self, color_image: np.ndarray, depth_image: np.ndarray
    ) -> Dict[str, Dict]:
        """CPU fallback for image fragmentation."""
        fragments = {}

        if (
            hasattr(self, "pipeline_config")
            and self.pipeline_config
            and "fragments" in self.pipeline_config
        ):
            fragment_configs = self.pipeline_config["fragments"]

            for fragment_config in fragment_configs:
                fragment_id = fragment_config.get("fragment_id", 0)
                fragment_name = fragment_config.get(
                    "name", f"fragment_{fragment_id}"
                )
                roi = fragment_config.get("roi", {})

                if "x" in roi and "y" in roi:
                    x_range = roi["x"]
                    y_range = roi["y"]

                    x_min, x_max = (
                        max(0, x_range[0]),
                        min(color_image.shape[1], x_range[1]),
                    )
                    y_min, y_max = (
                        max(0, y_range[0]),
                        min(color_image.shape[0], y_range[1]),
                    )

                    fragments[fragment_name] = {
                        "color": color_image[y_min:y_max, x_min:x_max].copy(),
                        "depth": depth_image[y_min:y_max, x_min:x_max].copy(),
                        "fragment_id": fragment_id,
                        "position": fragment_config.get("position", ""),
                        "roi": roi,
                        "on_gpu": False,
                    }
        else:
            # Default 4-part fragmentation
            h, w = color_image.shape[:2]
            mid_h, mid_w = h // 2, w // 2

            fragments = {
                "top_left": {
                    "color": color_image[0:mid_h, 0:mid_w].copy(),
                    "depth": depth_image[0:mid_h, 0:mid_w].copy(),
                    "fragment_id": 0,
                    "position": "top-left",
                    "on_gpu": False,
                },
                "top_right": {
                    "color": color_image[0:mid_h, mid_w:w].copy(),
                    "depth": depth_image[0:mid_h, mid_w:w].copy(),
                    "fragment_id": 1,
                    "position": "top-right",
                    "on_gpu": False,
                },
                "bottom_left": {
                    "color": color_image[mid_h:h, 0:mid_w].copy(),
                    "depth": depth_image[mid_h:h, 0:mid_w].copy(),
                    "fragment_id": 2,
                    "position": "bottom-left",
                    "on_gpu": False,
                },
                "bottom_right": {
                    "color": color_image[mid_h:h, mid_w:w].copy(),
                    "depth": depth_image[mid_h:h, mid_w:w].copy(),
                    "fragment_id": 3,
                    "position": "bottom-right",
                    "on_gpu": False,
                },
            }

        return fragments

    def serialize_fragments(
        self, fragments: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Serialize fragments (download from GPU if needed).

        Args:
            fragments: Dictionary of fragments (may be on GPU or CPU)

        Returns:
            Dict[str, Dict[str, Any]]: Fragments ready for JSON serialization
        """
        with Catchtime() as ser_timer:
            try:
                serializable_fragments = {}

                for fragment_name, fragment_data in fragments.items():
                    serializable_fragment = {}
                    on_gpu = fragment_data.get("on_gpu", False)

                    # Download from GPU if needed
                    for key, value in fragment_data.items():
                        if key.endswith("_gpu") and on_gpu:
                            # Download from GPU
                            cpu_array = value.download()
                            # Serialize to base64
                            array_bytes = cpu_array.tobytes()
                            encoded_array = base64.b64encode(array_bytes).decode("utf-8")
                            
                            serializable_fragment[key.replace("_gpu", "")] = {
                                "data": encoded_array,
                                "dtype": str(cpu_array.dtype),
                                "shape": cpu_array.shape,
                            }
                        elif isinstance(value, np.ndarray):
                            # CPU array - serialize directly
                            array_bytes = value.tobytes()
                            encoded_array = base64.b64encode(array_bytes).decode("utf-8")
                            
                            serializable_fragment[key] = {
                                "data": encoded_array,
                                "dtype": str(value.dtype),
                                "shape": value.shape,
                            }
                        elif not key.endswith("_gpu") and key not in ["on_gpu"]:
                            # Other metadata
                            serializable_fragment[key] = value

                    serializable_fragments[fragment_name] = serializable_fragment

                debug(
                    f"Serialized {len(fragments)} fragments in {ser_timer.ms:.2f}ms",
                    self._message_logger,
                )

                self.performance_metrics["serialization_times"].append(ser_timer.ms)
                return serializable_fragments

            except Exception as e:
                error(
                    f"Error serializing fragments: {e}", self._message_logger
                )
                error(f"Traceback: {traceback.format_exc()}", self._message_logger)
                return {}
        
    #save fragments to file
    async def save_image_opencv(self, image, filename, folder="temp/images"):
        # Create directory if it doesn't exist
        os.makedirs(folder, exist_ok=True)
        # Create full file path
        filepath = os.path.join(folder, filename)
        # Save the image
        cv2.imwrite(filepath, image)

    async def process_frame_to_fragments(
        self, frame_data: Dict[str, Any]
    ) -> Optional[bytes]:
        """Process frame data into serialized fragments using GPU."""
        try:
            color_image = frame_data.get("color")
            depth_image = frame_data.get("depth")

            if color_image is None or depth_image is None:
                error(
                    "Missing color or depth image in frame data", self._message_logger
                )
                return None

            # Fragment on GPU
            fragments = self.fragment_image_gpu(color_image, depth_image)

            if not fragments:
                error("Failed to fragment images", self._message_logger)
                return None
            
            # for key, fragment in fragments.items():
            #     # img = cv2.imread(fragment)
            #     await self.save_image_opencv(fragment['color'], f"fragment_{key}.jpg")

            # Serialize fragments (downloads from GPU)
            serialized_fragments = self.serialize_fragments(fragments)

            if not serialized_fragments:
                error("Failed to serialize fragments", self._message_logger)
                return None

            # Store for later retrieval
            self.last_fragments = serialized_fragments
            return serialized_fragments

        except Exception as e:
            error(f"Error processing frame to fragments: {e}", self._message_logger)
            error(f"Traceback: {traceback.format_exc()}", self._message_logger)
            return None

    def _run(self, pipe_in):
        """Synchronous pipe loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_run(pipe_in))
        finally:
            loop.close()

    async def _async_run(self, pipe_in):
        """Main async worker loop (same as CPU version)."""
        # Create local logger for this process
        self._message_logger = MessageLogger(
            filename=f"temp/pepper_camera_gpu_worker{self.__camera_ip}.log",
            debug=True,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=10,
            colors=False,
        )

        debug(f"{self.device_name} - GPU worker started", self._message_logger)

        start_time = asyncio.get_event_loop().time()
        frame_grabbed = False

        try:
            while True:
                # Check for pipe commands
                if pipe_in.poll(0.0001):
                    data = pipe_in.recv()

                    match data[0]:
                        case "CAMERA_INIT":
                            try:
                                debug(
                                    f"{self.device_name} - Received CAMERA_INIT",
                                    self._message_logger,
                                )
                                await self.init_camera(data[1])
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error in CAMERA_INIT: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(False)

                        case "CAMERA_START_GRABBING":
                            try:
                                debug(
                                    f"{self.device_name} - Starting frame grabbing",
                                    self._message_logger,
                                )
                                await self.start_camera()
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error starting grabbing: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(False)

                        case "CAMERA_STOP_GRABBING":
                            try:
                                debug(
                                    f"{self.device_name} - Stopping grabbing",
                                    self._message_logger,
                                )
                                await self.stop_camera()
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error stopping grabbing: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(False)

                        case "GET_STATE":
                            try:
                                pipe_in.send(self.state)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error getting state: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(None)

                        case "GET_LAST_FRAME":
                            try:
                                pipe_in.send(self.last_frame)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error getting last frame: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(None)

                        case "FRAGMENT_AND_SERIALIZE":
                            try:
                                debug(
                                    f"{self.device_name} - GPU processing frame to fragments",
                                    self._message_logger,
                                )
                                frame_data = data[1]
                                result = await self.process_frame_to_fragments(
                                    frame_data
                                )
                                pipe_in.send(result is not None)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error in GPU fragment processing: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(False)

                        case "GET_LAST_FRAGMENTS":
                            try:
                                pipe_in.send(self.last_fragments)
                                if self.last_fragments is not None:
                                    self.last_fragments = None  # Clear after sending
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error getting fragments: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(None)

                        case _:
                            error(
                                f"{self.device_name} - Unknown command: {data[0]}",
                                self._message_logger,
                            )

                # Continuous frame grabbing when started
                if self.state == CameraState.STARTED:
                    current_time = asyncio.get_event_loop().time()

                    # Reset frame_grabbed flag every 33.3ms (30 Hz)
                    if current_time - start_time >= 0.0333:
                        frame_grabbed = False
                        start_time = current_time

                    if not frame_grabbed:
                        with Catchtime() as ct:
                            frames = await self.grab_frames_from_camera()
                            if frames is not None:
                                frame_grabbed = True
                                self.last_frame = frames

        except asyncio.CancelledError:
            info(f"{self.device_name} - Task was cancelled", self._message_logger)
        except Exception as e:
            error(f"{self.device_name} - Error in Worker: {e}", self._message_logger)
            error(f"Traceback:\n{traceback.format_exc()}", self._message_logger)
        finally:
            info(
                f"{self.device_name} - GPU worker has shut down",
                self._message_logger,
            )


class PepperCameraGPUConnector(GeneralCameraConnector):
    """Thread-safe connector for PepperCameraGPUWorker.

    Provides synchronous API using pipe communication to GPU worker process.
    """

    def __init__(
        self,
        camera_ip: str,
        core: int = 8,
        message_logger: Optional[MessageLogger] = None,
    ):
        """Create GPU connector and start worker process.

        Args:
            camera_ip (str): IP address of the camera
            core (int): CPU core affinity for worker process
            message_logger (Optional[MessageLogger]): Message logger
        """
        self.camera_ip = camera_ip
        super().__init__(core=core, message_logger=message_logger)

    def _run(self, pipe_in, message_logger=None):
        """Run GPU worker in separate process."""
        worker = PepperCameraGPUWorker(
            camera_ip=self.camera_ip, message_logger=message_logger
        )
        asyncio.run(worker._run(pipe_in))

    def fragment_and_serialize_frame(self, frame_data: dict):
        """Process frame into fragments and serialize using GPU."""
        with self._GeneralCameraConnector__lock:
            return super()._send_thru_pipe(
                self._pipe_out, ["FRAGMENT_AND_SERIALIZE", frame_data]
            )

    def get_last_fragments(self):
        """Get last processed fragments."""
        with self._GeneralCameraConnector__lock:
            return super()._send_thru_pipe(self._pipe_out, ["GET_LAST_FRAGMENTS"])
