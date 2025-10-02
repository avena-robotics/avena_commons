import asyncio
import time
import threading
import traceback
import os
import cv2
import numpy as np
from enum import Enum
from typing import Optional, Dict, List, Tuple, Any

from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
    debug,
    error,
    info,
)
from avena_commons.util.worker import Connector, Worker
from avena_commons.util.catchtime import Catchtime


class PepperState(Enum):
    """Stany pracy Pepper Vision Worker.
    
    Enum odzwierciedla cykl życia procesu pepper vision.
    """
    IDLE = 0           # idle
    INITIALIZING = 1   # init pepper vision
    INITIALIZED = 2    # init completed
    STARTING = 3       # start processing
    STARTED = 4        # ready for processing
    PROCESSING = 5     # processing fragments
    STOPPING = 6       # stop processing
    STOPPED = 7        # stopped
    ERROR = 255        # error


class PepperWorker(Worker):
    """Asynchroniczny worker obsługujący pepper vision processing.
    
    Worker process uruchamiany na dedykowanym core (domyślnie core 2)
    do przetwarzania fragmentów obrazu z pepper vision functions.
    """
    
    def __init__(self, message_logger: Optional[MessageLogger] = None):
        """Zainicjalizuj Pepper Vision Worker.
        
        Args:
            message_logger: Logger do komunikatów (zostanie utworzony lokalny).
        """
        self._message_logger = None  # Będzie utworzony lokalny w _async_run
        self.device_name = "PepperWorker"
        super().__init__(message_logger=None)
        self.state = PepperState.IDLE
        
        # Pepper vision configuration
        self.pepper_config = None
        self.fragment_to_section = {
            0: "top_left",
            1: "top_right", 
            2: "bottom_left",
            3: "bottom_right"
        }
        
        # Results storage
        self.last_result = None
        
    @property
    def state(self) -> PepperState:
        return self.__state

    @state.setter
    def state(self, value: PepperState) -> None:
        debug(f"{self.device_name} - State changed to {value.name}", self._message_logger)
        self.__state = value

    # EMBEDDED PEPPER VISION FUNCTIONS
    def create_pepper_config(self, nozzle_mask, section, pepper_type="big_pepper", reflective_nozzle=False):
        """Create pepper vision config"""
        image_center = (nozzle_mask.shape[1]//2, nozzle_mask.shape[0]//2)
        
        # Simple vectors based on section
        vectors_map = {
            "top_left": (-0.4279989873279, 0.9037792135506836),
            "top_right": (0.38107893052152586, 0.9245425077910534),
            "bottom_right": (-0.3124139550973251, 0.9499460619742821),
            "bottom_left": (0.4889248257678126, 0.8723259223179798)
        }
        vectors = vectors_map.get(section, (0.0, 1.0))
        
        config_dict = {
            "nozzle_vectors": vectors,
            "image_center": image_center,
            "section": section,
            "reflective_nozzle": reflective_nozzle,
            "pepper_mask_config": {
                "red_bottom_range": [[0, 140, 50], [30, 255, 255]],
                "red_top_range": [[150, 140, 50], [180, 255, 255]],
                "mask_de_noise_open_params": {"kernel": (5,5), "iterations": 1},
                "mask_de_noise_close_params": {"kernel": (10,10), "iterations": 1},
                "min_mask_area": 100
            },
            "pepper_presence_max_depth": 245,
            "hole_detection_config": {
                "gauss_blur_kernel_size": (3, 3),
                "clahe_params": {"clipLimit": 2.0, "tileGridSize": (8, 8)},
                "threshold_param": 0.5,
                "open_on_l_params": {"kernel": (5, 5), "iterations": 1},
                "open_on_center_params": {"kernel": (5, 5), "iterations": 2},
                "open_on_center_raw_params": {"kernel": (2, 2), "iterations": 1},
                "max_distance_from_center": 30,
                "close_params": {"kernel": (5, 5), "iterations": 1},
                "min_hole_area": 30
            },
            "if_pepper_is_filled_config": {
                "max_outer_diff": 10,
                "min_inner_zone_non_zero_perc": 0.5,
                "min_inner_to_outer_diff": 0
            }
        }
        return config_dict

    def create_simple_nozzle_mask(self, fragment_shape, section):
        """Create a simple nozzle mask for fragment"""
        h, w = fragment_shape[:2]
        nozzle_mask = np.zeros((h, w), dtype=np.uint8)
        
        # Create a simple circular mask in the center as placeholder
        center_x, center_y = w // 2, h // 2
        radius = min(w, h) // 6
        cv2.circle(nozzle_mask, (center_x, center_y), radius, 255, -1)
        
        return nozzle_mask

    def pepper_search(self, color_fragment, depth_fragment, nozzle_mask, params):
        """Main search function - simplified version for benchmark"""
        try:
            # Simulate real pepper vision processing with actual CV operations
            
            # 1. Pepper mask creation
            hsv_color = cv2.cvtColor(color_fragment, cv2.COLOR_BGR2HSV)
            pepper_config = params["pepper_mask_config"]
            
            lower_range_bottom = np.array(pepper_config["red_bottom_range"][0])
            upper_range_bottom = np.array(pepper_config["red_bottom_range"][1])
            lower_range_top = np.array(pepper_config["red_top_range"][0])
            upper_range_top = np.array(pepper_config["red_top_range"][1])
            
            mask_bottom = cv2.inRange(hsv_color, lower_range_bottom, upper_range_bottom)
            mask_top = cv2.inRange(hsv_color, lower_range_top, upper_range_top)
            pepper_mask = cv2.bitwise_or(mask_bottom, mask_top)
            
            # 2. Mask refinement with morphological operations
            kernel_open = np.ones(pepper_config["mask_de_noise_open_params"]["kernel"], np.uint8)
            kernel_close = np.ones(pepper_config["mask_de_noise_close_params"]["kernel"], np.uint8)
            
            pepper_mask = cv2.morphologyEx(pepper_mask, cv2.MORPH_OPEN, kernel_open, 
                                         iterations=pepper_config["mask_de_noise_open_params"]["iterations"])
            pepper_mask = cv2.morphologyEx(pepper_mask, cv2.MORPH_CLOSE, kernel_close,
                                         iterations=pepper_config["mask_de_noise_close_params"]["iterations"])
            
            # 3. Pepper presence from depth
            if np.max(pepper_mask) > 0:
                depth_mask = depth_fragment[pepper_mask == 255]
                depth_mask = depth_mask[depth_mask > 0]
                if len(depth_mask) > 0:
                    depth_mask_mean = np.mean(depth_mask)
                    pepper_presence = depth_mask_mean < params["pepper_presence_max_depth"]
                else:
                    pepper_presence = False
            else:
                pepper_presence = False
            
            # 4. Hole detection (simplified)
            if pepper_presence:
                # Convert to LAB and work with L channel
                lab_image = cv2.cvtColor(color_fragment, cv2.COLOR_BGR2HLS)
                _, l, _ = cv2.split(lab_image)
                
                # Apply Gaussian blur and CLAHE
                hole_config = params["hole_detection_config"]
                l_gauss = cv2.GaussianBlur(l, hole_config["gauss_blur_kernel_size"], 0)
                l_equHist = cv2.equalizeHist(l_gauss)
                
                clahe = cv2.createCLAHE(clipLimit=hole_config["clahe_params"]["clipLimit"], 
                                      tileGridSize=hole_config["clahe_params"]["tileGridSize"])
                l_clahe = clahe.apply(np.uint8(l_equHist))
                l_clahe[pepper_mask == 0] = 0
                
                # Thresholding
                l_non_zero = l_clahe[l_clahe > 0]
                if len(l_non_zero) > 0:
                    l_non_zero_normalized = cv2.normalize(l_non_zero, None, 0, 255, cv2.NORM_MINMAX)
                    threshold_value = (((np.median(l_non_zero_normalized) * hole_config["threshold_param"]) / 255) * 
                                     np.max(l_non_zero)) + np.min(l_non_zero)
                    l_threshold = cv2.threshold(l_clahe, threshold_value, 255, cv2.THRESH_BINARY)[1]
                    
                    # Find hole contours
                    hole_contours, _ = cv2.findContours(l_threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    
                    # Check if hole found near center
                    image_center = params["image_center"]
                    hole_found = False
                    for cnt in hole_contours:
                        if cv2.contourArea(cnt) > hole_config["min_hole_area"]:
                            result = cv2.pointPolygonTest(cnt, image_center, True)
                            if abs(result) < hole_config["max_distance_from_center"]:
                                hole_found = True
                                break
                else:
                    hole_found = False
            else:
                hole_found = False
            
            # 5. Depth measurements for fill detection (simplified)
            is_filled = False
            if hole_found:
                # Create simple inner and outer zones
                h, w = depth_fragment.shape
                center_y, center_x = h//2, w//2
                
                # Inner zone (center circle)
                inner_mask = np.zeros_like(depth_fragment, dtype=np.uint8)
                cv2.circle(inner_mask, (center_x, center_y), min(h, w)//8, 255, -1)
                
                # Outer zone (ring around center)
                outer_mask = np.zeros_like(depth_fragment, dtype=np.uint8)
                cv2.circle(outer_mask, (center_x, center_y), min(h, w)//4, 255, -1)
                cv2.circle(outer_mask, (center_x, center_y), min(h, w)//6, 0, -1)
                
                # Measure depths
                inner_depths = depth_fragment[inner_mask == 255]
                outer_depths = depth_fragment[outer_mask == 255]
                
                inner_depths = inner_depths[inner_depths > 0]
                outer_depths = outer_depths[outer_depths > 0]
                
                if len(inner_depths) > 0 and len(outer_depths) > 0:
                    inner_median = np.median(inner_depths)
                    outer_median = np.median(outer_depths)
                    
                    # Check if filled
                    depth_diff = inner_median - outer_median
                    inner_perc = len(inner_depths) / np.count_nonzero(inner_mask)
                    
                    is_filled = (inner_perc > params["if_pepper_is_filled_config"]["min_inner_zone_non_zero_perc"] and 
                               depth_diff <= params["if_pepper_is_filled_config"]["min_inner_to_outer_diff"])
            
            # Simulate overflow detection
            overflow_detected = np.random.random() < 0.1  # 10% chance of overflow
            
            # Return results similar to real search function
            return {
                "search_state": pepper_presence and hole_found,
                "overflow_state": overflow_detected,
                "is_filled": is_filled,
                "pepper_presence": pepper_presence,
                "hole_found": hole_found,
                "success": True
            }
            
        except Exception as e:
            error(f"Pepper search error: {e}", self._message_logger)
            return {
                "search_state": False,
                "overflow_state": False,
                "is_filled": False,
                "pepper_presence": False,
                "hole_found": False,
                "success": False,
                "error": str(e)
            }

    async def process_fragments(self, fragments: Dict[str, Dict]) -> Dict:
        """Process list of image fragments with pepper vision.
        
        Args:
            fragments: Dict of fragment dicts with 'color', 'depth', 'fragment_id'

        Returns:
            Dict with processing results for each fragment
        """
        try:
            self.state = PepperState.PROCESSING
            
            with Catchtime() as processing_timer:
                results = {}
                
                for fragment_key, fragment_data in fragments.items():
                    fragment_id = fragment_data.get("fragment_id", fragment_key)
                    section = self.fragment_to_section.get(fragment_id, "top_left")
                    
                    try:
                        color_fragment = fragment_data["color"]
                        depth_fragment = fragment_data["depth"]
                        
                        # Create nozzle mask for this fragment
                        nozzle_mask = self.create_simple_nozzle_mask(color_fragment.shape, section)
                        
                        # Create parameters for pepper vision
                        params = self.create_pepper_config(nozzle_mask, section, "big_pepper", reflective_nozzle=False)
                        
                        # Execute pepper vision pipeline
                        with Catchtime() as fragment_timer:
                            fragment_result = self.pepper_search(color_fragment, depth_fragment, nozzle_mask, params)
                        
                        fragment_result["processing_time_ms"] = fragment_timer.ms
                        results[fragment_id] = fragment_result
                        
                        debug(f"Processed fragment {fragment_id} ({section}) in {fragment_timer.ms:.2f}ms", 
                                self._message_logger)
                                
                    except Exception as fragment_error:
                        error(f"Error processing fragment {fragment_id}: {fragment_error}", self._message_logger)
                        results[fragment_id] = {
                            "search_state": False,
                            "overflow_state": False,
                            "is_filled": False,
                            "success": False,
                            "error": str(fragment_error)
                        }
            
            total_time = processing_timer.ms
            debug(f"Processed {len(fragments)} fragments in {total_time:.2f}ms total", self._message_logger)

            # Store result
            self.last_result = {
                "results": results,
                "total_processing_time_ms": total_time,
                "fragments_count": 1,
                "success": True
            }
            
            self.state = PepperState.STARTED
            return self.last_result
            
        except Exception as e:
            error(f"Error in process_fragments: {e}", self._message_logger)
            self.state = PepperState.ERROR
            return {
                "results": {},
                "total_processing_time_ms": 0.0,
                "fragments_count": 0,
                "success": False,
                "error": str(e)
            }

    async def init_pepper(self, pepper_settings: dict):
        """Initialize pepper vision worker with settings.
        
        Args:
            pepper_settings: Configuration dict for pepper vision
            
        Returns:
            bool: True if initialization successful
        """
        try:
            self.state = PepperState.INITIALIZING
            debug(f"{self.device_name} - Initializing pepper vision", self._message_logger)
            
            self.pepper_config = pepper_settings
            
            self.state = PepperState.INITIALIZED
            debug(f"{self.device_name} - Pepper vision initialized", self._message_logger)
            return True
            
        except Exception as e:
            error(f"{self.device_name} - Init failed: {e}", self._message_logger)
            self.state = PepperState.ERROR
            return False

    async def start_pepper(self):
        """Start pepper vision processing.
        
        Returns:
            bool: True if start successful
        """
        try:
            self.state = PepperState.STARTING
            debug(f"{self.device_name} - Starting pepper vision", self._message_logger)
            
            self.last_result = None
            
            self.state = PepperState.STARTED
            debug(f"{self.device_name} - Pepper vision started", self._message_logger)
            return True
            
        except Exception as e:
            error(f"{self.device_name} - Start failed: {e}", self._message_logger)
            self.state = PepperState.ERROR
            return False

    async def stop_pepper(self):
        """Stop pepper vision processing.
        
        Returns:
            bool: True if stop successful
        """
        try:
            self.state = PepperState.STOPPING
            debug(f"{self.device_name} - Stopping pepper vision", self._message_logger)
            
            self.last_result = None
            
            self.state = PepperState.STOPPED
            debug(f"{self.device_name} - Pepper vision stopped", self._message_logger)
            return True
            
        except Exception as e:
            error(f"{self.device_name} - Stop failed: {e}", self._message_logger)
            self.state = PepperState.ERROR
            return False

    def _run(self, pipe_in):
        """Synchroniczna pętla pipe"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_run(pipe_in))
        finally:
            loop.close()

    async def _async_run(self, pipe_in):
        """Główna pętla pepper worker ASYNCHRONICZNA nasłuchująca komend przez pipe.
        
        Args:
            pipe_in: Dwukierunkowy kanał komunikacji (multiprocessing Pipe)
        """
        # Utwórz lokalny logger dla tego procesu
        self._message_logger = MessageLogger(
            filename=f"temp/pepper_worker.log",
            debug=True,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=10,
            colors=False,
        )

        debug(f"{self.device_name} - Worker started with local logger on PID: {os.getpid()}", 
              self._message_logger)
        
        try:
            while True:                
                if pipe_in.poll(0.0001):
                    data = pipe_in.recv()
                    response = None
                    
                    match data[0]:
                        case "PEPPER_INIT":
                            try:
                                debug(f"{self.device_name} - Received PEPPER_INIT: {data[1]}", 
                                      self._message_logger)
                                result = await self.init_pepper(data[1])
                                pipe_in.send(result)
                            except Exception as e:
                                error(f"{self.device_name} - Error in PEPPER_INIT: {e}", 
                                      self._message_logger)
                                pipe_in.send(False)

                        case "PEPPER_START":
                            try:
                                debug(f"{self.device_name} - Starting pepper processing", 
                                      self._message_logger)
                                result = await self.start_pepper()
                                pipe_in.send(result)
                            except Exception as e:
                                error(f"{self.device_name} - Error starting pepper: {e}", 
                                      self._message_logger)
                                pipe_in.send(False)

                        case "PEPPER_STOP":
                            try:
                                debug(f"{self.device_name} - Stopping pepper processing", 
                                      self._message_logger)
                                result = await self.stop_pepper()
                                pipe_in.send(result)
                            except Exception as e:
                                error(f"{self.device_name} - Error stopping pepper: {e}", 
                                      self._message_logger)
                                pipe_in.send(False)

                        case "GET_STATE":
                            try:
                                state = self.state
                                pipe_in.send(state)
                            except Exception as e:
                                error(f"{self.device_name} - Error getting state: {e}", 
                                      self._message_logger)
                                pipe_in.send(None)

                        case "PROCESS_FRAGMENTS":
                            try:
                                debug(f"{self.device_name} - Received PROCESS_FRAGMENTS with {len(data[1])} fragments", 
                                      self._message_logger)
                                fragments = data[1]
                                result = await self.process_fragments(fragments)
                                pipe_in.send(result)
                            except Exception as e:
                                error(f"{self.device_name} - Error processing fragments: {e}", 
                                      self._message_logger)
                                pipe_in.send({
                                    "results": {},
                                    "success": False,
                                    "error": str(e)
                                })

                        case "GET_LAST_RESULT":
                            try:
                                pipe_in.send(self.last_result)
                                if self.last_result is not None:
                                    self.last_result = None  # wyczyść po wysłaniu
                            except Exception as e:
                                error(f"{self.device_name} - Error getting last result: {e}", 
                                      self._message_logger)
                                pipe_in.send(None)

                        case _:
                            error(f"{self.device_name} - Unknown command: {data[0]}", 
                                  self._message_logger)

                # Sleep krótki czas aby nie hamować CPU
                await asyncio.sleep(0.001)

        except asyncio.CancelledError:
            info(f"{self.device_name} - Task was cancelled", self._message_logger)
        except Exception as e:
            error(f"{self.device_name} - Error in Worker: {e}", self._message_logger)
            error(f"Traceback:\n{traceback.format_exc()}", self._message_logger)
        finally:
            info(f"{self.device_name} - Worker has shut down", self._message_logger)


class PepperConnector(Connector):
    """Wątkowo-bezpieczny łącznik do PepperWorker.
    
    Zapewnia synchroniczne API wykorzystujące wewnętrznie komunikację
    przez pipe do procesu pepper worker.
    """

    def __init__(self, core: int = 2, message_logger: Optional[MessageLogger] = None):
        """Utwórz pepper connector z dedykowanym core.
        
        Args:
            core: Numer rdzenia CPU dla pepper worker (domyślnie 2)
            message_logger: Zewnętrzny logger
        """
        self.__lock = threading.Lock()
        super().__init__(core=core, message_logger=message_logger)
        super()._connect()
        self._local_message_logger = message_logger
        
    def _run(self, pipe_in, message_logger=None):
        """Uruchom pepper worker w osobnym procesie."""
        worker = PepperWorker(message_logger=message_logger)
        worker._run(pipe_in)

    def init(self, configuration: dict = {}):
        """Zainicjalizuj pepper vision przekazując konfigurację.
        
        Args:
            configuration: Parametry inicjalizacji pepper vision
            
        Returns:
            bool: True jeśli inicjalizacja się powiodła
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["PEPPER_INIT", configuration])
            return value

    def start(self):
        """Rozpocznij przetwarzanie pepper vision.
        
        Returns:
            bool: True jeśli start się powiódł
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["PEPPER_START"])
            return value

    def stop(self):
        """Zatrzymaj przetwarzanie pepper vision.
        
        Returns:
            bool: True jeśli stop się powiódł
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["PEPPER_STOP"])
            return value

    def get_state(self):
        """Pobierz aktualny stan pepper worker.
        
        Returns:
            PepperState: Aktualny stan lub None
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["GET_STATE"])
            return value

    def process_fragments(self, fragments: list[Dict]) -> Dict:
        """Przetwórz fragmenty obrazu z pepper vision.
        
        Args:
            fragments: Lista fragmentów do przetworzenia
            
        Returns:
            Dict: Wyniki przetwarzania lub None
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["PROCESS_FRAGMENTS", fragments])
            return value

    def get_last_result(self):
        """Pobierz ostatni wynik przetwarzania.
        
        Returns:
            Dict: Wyniki przetwarzania lub None
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["GET_LAST_RESULT"])
            return value
