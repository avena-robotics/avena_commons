"""PepperCamera EventListener for simplified camera processing dedicated to pepper detection.

Responsibility:
- Handle pepper camera events (capture_pepper_frame)
- Manage camera frame processing and fragmentation
- Send fragmented data to Pepper EventListener for processing
- Simplified workflow without QR/box detection logic

Exposes:
- Class `PepperCamera` (main pepper camera event listener)
"""

import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union
import json

import requests

from dotenv import load_dotenv

from avena_commons.camera.driver.general import CameraState
from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
    Result,
)
from avena_commons.pepper_camera.driver.pepper_camera_connector import PepperCameraConnector
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import MessageLogger, debug, error, info

load_dotenv(override=True)


class PepperCamera(EventListener):
    """
    Main PepperCamera EventListener for pepper-specific camera processing.

    Handles capture_pepper_frame events and manages the workflow:
    1. Capture frames from Orbec camera
    2. Fragment images into 4 parts
    3. Serialize fragments
    4. Send to Pepper EventListener for processing

    Attributes:
        camera_address (str): IP address of the camera
        camera_running (bool): Camera operation status
        latest_fragments: Last processed image fragments
        current_pepper_event: Current pepper processing event
    """

    def __init__(
        self,
        name: str,
        address: str,
        port: str,
        message_logger: MessageLogger | None = None,
        load_state: bool = False,
    ):
        """
        Initialize PepperCamera with necessary configuration and state.

        Args:
            name (str): Name of the pepper camera event listener
            address (str): IP address of the pepper camera event listener
            port (str): Port of the pepper camera event listener
            message_logger (MessageLogger | None): Logger for messages; default None
            load_state (bool): State loading flag (currently unused); default False

        Raises:
            ValueError: When required PEPPER_CAMERA_LISTENER_PORT or CAMERA_IP environment variable is missing
        """

        if not port:
            raise ValueError("Missing required PEPPER_CAMERA_LISTENER_PORT environment variable")

        self.check_local_data_frequency = 30  # Check local data every 30ms
        self.name = name

        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
        )
        
        self.__camera_config = self._configuration.get("camera_configuration", {})
        debug(f"Camera config: {self.__camera_config}", self._message_logger)
        
        # Get pipeline configuration for fragments (analogous to Camera EventListener)
        self.__pipeline_config = self._configuration.get("camera_pipeline", {})

        if self.__camera_config.get("camera_ip", None) is None:
            error(f"Missing CAMERA_IP configuration for pepper camera", self._message_logger)
            raise ValueError(f"Missing CAMERA_IP configuration for pepper camera")
        
        self.camera_address = self.__camera_config["camera_ip"]
        self._port = port
        self._address = address

        # Pepper-specific state management
        self.latest_fragments = None
        self.current_pepper_event = None

        # Performance metrics for image processing functions
        self.performance_metrics = {
            'frame_grab_times': [],
            'fragmentation_times': [],
            'serialization_times': [],
            'total_processing_times': [],
            'frames_processed': 0,
            'fragments_sent': 0,
            'start_time': datetime.now().isoformat(),
            'processing_errors': 0
        }

        debug(f"PepperCamera EventListener initialized for IP {self.camera_address}", self._message_logger)
        
        # Initialize PepperCamera connector with pipeline config
        self.camera = PepperCameraConnector(
            camera_ip=self.camera_address,
            core=self.__camera_config.get("core", 1),
            message_logger=self._message_logger
        )

        # Pass both camera and pipeline config to connector
        # full_config = {**self.__camera_config, "pipeline": self.__pipeline_config}

        # Pre-initialize camera (TODO: remove after performance tests)
        # self.camera.init(self.__camera_config)
        # self.camera.start()
        
        self._change_fsm_state(EventListenerState.INITIALIZING)

    async def on_initializing(self):
        """Method called during transition to INITIALIZING state.
        Component should establish connections, allocate resources etc."""
        # Exactly matching original Camera EventListener pattern: self.camera.init(self.__camera_config)
        # But PepperCamera needs pipeline config, so merge them
        full_config = {**self.__camera_config, "camera_pipeline": self.__pipeline_config}
        self.camera.init(full_config)

    async def on_starting(self):
        """Method called during transition to STARTING state.
        Component prepares for main operations."""
        self.camera.start()

    async def on_stopping(self):
        """Method called during transition to STOPPING state."""
        self.camera.stop()
        
        # Log performance metrics at shutdown
        self._log_performance_metrics()

    def _log_performance_metrics(self):
        """Log comprehensive performance metrics for image processing functions."""
        try:
            end_time = datetime.now().isoformat()
            
            # Calculate statistics
            metrics_summary = {
                'timestamp': end_time,
                'session_info': {
                    'start_time': self.performance_metrics['start_time'],
                    'end_time': end_time,
                    'camera_ip': self.camera_address,
                    'name': self.name,
                    'core': self.__camera_config.get("core", 1)
                },
                'processing_stats': {
                    'total_frames_processed': self.performance_metrics['frames_processed'],
                    'total_fragments_sent': self.performance_metrics['fragments_sent'],
                    'processing_errors': self.performance_metrics['processing_errors']
                },
                'timing_statistics': {}
            }
            
            # Process timing statistics
            for metric_name, times in self.performance_metrics.items():
                if isinstance(times, list) and times and metric_name.endswith('_times'):
                    stats = {
                        'count': len(times),
                        'avg_ms': sum(times) / len(times),
                        'min_ms': min(times),
                        'max_ms': max(times),
                        'total_ms': sum(times)
                    }
                    
                    # Calculate FPS/throughput for frame operations
                    if metric_name == 'frame_grab_times' and stats['avg_ms'] > 0:
                        stats['avg_fps'] = 1000.0 / stats['avg_ms']
                    
                    metrics_summary['timing_statistics'][metric_name] = stats
            
            # Create performance log file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"temp/performance_metrics_pepperCamera_{timestamp}.json"
            
            os.makedirs("temp", exist_ok=True)
            with open(log_filename, 'w') as f:
                json.dump(metrics_summary, f, indent=2)
            
            info(f"Performance metrics saved to {log_filename}", self._message_logger)
            
            # Log summary to main log
            if self.performance_metrics['frames_processed'] > 0:
                avg_total = sum(self.performance_metrics['total_processing_times']) / len(self.performance_metrics['total_processing_times']) if self.performance_metrics['total_processing_times'] else 0
                info(f"PERFORMANCE SUMMARY - Frames: {self.performance_metrics['frames_processed']}, Avg Total Time: {avg_total:.2f}ms", self._message_logger)
            
        except Exception as e:
            error(f"Error logging performance metrics: {e}", self._message_logger)
        
    def _clear_before_shutdown(self):
        """Clean resources before shutdown.
        
        Sets logger to None so other threads don't try to use it during shutdown process.
        """
        __logger = self._message_logger  # Save reference if needed
        # Set to None so other threads don't try to use it
        self._message_logger = None

    async def _analyze_event(self, event):
        """Analyze incoming events and handle pepper camera logic.

        Args:
            event: Event to process

        Returns:
            bool: True if event was processed correctly
        """

        match event.event_type:
            case _:
                if event.result is not None:
                    return True
                debug(f"Unknown event {event.event_type}", self._message_logger)
                return False

        return True

    async def _send_fragments_to_pepper_listener(self, fragments_data):
        """Send processed fragments to Pepper EventListener.

        Args:
            fragments_data (bytes): Serialized image fragments
            event (Event): Original pepper camera event
        """
        try:
            # Get pepper listener configuration from environment
            pepper_address = "http://127.0.0.1"
            pepper_port = "8001"

            if not pepper_address or not pepper_port:
                error("Missing PEPPER_LISTENER_ADDRESS or PEPPER_LISTENER_PORT environment variables", self._message_logger)
                return False

            # Send process_fragments event to Pepper EventListener with proper format
            event = Event(
                source="pepper_camera_autonomous_benchmark",  # Fixed name for PepperCamera Event
                source_port=8002,
                destination="pepper_autonomous_benchmark",  # Fixed name for Pepper EventListener
                destination_port=pepper_port,
                event_type="process_fragments",
                data={
                    "fragments": fragments_data,  # Already base64-encoded string
                    "timestamp": datetime.now().isoformat(),
                },
                to_be_processed=False,  # Changed to False for proper event processing
            )
            
            response = requests.post(f"{pepper_address}:{pepper_port}/event", json=event.to_dict())
            
            info(f"Sent process_fragments event to Pepper EventListener", self._message_logger)
            return True
            
        except Exception as e:
            error(f"Error sending fragments to Pepper EventListener: {e}", self._message_logger)
            return False

    async def _check_local_data(self):
        """
        Periodically checks and processes local camera data for pepper processing.

        Handles the main pepper camera workflow:
        1. Check camera state
        2. Grab frames when available  
        3. Process frames into fragments
        4. Send fragments to Pepper EventListener

        Raises:
            Exception: If an error occurs during data processing.
        """
        camera_state = self.camera.get_state()
        
        match camera_state:
            case CameraState.ERROR:
                self._change_fsm_state(EventListenerState.ON_ERROR)
                
            case CameraState.STARTED:
                # Grab frame from camera autonomously (no event needed)
                last_frame = self.camera.get_last_frame()

                if last_frame is not None:
                    debug(f"Got frame: color {last_frame['color'].shape}, depth {last_frame['depth'].shape}", self._message_logger)
                    
                    # Process frame to fragments with performance tracking
                    with Catchtime() as processing_time:
                        confirmed = self.camera.fragment_and_serialize_frame(last_frame)
                    
                    # Record total processing time
                    self.performance_metrics['total_processing_times'].append(processing_time.ms)
                    
                    if not confirmed:
                        error("Error in fragment_and_serialize_frame", self._message_logger)
                        self.performance_metrics['processing_errors'] += 1
                        self.camera.stop()
                        
                        self._change_fsm_state(EventListenerState.ON_ERROR)
                    else:
                        debug(f"Frame fragmentation initiated in {processing_time.ms:.2f}ms", self._message_logger)
                        self.performance_metrics['frames_processed'] += 1

                        fragments_data = self.camera.get_last_fragments()
                        
                        if fragments_data is not None:
                            debug(f"Got processed fragments: {len(fragments_data)}", self._message_logger)

                            # Send fragments to Pepper EventListener
                            fragments_sent = await self._send_fragments_to_pepper_listener(fragments_data)
                            
                            if fragments_sent:
                                debug(f"Successfully sent {len(fragments_data)} fragments to Pepper EventListener (autonomous)", self._message_logger)
                                self.performance_metrics['fragments_sent'] += len(fragments_data) if isinstance(fragments_data, dict) else 1
                            else:
                                error("Failed to send fragments to Pepper EventListener (autonomous)", self._message_logger)
                                self.performance_metrics['processing_errors'] += 1
                                
                            # Camera continues running - no stop/restart cycle needed
                            debug("Camera continues running for next frame", self._message_logger)
                        else:
                            error("No fragments data available after processing", self._message_logger)
                            self.performance_metrics['processing_errors'] += 1
                else:
                    # No frame available yet, keep trying
                    pass

            # case CameraState.RUNNING:
            #     # Get processed fragments
