import asyncio
import base64
import os
import time
from enum import Enum

import cv2
import numpy as np
from dotenv import load_dotenv

from avena_commons.event_listener import Event, EventListener
from avena_commons.util.logger import MessageLogger, debug, error, info, warning

# Import pepper_vision jako moduł siostrzany
from ..pepper_vision import CameraDetectionState, PerlaSystemState, config, search


class CameraInitFSM(Enum):
    """FSM dla inicjalizacji kamer (wzór z TestEventServer)"""
    IDLE = 0           # Nie zainicjalizowane
    INIT_SENT = 1      # Wysłano camera_init
    INIT_RECEIVED = 2  # Otrzymano potwierdzenia camera_init
    START_SENT = 3     # Wysłano camera_start  
    CAMERAS_READY = 4  # Kamery gotowe do pracy

load_dotenv(override=True)


class Perla(EventListener):
    """
    Main logic class for handling events and managing the pepper detection system.
    Zawiera główną logikę pepper detection przeniesioną z projektu papryczki.
    """

    def __init__(
        self,
        name: str,
        address: str,
        port: str,
        message_logger: MessageLogger | None = None,
        do_not_load_state: bool = False,
    ):
        """
        Initializes the Perla with pepper detection capabilities.

        Args:
            message_logger (Optional[MessageLogger]): Logger for logging messages.
            do_not_load_state (bool): Flag to skip loading state.

        Raises:
            ValueError: If required environment variables are missing.
        """

        # NAJPIERW wywołaj EventListener.__init__() 
        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
            do_not_load_state=do_not_load_state,
        )

        # POTEM zainicjalizuj pepper detection (aby nie zostało nadpisane)
        self._init_pepper_detection()

    def _init_pepper_detection(self):
        """Inicjalizuje pepper detection state i konfigurację"""
        
        # Pepper detection state - główna logika systemu
        self._state = {
            # System pepper detection
            'system_state': PerlaSystemState.IDLE,
            'detection_enabled': False,
            'detection_start_time': None,
            
            # Stany kamer (numery 1-4)
            'camera_states': {
                1: CameraDetectionState.IDLE,
                2: CameraDetectionState.IDLE,
                3: CameraDetectionState.IDLE, 
                4: CameraDetectionState.IDLE,
            },
            
            # Wyniki z kamer
            'camera_results': {
                1: {'search_state': False, 'overflow_state': False, 'timestamp': None, 'debug': None},
                2: {'search_state': False, 'overflow_state': False, 'timestamp': None, 'debug': None},
                3: {'search_state': False, 'overflow_state': False, 'timestamp': None, 'debug': None},
                4: {'search_state': False, 'overflow_state': False, 'timestamp': None, 'debug': None},
            },
            
            # Statystyki
            'pepper_stats': {
                'total_frames_processed': 0,
                'peppers_found_count': 0,
                'overflow_detected_count': 0,
                'last_detection_time': None
            }
        }

        # Pepper detection configuration - rozszerz istniejącą konfigurację EventListener
        pepper_config = {
            # Mapowanie kamer na sekcje (zgodnie z papryczki)
            "camera_to_section": {
                1: "top_left",
                2: "top_right", 
                3: "bottom_left",
                4: "bottom_right"
            },
            
            # Logika biznesowa pepper detection
            "pepper_detection": {
                "min_cameras_for_success": 2,        # Minimum kamer które muszą znaleźć papryczką
                "timeout_seconds": 30,               # Timeout dla wyszukiwania
                "enable_overflow_detection": True,   # Czy włączyć detekcję overflow
                "pepper_type": "small_prime",        # Typ papryczki dla algorytmu
                "search_frequency_hz": 10,           # Częstotliwość przetwarzania frame'ów
                "reflective_nozzle": True            # Czy końcówka jest odbijająca
            },
            
            # Nozzle masks per kamera (będą ładowane dynamicznie)
            "nozzle_masks_paths": {
                1: "/home/avena/system_perla/resources/pepper_vision/nozzle_mask_camera1.png",
                2: "/home/avena/system_perla/resources/pepper_vision/nozzle_mask_camera2.png", 
                3: "/home/avena/system_perla/resources/pepper_vision/nozzle_mask_camera3.png",
                4: "/home/avena/system_perla/resources/pepper_vision/nozzle_mask_camera4.png"
            }
        }
        
        # Rozszerz istniejącą _configuration z EventListener
        if hasattr(self, '_configuration') and self._configuration:
            self._configuration.update(pepper_config)
        else:
            self._configuration = pepper_config

        # Cached pepper vision resources
        self._nozzle_masks = {}      # Załadowane maski
        self._pepper_params = {}     # Parametry pepper_vision per kamera
        
        # Camera initialization FSM (wzór z TestEventServer)
        self._camera_init_fsm = CameraInitFSM.IDLE
        self._cameras_config = {
            1: {"port": 8201, "ip": "192.168.1.100"},
            2: {"port": 8202, "ip": "192.168.1.101"}, 
            3: {"port": 8203, "ip": "192.168.1.102"},
            4: {"port": 8204, "ip": "192.168.1.103"}
        }
        self._camera_init_responses = set()  # Tracking odpowiedzi od kamer
        
        # Konfiguracja zapisywania ramek i wyników
        self._captures_config = {
            'enable_capture': True,                    # Czy zapisywać ramki i wyniki
            'capture_first_frames': True,             # Czy zapisywać pierwszą ramkę z każdej kamery
            'capture_results': True,                  # Czy zapisywać wyniki detekcji
            'base_directory': 'captures',             # Katalog główny
            'session_directory': None,                # Katalog sesji (tworzony dynamicznie)
        }
        
        # Tracking pierwszych ramek z każdej kamery
        self._first_frames_captured = {
            1: False, 2: False, 3: False, 4: False
        }
        
        # Auto-start pepper detection (sterowane przez .env)
        auto_start_env = os.getenv("PERLA_AUTO_START_DETECTION", "false").lower()
        self._auto_start_detection = auto_start_env in ("true", "1", "yes", "on")
        
        if self._auto_start_detection:
            info("AUTO-START: Pepper detection będzie uruchomiony automatycznie po stabilizacji serwera", 
                 message_logger=self._message_logger)
        else:
            debug("AUTO-START: Pepper detection wyłączony - uruchom ręcznie przez HTTP API", 
                  message_logger=self._message_logger)

    # MARK: PEPPER DETECTION METHODS (przeniesione z PerlaServer)
    
    def _create_session_directory(self) -> str:
        """Tworzy katalog sesji dla zapisywanych ramek i wyników"""
        try:
            if self._captures_config['session_directory'] is not None:
                return self._captures_config['session_directory']  # Już utworzony
            
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            session_dir = os.path.join(self._captures_config['base_directory'], f"session_{timestamp}")
            
            os.makedirs(session_dir, exist_ok=True)
            self._captures_config['session_directory'] = session_dir
            
            info(f"CAPTURE: Utworzono katalog sesji: {session_dir}", message_logger=self._message_logger)
            return session_dir
            
        except Exception as e:
            error(f"CAPTURE: Błąd tworzenia katalogu sesji: {e}", message_logger=self._message_logger)
            return None
    
    def _save_first_frame(self, rgb: np.ndarray, depth: np.ndarray, camera_number: int) -> bool:
        """Zapisuje pierwszą ramkę z kamery (RGB + Depth)"""
        try:
            if not self._captures_config['enable_capture'] or not self._captures_config['capture_first_frames']:
                return True  # Capture wyłączony
                
            if self._first_frames_captured.get(camera_number, True):
                return True  # Już zapisano pierwszą ramkę z tej kamery
                
            session_dir = self._create_session_directory()
            if session_dir is None:
                return False
            
            # Zapisz RGB jako JPEG
            rgb_filename = os.path.join(session_dir, f"camera{camera_number}_first_rgb.jpg")
            cv2.imwrite(rgb_filename, rgb)
            
            # Zapisz Depth jako PNG (16-bit)
            depth_filename = os.path.join(session_dir, f"camera{camera_number}_first_depth.png")
            cv2.imwrite(depth_filename, depth)
            
            # Oznacz jako zapisane
            self._first_frames_captured[camera_number] = True
            
            info(f"CAPTURE: Zapisano pierwszą ramkę z kamery {camera_number}: {rgb_filename}, {depth_filename}", 
                 message_logger=self._message_logger)
            return True
            
        except Exception as e:
            error(f"CAPTURE: Błąd zapisywania pierwszej ramki z kamery {camera_number}: {e}", 
                  message_logger=self._message_logger)
            return False
    
    def _save_detection_results(self) -> bool:
        """Zapisuje aktualny stan wyników detekcji do JSON"""
        try:
            if not self._captures_config['enable_capture'] or not self._captures_config['capture_results']:
                return True  # Capture wyłączony
                
            session_dir = self._create_session_directory()
            if session_dir is None:
                return False
            
            # Przygotuj dane do zapisu
            results_data = {
                'timestamp': time.time(),
                'session_info': {
                    'system_state': self._state['system_state'].name,
                    'detection_enabled': self._state['detection_enabled'],
                    'detection_start_time': self._state['detection_start_time'],
                },
                'camera_states': {str(k): v.name for k, v in self._state['camera_states'].items()},
                'camera_results': {},
                'pepper_stats': self._state['pepper_stats'].copy(),
                'first_frames_captured': self._first_frames_captured.copy()
            }
            
            # Skopiuj wyniki kamer (bez debug info - może być duża)
            for cam_num, result in self._state['camera_results'].items():
                results_data['camera_results'][str(cam_num)] = {
                    'search_state': result['search_state'],
                    'overflow_state': result['overflow_state'],
                    'timestamp': result['timestamp'],
                    'debug_available': result['debug'] is not None
                }
            
            # Zapisz do pliku
            results_filename = os.path.join(session_dir, 'results.json')
            import json
            with open(results_filename, 'w', encoding='utf-8') as f:
                json.dump(results_data, f, indent=2, ensure_ascii=False)
            
            debug(f"CAPTURE: Zapisano wyniki detekcji: {results_filename}", message_logger=self._message_logger)
            return True
            
        except Exception as e:
            error(f"CAPTURE: Błąd zapisywania wyników detekcji: {e}", message_logger=self._message_logger)
            return False

    def _extract_camera_number(self, source: str) -> int:
        """Ekstraktuje numer kamery z source (np. 'camera1' -> 1)"""
        try:
            return int(source.replace("camera", ""))
        except ValueError:
            warning(f"Nie można wyekstraktować numeru kamery z: {source}", 
                   message_logger=self._message_logger)
            return None

    def _deserialize_frame(self, frame_data: dict) -> tuple:
        """Deserializuje dane frame'a z base64 do numpy arrays (RGB, Depth)"""
        try:
            # Dekoduj color (JPEG)
            color_bytes = base64.b64decode(frame_data.get("color", ""))
            color_array = np.frombuffer(color_bytes, dtype=np.uint8)
            rgb_image = cv2.imdecode(color_array, cv2.IMREAD_COLOR)
            
            # Dekoduj depth (PNG)  
            depth_bytes = base64.b64decode(frame_data.get("depth", ""))
            depth_array = np.frombuffer(depth_bytes, dtype=np.uint8)
            depth_image = cv2.imdecode(depth_array, cv2.IMREAD_UNCHANGED)
            
            return rgb_image, depth_image
            
        except Exception as e:
            error(f"Błąd deserializacji frame'a: {e}", message_logger=self._message_logger)
            return None, None

    def _load_nozzle_mask(self, camera_number: int) -> np.ndarray:
        """Ładuje maskę nozzle dla danej kamery"""
        if camera_number in self._nozzle_masks:
            return self._nozzle_masks[camera_number]
            
        try:
            mask_path = self._configuration["nozzle_masks_paths"].get(camera_number)
            if not mask_path or not os.path.exists(mask_path):
                warning(f"Nie znaleziono maski nozzle dla kamery {camera_number}: {mask_path}", 
                       message_logger=self._message_logger)
                # Tworzę dummy maskę jako fallback
                dummy_mask = np.zeros((400, 640), dtype=np.uint8)  
                cv2.circle(dummy_mask, (320, 200), 50, 255, -1)  # Okrągła maska w centrum
                self._nozzle_masks[camera_number] = dummy_mask
                return dummy_mask
                
            # Wczytaj maskę z pliku
            mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
            self._nozzle_masks[camera_number] = mask
            info(f"Załadowano maskę nozzle dla kamery {camera_number}: {mask.shape}", 
                 message_logger=self._message_logger)
            return mask
            
        except Exception as e:
            error(f"Błąd ładowania maski nozzle dla kamery {camera_number}: {e}", 
                  message_logger=self._message_logger)
            return None

    def _get_pepper_params(self, camera_number: int) -> dict:
        """Pobiera parametry pepper_vision dla danej kamery"""
        if camera_number in self._pepper_params:
            return self._pepper_params[camera_number]
            
        try:
            nozzle_mask = self._load_nozzle_mask(camera_number)
            if nozzle_mask is None:
                return None
                
            section = self._configuration["camera_to_section"].get(camera_number, "top_left")
            pepper_type = self._configuration["pepper_detection"]["pepper_type"]
            reflective_nozzle = self._configuration["pepper_detection"]["reflective_nozzle"]
            
            # Wywołaj config z pepper_vision
            params = config(nozzle_mask, section, pepper_type, reflective_nozzle)
            self._pepper_params[camera_number] = params
            
            debug(f"Utworzono parametry pepper_vision dla kamery {camera_number}, sekcja: {section}", 
                  message_logger=self._message_logger)
            return params
            
        except Exception as e:
            error(f"Błąd tworzenia parametrów pepper_vision dla kamery {camera_number}: {e}", 
                  message_logger=self._message_logger)
            return None

    async def _process_pepper_detection(self, rgb: np.ndarray, depth: np.ndarray, camera_number: int) -> dict:
        """Wykonuje wyszukiwanie papryczki dla danej klatki z kamery"""
        try:
            nozzle_mask = self._load_nozzle_mask(camera_number)
            params = self._get_pepper_params(camera_number)
            
            if nozzle_mask is None or params is None:
                return {
                    'success': False,
                    'error': 'Brak maski lub parametrów',
                    'camera_number': camera_number
                }
            
            # Wywołaj pepper_vision.search()
            result = search(rgb, depth, nozzle_mask, params)
            
            # result to tupla: (search_state, overflow_state, ..., debug)
            search_state = result[0]
            overflow_state = result[1] 
            debug_info = result[-1]
            
            # Aktualizuj statystyki
            self._state['pepper_stats']['total_frames_processed'] += 1
            if search_state:
                self._state['pepper_stats']['peppers_found_count'] += 1
            if overflow_state:
                self._state['pepper_stats']['overflow_detected_count'] += 1
                
            return {
                'success': True,
                'search_state': search_state,
                'overflow_state': overflow_state,
                'camera_number': camera_number,
                'timestamp': time.time(),
                'debug': debug_info
            }
            
        except Exception as e:
            error(f"Błąd pepper detection dla kamery {camera_number}: {e}", 
                  message_logger=self._message_logger)
            return {
                'success': False,
                'error': str(e),
                'camera_number': camera_number
            }

    def _log_state_change(self, camera_number=None, old_state=None, new_state=None):
        """Loguje zmiany stanów (zgodnie z architekturą papryczki)"""
        if camera_number:
            info(f"Camera {camera_number}: {old_state.name} → {new_state.name}", 
                 message_logger=self._message_logger)
        else:
            info(f"System: {old_state.name} → {new_state.name}", 
                 message_logger=self._message_logger)

    def _update_camera_state(self, camera_number: int, new_state: CameraDetectionState):
        """Aktualizuje stan kamery z logowaniem"""
        old_state = self._state['camera_states'][camera_number]
        if old_state != new_state:
            self._state['camera_states'][camera_number] = new_state
            self._log_state_change(camera_number, old_state, new_state)

    def _update_system_state(self, new_state: PerlaSystemState):
        """Aktualizuje stan systemu z logowaniem"""
        old_state = self._state['system_state']
        if old_state != new_state:
            self._state['system_state'] = new_state
            self._log_state_change(None, old_state, new_state)

    def _evaluate_system_state(self):
        """Ocenia globalny stan systemu na podstawie stanów kamer (analogia do papryczki)"""
        camera_states = list(self._state['camera_states'].values())
        
        # Zlicz kamery w różnych stanach
        ready_count = sum(1 for s in camera_states if s == CameraDetectionState.READY)
        found_count = sum(1 for s in camera_states if s == CameraDetectionState.PEPPER_FOUND)
        search_count = sum(1 for s in camera_states if s == CameraDetectionState.SEARCH)
        error_count = sum(1 for s in camera_states if s == CameraDetectionState.ERROR)
        overflow_count = sum(1 for s in camera_states if s == CameraDetectionState.OVERFLOW_DETECTED)
        
        min_required = self._configuration["pepper_detection"]["min_cameras_for_success"]
        
        # Logika stanów (zgodnie z papryczki)
        if error_count > 0:
            new_state = PerlaSystemState.ERROR
        elif overflow_count > 0:
            new_state = PerlaSystemState.ERROR  # Overflow traktujemy jako błąd
        elif (ready_count + found_count) >= min_required:
            new_state = PerlaSystemState.PEPPERS_READY
        elif search_count > 0:
            new_state = PerlaSystemState.DETECTION_ACTIVE
        else:
            new_state = PerlaSystemState.IDLE
            
        self._update_system_state(new_state)

    async def _handle_camera_frame(self, event: Event) -> bool:
        """Obsługuje event camera_frame - główna logika pepper detection"""
        if not self._state['detection_enabled']:
            return True  # Detection wyłączony, ignoruj frame
            
        try:
            camera_number = self._extract_camera_number(event.source)
            if camera_number is None:
                return False
                
            frame_data = event.data
            rgb, depth = self._deserialize_frame(frame_data)
            
            if rgb is None or depth is None:
                error(f"Nie udało się zdekodować frame'a z kamery {camera_number}", 
                      message_logger=self._message_logger)
                self._update_camera_state(camera_number, CameraDetectionState.ERROR)
                return False
            
            debug(f"Przetwarzanie frame'a z kamery {camera_number}: RGB {rgb.shape}, Depth {depth.shape}", 
                  message_logger=self._message_logger)
            
            # NOWE: Zapisz pierwszą ramkę z każdej kamery (dla konfiguracji)
            self._save_first_frame(rgb, depth, camera_number)
            
            # Ustaw stan kamery na SEARCH jeśli nie jest aktywna
            if self._state['camera_states'][camera_number] == CameraDetectionState.IDLE:
                self._update_camera_state(camera_number, CameraDetectionState.SEARCH)
            
            # Wykonaj pepper detection
            result = await self._process_pepper_detection(rgb, depth, camera_number)
            
            if result['success']:
                # Zapisz wyniki
                self._state['camera_results'][camera_number] = {
                    'search_state': result['search_state'],
                    'overflow_state': result['overflow_state'], 
                    'timestamp': result['timestamp'],
                    'debug': result['debug']
                }
                
                # Aktualizuj stan kamery na podstawie wyników
                if result['overflow_state']:
                    self._update_camera_state(camera_number, CameraDetectionState.OVERFLOW_DETECTED)
                elif result['search_state']:
                    self._update_camera_state(camera_number, CameraDetectionState.PEPPER_FOUND)
                    self._update_camera_state(camera_number, CameraDetectionState.READY)
                else:
                    self._update_camera_state(camera_number, CameraDetectionState.NO_PEPPER)
                
                # Oceń globalny stan systemu
                self._evaluate_system_state()
                
                # NOWE: Zapisz aktualne wyniki detekcji
                self._save_detection_results()
                
                info(f"Pepper detection kamera {camera_number}: papryczka={result['search_state']}, overflow={result['overflow_state']}", 
                     message_logger=self._message_logger)
            else:
                error(f"Pepper detection błąd kamera {camera_number}: {result.get('error', 'nieznany')}", 
                      message_logger=self._message_logger)
                self._update_camera_state(camera_number, CameraDetectionState.ERROR)
            
            return True
            
        except Exception as e:
            error(f"Błąd obsługi camera_frame: {e}", message_logger=self._message_logger)
            return False

    async def _start_pepper_detection(self, event: Event) -> bool:
        """Uruchamia pepper detection"""
        try:
            if self._state['detection_enabled']:
                warning("Pepper detection już włączony", message_logger=self._message_logger)
                return True
                
            info("Uruchamianie pepper detection...", message_logger=self._message_logger)
            
            # NOWE: Rozpocznij inicjalizację kamer (FSM)
            if self._camera_init_fsm == CameraInitFSM.IDLE:
                info("Rozpoczynam inicjalizację kamer...", message_logger=self._message_logger)
                self._camera_init_fsm = CameraInitFSM.IDLE  # Będzie obsłużone w _check_local_data
                self._camera_init_responses.clear()
            
            # Resetuj stany
            for camera_num in range(1, 5):
                self._update_camera_state(camera_num, CameraDetectionState.IDLE)
                self._state['camera_results'][camera_num] = {
                    'search_state': False, 'overflow_state': False, 
                    'timestamp': None, 'debug': None
                }
            
            # Resetuj statystyki
            self._state['pepper_stats'] = {
                'total_frames_processed': 0,
                'peppers_found_count': 0,
                'overflow_detected_count': 0,
                'last_detection_time': None
            }
            
            # NOWE: Resetuj tracking pierwszych ramek i utwórz nową sesję
            self._first_frames_captured = {1: False, 2: False, 3: False, 4: False}
            self._captures_config['session_directory'] = None  # Wymusi utworzenie nowej sesji
            
            self._state['detection_enabled'] = True
            self._state['detection_start_time'] = time.time()
            self._update_system_state(PerlaSystemState.DETECTION_START)
            
            info("Pepper detection uruchomiony pomyślnie", message_logger=self._message_logger)
            return True
            
        except Exception as e:
            error(f"Błąd uruchamiania pepper detection: {e}", message_logger=self._message_logger)
            return False

    async def _stop_pepper_detection(self, event: Event) -> bool:
        """Zatrzymuje pepper detection"""
        try:
            if not self._state['detection_enabled']:
                warning("Pepper detection już wyłączony", message_logger=self._message_logger)
                return True
                
            info("Zatrzymywanie pepper detection...", message_logger=self._message_logger)
            
            # NOWE: Zatrzymaj kamery przed wyłączeniem detekcji
            await self._stop_cameras()
            
            # Zapisz wyniki końcowe
            detection_duration = time.time() - self._state['detection_start_time'] if self._state['detection_start_time'] else 0
            stats = self._state['pepper_stats']
            
            info(f"Podsumowanie pepper detection - czas: {detection_duration:.2f}s, "
                 f"frame'ów: {stats['total_frames_processed']}, "
                 f"papryczek: {stats['peppers_found_count']}, "
                 f"overflow: {stats['overflow_detected_count']}", 
                 message_logger=self._message_logger)
            
            # Wyłącz system
            self._state['detection_enabled'] = False
            self._state['detection_start_time'] = None
            
            # Ustaw wszystkie kamery w IDLE
            for camera_num in range(1, 5):
                self._update_camera_state(camera_num, CameraDetectionState.IDLE)
                
            self._update_system_state(PerlaSystemState.RESULTS_PROCESSED)
            # Po chwili przejdź do IDLE
            self._update_system_state(PerlaSystemState.IDLE)
            
            info("Pepper detection zatrzymany pomyślnie", message_logger=self._message_logger)
            return True
            
        except Exception as e:
            error(f"Błąd zatrzymywania pepper detection: {e}", message_logger=self._message_logger)
            return False

    async def _get_pepper_status(self, event: Event) -> dict:
        """Zwraca aktualny status pepper detection"""
        try:
            return {
                'system_state': self._state['system_state'].name,
                'detection_enabled': self._state['detection_enabled'],
                'camera_states': {k: v.name for k, v in self._state['camera_states'].items()},
                'camera_results': self._state['camera_results'],
                'pepper_stats': self._state['pepper_stats'],
                'detection_duration': time.time() - self._state['detection_start_time'] if self._state['detection_start_time'] else 0
            }
        except Exception as e:
            error(f"Błąd pobierania statusu pepper detection: {e}", message_logger=self._message_logger)
            return {'error': str(e)}

    # MARK: ANALYZE EVENT
    async def _analyze_event(self, event: Event) -> bool:
        """
        Analyzes and routes events to the appropriate handler based on their source.
        Główna logika pepper detection przeniesiona z PerlaServer.

        Args:
            event (Event): The event to analyze.

        Returns:
            bool: True if the event was handled successfully, False otherwise.
        """
        try:
            # Obsługa eventów z kamer - główna funkcjonalność
            if event.source.startswith("camera") and event.event_type == "camera_frame":
                return await self._handle_camera_frame(event)
                
            # Obsługa potwiedzeń inicjalizacji kamer (wzór z TestEventServer)
            elif event.source.startswith("camera") and event.event_type == "camera_init":
                return await self._handle_camera_init_response(event)
            elif event.source.startswith("camera") and event.event_type == "camera_start":
                return await self._handle_camera_start_response(event)
                
            # Obsługa eventów sterowania pepper detection
            elif event.event_type == "start_pepper_detection":
                return await self._start_pepper_detection(event)
            elif event.event_type == "stop_pepper_detection":
                return await self._stop_pepper_detection(event)
            elif event.event_type == "get_pepper_status":
                return await self._get_pepper_status(event)
                
            return True
            
        except Exception as e:
            error(f"Błąd analizy eventu: {e}", message_logger=self._message_logger)
            return False

    # MARK: CHECK LOCAL DATA
    async def _check_local_data(self):
        """
        Periodically checks and processes local data, including pepper detection monitoring.
        Obsługuje FSM inicjalizacji kamer (wzór z TestEventServer).

        Raises:
            Exception: If an error occurs during data processing.
        """
        try:
            # NOWE: Obsługa FSM inicjalizacji kamer (wzór z TestEventServer)
            await self._handle_camera_init_fsm()
            
            # Sprawdź timeout pepper detection
            if (self._state['detection_enabled'] and 
                self._state['detection_start_time'] and 
                time.time() - self._state['detection_start_time'] > self._configuration["pepper_detection"]["timeout_seconds"]):
                
                warning("Timeout pepper detection - zatrzymywanie...", message_logger=self._message_logger)
                await self._stop_pepper_detection(None)
                
        except Exception as e:
            error(f"Błąd sprawdzania danych lokalnych: {e}", message_logger=self._message_logger)
            
    # MARK: CAMERA MANAGEMENT (FSM - wzór z TestEventServer)
    
    async def _handle_camera_init_fsm(self):
        """Obsługuje FSM inicjalizacji kamer (wzór z TestEventServer)"""
        try:
            # OPCJONALNE: Auto-start gdy serwer się ustabilizuje
            if (self._camera_init_fsm == CameraInitFSM.IDLE and 
                not self._state.get('detection_enabled', False) and
                hasattr(self, '_auto_start_detection') and self._auto_start_detection):
                
                info("AUTO-START: Uruchamianie pepper detection po stabilizacji serwera...", message_logger=self._message_logger)
                await self._start_pepper_detection(None)
                self._auto_start_detection = False  # Auto-start tylko raz
                
            elif self._camera_init_fsm == CameraInitFSM.IDLE and self._state.get('detection_enabled', False):
                # Rozpocznij inicjalizację - wyślij camera_init do wszystkich kamer
                info("FSM: Wysyłanie camera_init do wszystkich kamer...", message_logger=self._message_logger)
                
                for camera_num, config in self._cameras_config.items():
                    try:
                        await self._event(
                            destination=f"camera{camera_num}",
                            destination_address="127.0.0.1",
                            destination_port=config["port"],
                            event_type="camera_init",
                            data={},
                            to_be_processed=False
                        )
                        debug(f"FSM: Wysłano camera_init do camera{camera_num} (port {config['port']})", 
                              message_logger=self._message_logger)
                        
                    except Exception as e:
                        error(f"FSM: Błąd wysyłania camera_init do camera{camera_num}: {e}", 
                              message_logger=self._message_logger)
                
                self._camera_init_fsm = CameraInitFSM.INIT_SENT
                self._camera_init_responses.clear()
                
            elif self._camera_init_fsm == CameraInitFSM.INIT_RECEIVED:
                # Wszyscy odpowiedzieli na camera_init, wyślij camera_start
                info("FSM: Wszyscy odpowiedzieli na camera_init, wysyłanie camera_start...", message_logger=self._message_logger)
                
                for camera_num, config in self._cameras_config.items():
                    try:
                        await self._event(
                            destination=f"camera{camera_num}",
                            destination_address="127.0.0.1",
                            destination_port=config["port"],
                            event_type="camera_start", 
                            data={},
                            to_be_processed=False
                        )
                        debug(f"FSM: Wysłano camera_start do camera{camera_num} (port {config['port']})", 
                              message_logger=self._message_logger)
                        
                    except Exception as e:
                        error(f"FSM: Błąd wysyłania camera_start do camera{camera_num}: {e}", 
                              message_logger=self._message_logger)
                
                self._camera_init_fsm = CameraInitFSM.START_SENT
                self._camera_init_responses.clear()
                
        except Exception as e:
            error(f"FSM: Błąd obsługi camera init FSM: {e}", message_logger=self._message_logger)
    
    async def _handle_camera_init_response(self, event: Event) -> bool:
        """Obsługuje odpowiedź camera_init od kamery (wzór z TestEventServer)"""
        try:
            camera_num = self._extract_camera_number(event.source)
            info(f"FSM: Otrzymano camera_init od camera{camera_num}", message_logger=self._message_logger)
            
            if self._camera_init_fsm == CameraInitFSM.INIT_SENT:
                self._camera_init_responses.add(camera_num)
                
                # Sprawdź czy wszystkie kamery odpowiedziały
                if len(self._camera_init_responses) >= len(self._cameras_config):
                    info("FSM: Wszystkie kamery odpowiedziały na camera_init", message_logger=self._message_logger)
                    self._camera_init_fsm = CameraInitFSM.INIT_RECEIVED
                    
            return True
            
        except Exception as e:
            error(f"FSM: Błąd obsługi camera_init response: {e}", message_logger=self._message_logger)
            return False
    
    async def _handle_camera_start_response(self, event: Event) -> bool:
        """Obsługuje odpowiedź camera_start od kamery (wzór z TestEventServer)"""
        try:
            camera_num = self._extract_camera_number(event.source)
            info(f"FSM: Otrzymano camera_start od camera{camera_num}", message_logger=self._message_logger)
            
            if self._camera_init_fsm == CameraInitFSM.START_SENT:
                self._camera_init_responses.add(camera_num)
                
                # Sprawdź czy wszystkie kamery odpowiedziały
                if len(self._camera_init_responses) >= len(self._cameras_config):
                    info("FSM: Wszystkie kamery gotowe - pepper detection może rozpocząć!", message_logger=self._message_logger)
                    self._camera_init_fsm = CameraInitFSM.CAMERAS_READY
                    
                    # Przejście do aktywnej detekcji
                    self._update_system_state(PerlaSystemState.DETECTION_ACTIVE)
                    
            return True
            
        except Exception as e:
            error(f"FSM: Błąd obsługi camera_start response: {e}", message_logger=self._message_logger)
            return False
             
    async def _stop_cameras(self):
        """Zatrzymuje wszystkie kamery i resetuje FSM inicjalizacji"""
        try:
            info("FSM: Zatrzymywanie kamer - resetuję FSM inicjalizacji...", message_logger=self._message_logger)
            
            # Reset FSM
            self._camera_init_fsm = CameraInitFSM.IDLE
            self._camera_init_responses.clear()
            
            # Kamery CameraServer nie mają explicite eventu "camera_stop"
            # Pipeline zostanie zatrzymany gdy nie będą przychodzić eventy detection
            # Lub można dodać event camera_stop do CameraServer w przyszłości
            
            info("FSM: Kamery zostaną zatrzymane przez brak eventów pepper detection", 
                 message_logger=self._message_logger)
            
        except Exception as e:
            error(f"FSM: Błąd zatrzymywania kamer: {e}", message_logger=self._message_logger)
