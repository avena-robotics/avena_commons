"""Virtual PepperCamera implementation for testing and scaling without hardware.

This module provides a virtual camera that generates synthetic frames with the same
characteristics as the physical Orbec camera, allowing for:
- Testing without hardware
- Scaling to multiple camera instances
- Performance benchmarking
- Development without camera access

Exposes:
- VirtualPepperCameraWorker: Worker generating synthetic frames
- VirtualPepperCameraConnector: Thread-safe connector interface
"""

import asyncio
import base64
import time
from typing import Any, Dict, Optional

import cv2
import numpy as np

from avena_commons.camera.driver.general import (
    CameraState,
    GeneralCameraConnector,
    GeneralCameraWorker,
)
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
    debug,
    error,
    info,
)
from avena_commons.util.sync_timer import now_ns


class VirtualPepperCameraWorker(GeneralCameraWorker):
    """Virtual camera worker generating synthetic frames.

    Simulates Orbec Gemini 335Le camera behavior:
    - Same resolution and format as physical camera
    - Synthetic color and depth data generation
    - Frame rate control
    - Fragmentation and serialization support
    """

    def __init__(
        self, camera_id: str = "virtual", message_logger: Optional[MessageLogger] = None
    ):
        """Initialize virtual camera worker.

        Args:
            camera_id (str): Identifier for this virtual camera instance
            message_logger (Optional[MessageLogger]): Logger for messages
        """
        self._message_logger = None  # Will be set in worker process
        self.camera_id = camera_id
        self.device_name = f"VirtualPepperCamera_{camera_id}"
        super().__init__(message_logger=None)

        # Camera configuration
        self.color_width = 640
        self.color_height = 400
        self.depth_width = 1280
        self.depth_height = 800
        self.fps = 30
        self.frame_number = 0

        # Pipeline configuration for fragmentation
        self.pipeline_config = None
        self.last_fragments = None

        # Performance metrics
        self.performance_metrics = {
            "frame_generation_times": [],
            "fragmentation_times": [],
            "serialization_times": [],
        }

    async def init(self, camera_settings: dict):
        """Initialize virtual camera with settings.

        Args:
            camera_settings (dict): Camera configuration dictionary

        Returns:
            bool: True if initialization successful
        """
        try:
            self.state = CameraState.INITIALIZING
            debug(
                f"{self.device_name} - Initializing virtual camera",
                self._message_logger,
            )

            # Extract camera settings
            color_settings = camera_settings.get("color", {})
            depth_settings = camera_settings.get("depth", {})

            self.color_width = color_settings.get("width", 640)
            self.color_height = color_settings.get("height", 400)
            self.fps = color_settings.get("fps", 30)

            self.depth_width = depth_settings.get("width", 640)
            self.depth_height = depth_settings.get("height", 400)

            # Store pipeline configuration for fragmentation
            self.pipeline_config = camera_settings.get("camera_pipeline", {})

            debug(
                f"{self.device_name} - Virtual camera configured: {self.color_width}x{self.color_height}@{self.fps}fps",
                self._message_logger,
            )

            self.state = CameraState.INITIALIZED
            return True

        except Exception as e:
            error(f"{self.device_name} - Init failed: {e}", self._message_logger)
            self.state = CameraState.ERROR
            return False

    async def start(self):
        """Start virtual camera frame generation.

        Returns:
            bool: True if start successful
        """
        try:
            self.state = CameraState.STARTING
            debug(f"{self.device_name} - Starting virtual camera", self._message_logger)

            self.frame_number = 0
            self.state = CameraState.STARTED

            debug(f"{self.device_name} - Virtual camera started", self._message_logger)
            return True

        except Exception as e:
            error(f"{self.device_name} - Start failed: {e}", self._message_logger)
            self.state = CameraState.ERROR
            return False

    async def stop(self):
        """Stop virtual camera frame generation.

        Returns:
            bool: True if stop successful
        """
        try:
            self.state = CameraState.STOPPING
            debug(f"{self.device_name} - Stopping virtual camera", self._message_logger)

            self.state = CameraState.STOPPED
            debug(f"{self.device_name} - Virtual camera stopped", self._message_logger)
            return True

        except Exception as e:
            error(f"{self.device_name} - Stop failed: {e}", self._message_logger)
            self.state = CameraState.ERROR
            return False

    async def grab_frames_from_camera(self):
        """Generate synthetic color and depth frames.

        Returns:
            dict: Frame data with 'color', 'depth', 'timestamp', 'number'
        """
        with Catchtime() as gen_timer:
            try:
                # Generate synthetic color image (BGR format like real camera)
                color_image = self._generate_synthetic_color(
                    self.color_width, self.color_height
                )

                # Generate synthetic depth image (uint16 like real camera)
                depth_image = self._generate_synthetic_depth(
                    self.color_width,
                    self.color_height,  # Aligned to color
                )

                self.frame_number += 1

                # Record generation time
                self.performance_metrics["frame_generation_times"].append(gen_timer.ms)

                result = {
                    "timestamp": int(time.time() * 1000),
                    "number": self.frame_number,
                    "color": color_image,
                    "depth": depth_image,
                }

                debug(
                    f"{self.device_name} - Generated frame {self.frame_number} in {gen_timer.ms:.2f}ms",
                    self._message_logger,
                )

                return result

            except Exception as e:
                error(
                    f"{self.device_name} - Frame generation error: {e}",
                    self._message_logger,
                )
                return None

    def _generate_synthetic_color(self, width: int, height: int) -> np.ndarray:
        """Generate realistic-looking synthetic color image.

        Creates an image with:
        - Gradient background
        - Random noise for realism
        - Simulated pepper-like red regions

        Args:
            width (int): Image width
            height (int): Image height

        Returns:
            np.ndarray: BGR color image (uint8)
        """
        # Create base gradient (gray-ish background)
        color = np.zeros((height, width, 3), dtype=np.uint8)

        # Add gradient
        for y in range(height):
            intensity = int(80 + (y / height) * 60)  # 80-140 range
            color[y, :, :] = intensity

        # Add some Gaussian noise for realism
        noise = np.random.normal(0, 10, (height, width, 3)).astype(np.int16)
        color = np.clip(color.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # Add simulated red pepper regions (4 regions for 4 fragments)
        regions = [
            (width // 4, height // 4),  # Top-left region
            (3 * width // 4, height // 4),  # Top-right region
            (width // 4, 3 * height // 4),  # Bottom-left region
            (3 * width // 4, 3 * height // 4),  # Bottom-right region
        ]

        for cx, cy in regions:
            # Random size and shape for variety
            radius = np.random.randint(20, 40)

            # Draw red-ish circle (simulating pepper)
            cv2.circle(
                color,
                (cx, cy),
                radius,
                (40, 40, 180 + np.random.randint(-30, 30)),  # Red in BGR
                -1,
            )

        return color

    def _generate_synthetic_depth(self, width: int, height: int) -> np.ndarray:
        """Generate realistic-looking synthetic depth image.

        Creates depth data with:
        - Background at ~800mm
        - Objects (peppers) at ~250mm
        - Some noise for realism

        Args:
            width (int): Image width
            height (int): Image height

        Returns:
            np.ndarray: Depth image in mm (uint16)
        """
        # Background depth (~800mm)
        depth = np.full((height, width), 800, dtype=np.uint16)

        # Add depth variation (noise)
        noise = np.random.randint(-50, 50, (height, width), dtype=np.int16)
        depth = np.clip(depth.astype(np.int16) + noise, 200, 1000).astype(np.uint16)

        # Add closer objects (simulated peppers) at same locations as color
        regions = [
            (width // 4, height // 4),
            (3 * width // 4, height // 4),
            (width // 4, 3 * height // 4),
            (3 * width // 4, 3 * height // 4),
        ]

        for cx, cy in regions:
            radius = np.random.randint(20, 40)
            # Objects closer to camera (200-300mm)
            object_depth = np.random.randint(200, 300)
            cv2.circle(depth, (cx, cy), radius, int(object_depth), -1)

        return depth

    def fragment_image(
        self, color_image: np.ndarray, depth_image: np.ndarray
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """Fragment images based on pipeline configuration.

        Same logic as PepperCameraWorker for consistency.

        Args:
            color_image: Color image array
            depth_image: Depth image array

        Returns:
            Dictionary with fragments based on pipeline config
        """
        with Catchtime() as frag_timer:
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
                    # Fallback to default 4-part fragmentation
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

                # Record fragmentation timing
                self.performance_metrics["fragmentation_times"].append(frag_timer.ms)
                return fragments

            except Exception as e:
                error(f"Error fragmenting image: {e}", self._message_logger)
                return {}

    def serialize_fragments(
        self, fragments: Dict[str, Dict[str, np.ndarray]]
    ) -> Dict[str, Dict[str, Any]]:
        """Convert fragments to JSON-serializable format.

        Same logic as PepperCameraWorker for consistency.

        Args:
            fragments: Dictionary of fragments with numpy arrays

        Returns:
            JSON-serializable fragments dictionary
        """
        with Catchtime() as ser_timer:
            try:
                serializable_fragments = {}

                for fragment_name, fragment_data in fragments.items():
                    serializable_fragment = {}

                    # Convert numpy arrays to base64
                    for key, value in fragment_data.items():
                        if isinstance(value, np.ndarray):
                            # Store array metadata for reconstruction
                            array_bytes = value.tobytes()
                            encoded_array = base64.b64encode(array_bytes).decode(
                                "utf-8"
                            )

                            serializable_fragment[key] = {
                                "data": encoded_array,
                                "dtype": str(value.dtype),
                                "shape": value.shape,
                            }
                        else:
                            # Keep other values unchanged
                            serializable_fragment[key] = value

                    serializable_fragments[fragment_name] = serializable_fragment

                debug(
                    f"Serialized {len(fragments)} fragments for JSON transmission",
                    self._message_logger,
                )

                # Record serialization timing
                self.performance_metrics["serialization_times"].append(ser_timer.ms)
                return serializable_fragments

            except Exception as e:
                error(
                    f"Error serializing fragments for JSON: {e}", self._message_logger
                )
                return {}

    async def process_frame_to_fragments(
        self, frame_data: Dict[str, Any]
    ) -> Optional[Dict]:
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

    async def _handle_pipe_command(self, pipe_in):
        """Handle single pipe command (extracted for reuse in sync loop)."""
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
                        f"{self.device_name} - Processing frame to fragments",
                        self._message_logger,
                    )
                    frame_data = data[1]
                    result = await self.process_frame_to_fragments(frame_data)
                    pipe_in.send(result is not None)
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

    async def _sync_grid_loop(self, pipe_in, sync_hz, sync_phase_ns, sync_overrun_mode):
        """Grid-synchronized frame capture loop.

        All cameras sync to same time grid for simultaneous capture.
        """
        period_ns = int(round(1_000_000_000 / sync_hz))
        k = 0

        # Calculate first grid point
        n0 = now_ns()
        next_ns = ((n0 - sync_phase_ns) // period_ns + 1) * period_ns + sync_phase_ns

        info(
            f"{self.device_name} - Starting SYNC mode @ {sync_hz}Hz, phase={sync_phase_ns}ns, overrun={sync_overrun_mode}",
            self._message_logger,
        )

        while True:
            # Sleep until grid point (with pipe checking)
            target_ns = next_ns
            while now_ns() < target_ns:
                if pipe_in.poll(0.0001):
                    await self._handle_pipe_command(pipe_in)
                await asyncio.sleep(
                    0.0001
                )  # Essential to prevent busy-waiting and high CPU usage

            # TICK at grid point
            t_ns = now_ns()

            # Capture frame if camera started
            if self.state == CameraState.STARTED:
                frames = await self.grab_frames_from_camera()
                if frames:
                    # Add sync metadata
                    # frames['sync_tick'] = k
                    # frames['sync_grid_ns'] = next_ns
                    # frames['sync_id'] = next_ns // 1_000_000  # ms for JSON
                    # frames['sync_actual_ns'] = t_ns
                    # frames['sync_drift_us'] = (t_ns - next_ns) // 1000
                    self.last_frame = frames

                    # Log significant drift
                    drift_us = abs(t_ns - next_ns) // 1000
                    if drift_us > 1000:  # > 1ms
                        debug(
                            f"{self.device_name} - Tick {k}: drift {drift_us}us",
                            self._message_logger,
                        )

            # Advance to next grid
            k += 1
            next_ns += period_ns

            # Handle overrun
            n = now_ns()
            if n > next_ns:
                if sync_overrun_mode == "skip_one":
                    missed_ticks = (next_ns - n) // period_ns + 1
                    debug(
                        f"{self.device_name} - Overrun: skipping {missed_ticks} tick(s)",
                        self._message_logger,
                    )
                    next_ns = (
                        (n - sync_phase_ns) // period_ns + 1
                    ) * period_ns + sync_phase_ns
                    k = (next_ns - sync_phase_ns) // period_ns
                elif sync_overrun_mode == "skip_all":
                    missed = max(0, (n - next_ns + period_ns - 1) // period_ns)
                    next_ns += missed * period_ns
                    k += missed
                    if n >= next_ns:
                        next_ns += period_ns
                        k += 1

    async def _autonomous_loop(self, pipe_in):
        """Autonomous frame generation loop (fallback mode)."""
        start_time = asyncio.get_event_loop().time()
        frame_grabbed = False

        info(
            f"{self.device_name} - Starting AUTONOMOUS mode @ {self.fps}Hz",
            self._message_logger,
        )

        while True:
            # Check for pipe commands
            if pipe_in.poll(0.0001):
                await self._handle_pipe_command(pipe_in)

            # Continuous frame generation when started
            if self.state == CameraState.STARTED:
                current_time = asyncio.get_event_loop().time()

                # Reset frame_grabbed flag based on FPS
                frame_interval = 1.0 / self.fps
                if current_time - start_time >= frame_interval:
                    frame_grabbed = False
                    start_time = current_time

                if not frame_grabbed:
                    frames = await self.grab_frames_from_camera()
                    if frames is not None:
                        frame_grabbed = True
                        self.last_frame = frames

            # Sleep based on FPS to prevent excessive CPU usage
            # For 30 FPS: 1/30 = 0.0333s, use 1/10 of that for responsiveness
            await asyncio.sleep(1.0 / (self.fps * 10))

    async def _async_run(self, pipe_in):
        """Main async worker loop handling pipe commands and frame processing."""
        # Create local logger for this process
        self._message_logger = MessageLogger(
            filename=f"temp/virtual_pepper_camera_worker_{self.camera_id}.log",
            core=12,
            debug=False,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=10,
            colors=False,
        )

        debug(
            f"{self.device_name} - Virtual PepperCamera worker started",
            self._message_logger,
        )

        # Determine sync mode from pipeline config
        sync_enabled = (
            self.pipeline_config.get("sync_enabled", True)
            if self.pipeline_config
            else True
        )
        sync_hz = self.fps
        sync_phase_ns = (
            self.pipeline_config.get("sync_phase_ns", 0) if self.pipeline_config else 0
        )
        sync_overrun_mode = (
            self.pipeline_config.get("sync_overrun_mode", "skip_one")
            if self.pipeline_config
            else "skip_one"
        )

        try:
            if sync_enabled:
                await self._sync_grid_loop(
                    pipe_in, sync_hz, sync_phase_ns, sync_overrun_mode
                )
            else:
                await self._autonomous_loop(pipe_in)
        except asyncio.CancelledError:
            info(f"{self.device_name} - Task was cancelled", self._message_logger)
        except Exception as e:
            error(f"{self.device_name} - Error in Worker: {e}", self._message_logger)
            import traceback

            error(f"Traceback:\n{traceback.format_exc()}", self._message_logger)
        finally:
            info(
                f"{self.device_name} - Virtual PepperCamera worker has shut down",
                self._message_logger,
            )


class VirtualPepperCameraConnector(GeneralCameraConnector):
    """Thread-safe connector for VirtualPepperCameraWorker.

    Provides synchronous API using pipe communication to worker process.
    """

    def __init__(
        self,
        camera_id: str = "virtual",
        core: int = 1,
        message_logger: Optional[MessageLogger] = None,
    ):
        """Create connector and start worker process.

        Args:
            camera_id (str): Identifier for this virtual camera instance
            core (int): CPU core affinity for worker process
            message_logger (Optional[MessageLogger]): Message logger
        """
        self.camera_id = camera_id
        super().__init__(core=core, message_logger=message_logger)

    def _run(self, pipe_in, message_logger=None):
        """Run worker in separate process."""
        worker = VirtualPepperCameraWorker(
            camera_id=self.camera_id, message_logger=message_logger
        )
        asyncio.run(worker._run(pipe_in))

    # PEPPER-SPECIFIC METHODS (same as PepperCameraConnector)

    def fragment_and_serialize_frame(self, frame_data: dict):
        """Process frame into fragments and serialize."""
        with self._GeneralCameraConnector__lock:
            return super()._send_thru_pipe(
                self._pipe_out, ["FRAGMENT_AND_SERIALIZE", frame_data]
            )

    def get_last_fragments(self):
        """Get last processed fragments."""
        with self._GeneralCameraConnector__lock:
            return super()._send_thru_pipe(self._pipe_out, ["GET_LAST_FRAGMENTS"])
