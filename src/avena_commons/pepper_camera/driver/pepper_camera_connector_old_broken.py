"""PepperCamera Connector and Worker for simplified camera processing with fragmentation."""

import asyncio
import pickle
import threading
import traceback
from typing import Optional, Dict, Any

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

from avena_commons.camera.driver.general import CameraState
from avena_commons.util.logger import (
    MessageLogger,
    debug,
    error,
    info,
    LoggerPolicyPeriod,
)
from avena_commons.util.worker import Connector, Worker
from avena_commons.util.catchtime import Catchtime


class PepperCameraWorker(Worker):
    """Simplified camera worker for pepper processing with fragmentation and serialization.

    Handles:
    - Orbec camera connection and frame grabbing
    - Image fragmentation into 4 parts (top_left, top_right, bottom_left, bottom_right)
    - Serialization of fragments for transmission to Pepper EventListener
    """

    def __init__(self, camera_ip: str, message_logger: Optional[MessageLogger] = None):
        """Initialize PepperCamera worker.

        Args:
            camera_ip (str): IP address of the Orbec camera
            message_logger (Optional[MessageLogger]): Logger for messages
        """
        self.__camera_ip = camera_ip
        self._message_logger = None  # Will be set in worker process
        self.device_name = f"PepperCamera_{camera_ip}"
        super().__init__(message_logger=None)

        # Camera state and resources
        self.state = CameraState.IDLE
        self.camera_pipeline = None
        self.camera_config = None
        self.camera_configuration = None
        self.pipeline_config = None  # For fragment configuration

        # Frame processing
        self.last_frame = None
        self.last_fragments = None
        self.frame_number = 0

        # Filters
        self.align_filter = None
        self.spatial_filter = None
        self.temporal_filter = None

    @property
    def state(self) -> CameraState:
        return self.__state

    @state.setter
    def state(self, value: CameraState) -> None:
        debug(
            f"{self.device_name} - State changed to {value.name}", self._message_logger
        )
        self.__state = value

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
        """Initialize camera connection and configuration."""
        try:
            self.state = CameraState.INITIALIZING
            debug(
                f"{self.device_name} - Initializing pepper camera", self._message_logger
            )

            print("Camera settings: ", camera_settings)

            # Store pipeline configuration for fragmentation
            self.pipeline_config = camera_settings.get("camera_pipeline", {})
            debug(f"Pipeline config: {self.pipeline_config}", self._message_logger)

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

            # MARK: Disparity Settings
            try:
                disparity_settings = camera_settings.get("disparity", {})
                if disparity_settings:
                    disparity_pid = OBPropertyID.OB_STRUCT_DISPARITY_RANGE_MODE
                    if not dev.is_property_supported(
                        disparity_pid, OBPermissionType.PERMISSION_READ_WRITE
                    ):
                        error(
                            f"CAMERA_INIT: Zmiana trybu zakresu dysparycji nie jest obsługiwana w kamerze. Sprawdź wersję firmware.",
                            self._message_logger,
                        )
                    else:
                        # Set Disparity Range Mode
                        desired_mode_name = disparity_settings.get("range_mode")
                        if desired_mode_name:
                            current_mode = dev.get_disparity_range_mode()
                            debug(
                                f"CAMERA_INIT: Aktualny tryb zakresu dysparycji: {current_mode.name}",
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
                                        f"CAMERA_INIT: Ustawiono tryb zakresu dysparycji na {mode.name}",
                                        self._message_logger,
                                    )
                                    is_mode_set = True
                                    break

                            if not is_mode_set:
                                error(
                                    f"CAMERA_INIT: Żądany tryb zakresu dysparycji '{desired_mode_name}' nie został znaleziony. Dostępne tryby: {available_mode_names}. Używam bieżącego: {current_mode.name}",
                                    self._message_logger,
                                )

                # Set Disparity Search Offset
                offset_pid = OBPropertyID.OB_STRUCT_DISPARITY_SEARCH_OFFSET
                if not dev.is_property_supported(
                    offset_pid, OBPermissionType.PERMISSION_READ_WRITE
                ):
                    debug(
                        f"Przesunięcie wyszukiwania dysparycji nie jest obsługiwane w kamerze",
                        self._message_logger,
                    )
                else:
                    disparity_offset = disparity_settings.get("search_offset")
                    if disparity_offset and disparity_offset > 0:
                        dev.set_int_property(offset_pid, disparity_offset)
                        debug(
                            f"Kamera {self.device_name} - Ustawiono przesunięcie wyszukiwania dysparycji na {disparity_offset}",
                            self._message_logger,
                        )
            except AttributeError as e:
                error(
                    f"Używana wersja pyorbbecsdk nie obsługuje zmiany trybu dysparycji. Wymagana jest wersja >= 2.2.x. Ta funkcja zostanie pominięta. Błąd: {e}",
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

            # color_format = {
            #     "BGR": OBFormat.BGR,
            #     "RGB": OBFormat.RGB,
            #     "MJPG": OBFormat.MJPG
            # }.get(color_settings.get("format", "BGR"), OBFormat.BGR)

            match color_settings.get("format", "BGR"):
                case "BGR":
                    color_format = OBFormat.BGR
                case "RGB":
                    color_format = OBFormat.RGB
                case "MJPG":
                    color_format = OBFormat.MJPG
                case _:
                    error(
                        f"Nieznany format koloru: {color_settings.get('format', 'BGR')} - używam BGR",
                        self._message_logger,
                    )
                    color_format = OBFormat.BGR  # Ustaw domyślny format

            width = color_settings.get("width", 640)
            height = color_settings.get("height", 400)
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
                f"Ustawiono profil koloru dla {width}x{height}@{fps} {color_format}",
                self._message_logger,
            )
            match camera_settings.get("align", None):
                case "d2c":
                    # bedziemy wyrownywac strumienie
                    # 1. Sprawdź czy sprzętowe wyrównanie jest obsługiwane dla tego profilu
                    hw_d2c_profile_list = (
                        self.camera_pipeline.get_d2c_depth_profile_list(
                            color_profile, OBAlignMode.HW_MODE
                        )
                    )
                    if not hw_d2c_profile_list or len(hw_d2c_profile_list) == 0:
                        error(
                            f"CAMERA_INIT: Żądany profil {width}x{height}@{fps} {color_format} 'NIE OBSŁUGUJE' sprzętowego wyrównania. Przełączam na programowe.",
                            self._message_logger,
                        )
                        # self.camera_config.set_align_mode(OBAlignMode.SW_MODE)
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
                        # 2. Jeśli jest, to użyj go
                        # self.camera_config.set_align_mode(OBAlignMode.HW_MODE)
                        depth_profile = hw_d2c_profile_list[0]
                    debug(
                        f"Włączono sprzętowe wyrównanie dla strumienia głębi: {depth_profile}",
                        self._message_logger,
                    )

                    # 3. Jeśli nie, to użyj programowego wyrównania

                    pass
                case "c2d":
                    # nie bedziemy wyrownywac strumieni
                    pass
                case _:
                    # nie bedziemy wyrownywac strumieni
                    pass

            self.camera_config.enable_stream(depth_profile)
            debug(
                f"CAMERA_INIT: Włączono strumień głębi: {depth_profile.get_width()}x{depth_profile.get_height()}@{depth_profile.get_fps()} {depth_profile.get_format()}",
                self._message_logger,
            )
            self.camera_config.enable_stream(color_profile)
            debug(
                f"CAMERA_INIT: Włączono strumień koloru: {color_profile.get_width()}x{color_profile.get_height()}@{color_profile.get_fps()} {color_profile.get_format()}",
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

            info("PepperCamera configuration completed", self._message_logger)
            self.state = CameraState.INITIALIZED
            return True

        except Exception as e:
            error(f"{self.device_name} - Init failed: {e}", self._message_logger)
            self.state = CameraState.ERROR
            return False

    async def start(self):
        """Start camera pipeline."""
        try:
            self.state = CameraState.STARTING
            debug(
                f"{self.device_name} - Starting camera pipeline", self._message_logger
            )

            if not self.camera_pipeline or not self.camera_config:
                raise ValueError("Camera not initialized")

            self.camera_pipeline.start(self.camera_config)
            self.last_frame = None
            self.state = CameraState.STARTED
            return True

        except Exception as e:
            error(f"{self.device_name} - Start failed: {e}", self._message_logger)
            self.state = CameraState.ERROR
            return False

    async def stop(self):
        """Stop camera pipeline."""
        try:
            self.state = CameraState.STOPPING
            debug(
                f"{self.device_name} - Stopping camera pipeline", self._message_logger
            )

            if self.camera_pipeline:
                self.camera_pipeline.stop()

            self.state = CameraState.STOPPED
            return True

        except Exception as e:
            error(f"{self.device_name} - Stop failed: {e}", self._message_logger)
            self.state = CameraState.ERROR
            return False

    async def grab_frames_from_camera(self):
        """Grab and process frames from camera."""
        try:
            frames = self.camera_pipeline.wait_for_frames(3)
            if frames is None:
                return None

            frame_color = frames.get_color_frame()
            frame_depth = frames.get_depth_frame()

            if frame_color is None or frame_depth is None:
                debug("Missing frame data, skip...", self._message_logger)
                return None

            self.frame_number += 1

            # Apply alignment filter if configured
            if self.align_filter:
                aligned_frames = self.align_filter.process(frames)
                aligned_frames = aligned_frames.as_frame_set()
                frame_depth = aligned_frames.get_depth_frame()
                debug("Alignment filter applied", self._message_logger)

            # Apply other filters
            if self.spatial_filter and frame_depth:
                frame_depth = self.spatial_filter.process(frame_depth)
            if self.temporal_filter and frame_depth:
                frame_depth = self.temporal_filter.process(frame_depth)

            # Process color frame
            color_image = None
            if frame_color.get_format() == OBFormat.MJPG:
                color_data = frame_color.get_data()
                color_image = cv2.imdecode(
                    np.frombuffer(color_data, np.uint8), cv2.IMREAD_COLOR
                )
                if color_image is None:
                    error("Failed to decode MJPG color frame", self._message_logger)
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
            except ValueError as e:
                error(f"Failed to reshape depth frame: {e}", self._message_logger)
                return None

            return {
                "timestamp": frame_color.get_timestamp(),
                "number": self.frame_number,
                "color": color_image,
                "depth": depth_image,
            }

        except Exception as e:
            error(f"Error grabbing frames: {e}", self._message_logger)
            return None

    def fragment_image(
        self, color_image: np.ndarray, depth_image: np.ndarray
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """Fragment images based on pipeline configuration.

        Args:
            color_image: Color image array
            depth_image: Depth image array

        Returns:
            Dictionary with fragments based on pipeline config
        """
        try:
            fragments = {}

            # Use pipeline configuration if available
            if (
                hasattr(self, "pipeline_config")
                and self.pipeline_config
                and "fragments" in self.pipeline_config
            ):
                fragment_configs = self.pipeline_config["fragments"]
                debug(
                    f"Using {len(fragment_configs)} fragments from pipeline config",
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

                        fragments[fragment_name] = {
                            "color": color_image[y_min:y_max, x_min:x_max].copy(),
                            "depth": depth_image[y_min:y_max, x_min:x_max].copy(),
                            "fragment_id": fragment_id,
                            "position": fragment_config.get("position", ""),
                            "roi": roi,
                        }

                        debug(
                            f"Fragment {fragment_name}: ROI ({x_min},{y_min})-({x_max},{y_max})",
                            self._message_logger,
                        )
                    else:
                        error(
                            f"Invalid ROI config for fragment {fragment_name}: {roi}",
                            self._message_logger,
                        )
            else:
                # Fallback to default 4-part fragmentation if no config
                debug(
                    f"No pipeline config, using default 4-part fragmentation",
                    self._message_logger,
                )
                h, w = color_image.shape[:2]
                mid_h, mid_w = h // 2, w // 2

                fragments = {
                    "top_left": {
                        "color": color_image[0:mid_h, 0:mid_w].copy(),
                        "depth": depth_image[0:mid_h, 0:mid_w].copy(),
                        "fragment_id": 0,
                        "position": "top-left",
                    },
                    "top_right": {
                        "color": color_image[0:mid_h, mid_w:w].copy(),
                        "depth": depth_image[0:mid_h, mid_w:w].copy(),
                        "fragment_id": 1,
                        "position": "top-right",
                    },
                    "bottom_left": {
                        "color": color_image[mid_h:h, 0:mid_w].copy(),
                        "depth": depth_image[mid_h:h, 0:mid_w].copy(),
                        "fragment_id": 2,
                        "position": "bottom-left",
                    },
                    "bottom_right": {
                        "color": color_image[mid_h:h, mid_w:w].copy(),
                        "depth": depth_image[mid_h:h, mid_w:w].copy(),
                        "fragment_id": 3,
                        "position": "bottom-right",
                    },
                }

            debug(
                f"Fragmented image {color_image.shape[1]}x{color_image.shape[0]} into {len(fragments)} parts",
                self._message_logger,
            )
            return fragments

        except Exception as e:
            error(f"Error fragmenting image: {e}", self._message_logger)
            return {}

    def serialize_fragments(self, fragments: Dict[str, Dict[str, np.ndarray]]) -> bytes:
        """Serialize fragments for transmission.

        Args:
            fragments: Dictionary of image fragments

        Returns:
            Serialized fragments as bytes
        """
        try:
            with Catchtime() as ct:
                serialized_data = pickle.dumps(fragments)

            size_mb = len(serialized_data) / (1024 * 1024)
            debug(
                f"Serialized {len(fragments)} fragments to {size_mb:.2f}MB in {ct.ms:.1f}ms",
                self._message_logger,
            )
            return serialized_data

        except Exception as e:
            error(f"Error serializing fragments: {e}", self._message_logger)
            return b""

    async def process_frame_to_fragments(
        self, frame_data: Dict[str, Any]
    ) -> Optional[bytes]:
        """Process frame data into serialized fragments.

        Args:
            frame_data: Frame data containing color and depth images

        Returns:
            Serialized fragments or None on error
        """
        try:
            color_image = frame_data.get("color")
            depth_image = frame_data.get("depth")

            if color_image is None or depth_image is None:
                error(
                    "Missing color or depth image in frame data", self._message_logger
                )
                return None

            # Fragment the images
            with Catchtime() as frag_time:
                fragments = self.fragment_image(color_image, depth_image)

            if not fragments:
                error("Failed to fragment images", self._message_logger)
                return None

            # Serialize fragments
            with Catchtime() as ser_time:
                serialized_fragments = self.serialize_fragments(fragments)

            if not serialized_fragments:
                error("Failed to serialize fragments", self._message_logger)
                return None

            debug(
                f"Frame processing: fragment={frag_time.ms:.2f}ms, serialize={ser_time.ms:.2f}ms",
                self._message_logger,
            )

            # Store for later retrieval
            self.last_fragments = serialized_fragments
            return serialized_fragments

        except Exception as e:
            error(f"Error processing frame to fragments: {e}", self._message_logger)
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
        """Main async worker loop handling pipe commands and frame processing."""
        # Create local logger for this process
        self._message_logger = MessageLogger(
            filename=f"temp/pepper_camera_worker.log",
            debug=True,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=10,
            colors=False,
        )

        debug(f"{self.device_name} - PepperCamera worker started", self._message_logger)

        try:
            while True:
                # Check for pipe commands
                if pipe_in.poll(0.0001):
                    data = pipe_in.recv()

                    match data[0]:
                        case "PEPPER_CAMERA_INIT":
                            try:
                                debug(
                                    f"{self.device_name} - Received PEPPER_CAMERA_INIT",
                                    self._message_logger,
                                )
                                await self.init(data[1])
                                self.camera_configuration = data[1]
                                # Store pipeline config from camera configuration
                                self.pipeline_config = data[1].get("pipeline", {})
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error in PEPPER_CAMERA_INIT: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(False)

                        case "PEPPER_CAMERA_START_GRABBING":
                            try:
                                debug(
                                    f"{self.device_name} - Starting frame grabbing",
                                    self._message_logger,
                                )
                                await self.start()
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error starting grabbing: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(False)

                        case "PEPPER_CAMERA_STOP_GRABBING":
                            try:
                                debug(
                                    f"{self.device_name} - Stopping grabbing",
                                    self._message_logger,
                                )
                                await self.stop()
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
                                    f"{self.device_name} - Processing frame to fragments",
                                    self._message_logger,
                                )
                                frame_data = data[1]
                                self.state = CameraState.RUNNING

                                # Process frame asynchronously
                                task = asyncio.create_task(
                                    self.process_frame_to_fragments(frame_data)
                                )
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error in fragment processing: {e}",
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
                    with Catchtime() as ct:
                        frames = await self.grab_frames_from_camera()
                        if frames is None:
                            continue
                        self.last_frame = frames

        except asyncio.CancelledError:
            info(f"{self.device_name} - Task was cancelled", self._message_logger)
        except Exception as e:
            error(f"{self.device_name} - Error in Worker: {e}", self._message_logger)
            error(f"Traceback:\n{traceback.format_exc()}", self._message_logger)
        finally:
            info(
                f"{self.device_name} - PepperCamera worker has shut down",
                self._message_logger,
            )


class PepperCameraConnector(Connector):
    """Thread-safe connector for PepperCameraWorker.

    Provides synchronous API using pipe communication to worker process.
    """

    def __init__(
        self,
        camera_ip: str,
        core: int = 8,
        message_logger: Optional[MessageLogger] = None,
    ):
        """Create connector and start worker process.

        Args:
            camera_ip (str): IP address of the camera
            core (int): CPU core affinity for worker process
            message_logger (Optional[MessageLogger]): Message logger
        """
        self.camera_ip = camera_ip
        self.__lock = threading.Lock()
        super().__init__(core=core, message_logger=message_logger)
        super()._connect()

    def _run(self, pipe_in, message_logger=None):
        """Run worker in separate process."""
        worker = PepperCameraWorker(
            camera_ip=self.camera_ip, message_logger=message_logger
        )
        asyncio.run(worker._run(pipe_in))

    def init(self, configuration: dict = {}):
        """Initialize pepper camera with configuration."""
        with self.__lock:
            return super()._send_thru_pipe(
                self._pipe_out, ["PEPPER_CAMERA_INIT", configuration]
            )

    def start(self):
        """Start frame grabbing."""
        with self.__lock:
            return super()._send_thru_pipe(
                self._pipe_out, ["PEPPER_CAMERA_START_GRABBING"]
            )

    def stop(self):
        """Stop frame grabbing."""
        with self.__lock:
            return super()._send_thru_pipe(
                self._pipe_out, ["PEPPER_CAMERA_STOP_GRABBING"]
            )

    def get_state(self):
        """Get current camera state."""
        with self.__lock:
            return super()._send_thru_pipe(self._pipe_out, ["GET_STATE"])

    def get_last_frame(self):
        """Get last grabbed frame."""
        with self.__lock:
            return super()._send_thru_pipe(self._pipe_out, ["GET_LAST_FRAME"])

    def fragment_and_serialize_frame(self, frame_data: dict):
        """Process frame into fragments and serialize."""
        with self.__lock:
            return super()._send_thru_pipe(
                self._pipe_out, ["FRAGMENT_AND_SERIALIZE", frame_data]
            )

    def get_last_fragments(self):
        """Get last processed fragments."""
        with self.__lock:
            return super()._send_thru_pipe(self._pipe_out, ["GET_LAST_FRAGMENTS"])
