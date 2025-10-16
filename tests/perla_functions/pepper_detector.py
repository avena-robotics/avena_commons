"""
PepperDetector - Dedykowany obiekt do detekcji papryczek

Odbiera już przygotowane fragmenty z różnych kamer i wykonuje na nich detekcję papryczek.
Pracuje na poziomie głównego systemu, agregując fragmenty z wielu kamer.
"""

import cv2
import numpy as np
import time
import base64
from typing import Dict, List, Optional, Any

from avena_commons.util.logger import MessageLogger, debug, error, info

from . import config, search
from .enums import CameraDetectionState


class PepperDetector:
    """
    Detektor papryczek na poziomie głównego systemu.

    Odpowiedzialny za:
    - Odbieranie już przygotowanych fragmentów z różnych kamer
    - Wykonywanie detekcji papryczek na fragmentach
    - Agregowanie wyników z wielu kamer/fragmentów
    - Zwracanie zagregowanych wyników detekcji
    """

    def __init__(
        self,
        pepper_config: Dict[str, Any],
        message_logger: Optional[MessageLogger] = None,
    ):
        """
        Inicjalizuje detektor papryczek dla głównego systemu.

        Args:
            pepper_config: Konfiguracja pepper detection
            message_logger: Logger komunikatów
        """
        self.pepper_config = pepper_config
        self._message_logger = message_logger

        # Cache dla parametrów pepper vision per kamera
        self._pepper_params_cache = {}

        # Statystyki
        self.stats = {
            "total_fragments_processed": 0,
            "peppers_found": 0,
            "overflow_detected": 0,
            "last_detection_time": None,
            "cameras_processed": set(),
        }

        debug(
            f"PepperDetector: Utworzono detektor głównego systemu",
            message_logger=self._message_logger,
        )

    def _get_pepper_vision_params(
        self, camera_number: int, mask_fragment: np.ndarray
    ) -> Dict[str, Any]:
        """
        Pobiera parametry pepper_vision dla danego fragmentu z kamery.

        Args:
            camera_number: Numer kamery
            mask_fragment: Maska fragmentu (już wycięta)

        Returns:
            Parametry pepper_vision dla fragmentu
        """
        try:
            # Sprawdź cache
            cache_key = camera_number
            if cache_key in self._pepper_params_cache:
                return self._pepper_params_cache[cache_key]

            # Utwórz parametry pepper_vision
            section = self.pepper_config["camera_to_section"].get(
                camera_number, "top_left"
            )
            pepper_type = self.pepper_config["pepper_detection"]["pepper_type"]
            reflective_nozzle = self.pepper_config["pepper_detection"][
                "reflective_nozzle"
            ]

            # Używamy maski fragmentu zamiast pełnej maski kamery
            params = config(mask_fragment, section, pepper_type, reflective_nozzle)

            # Cache parametry
            self._pepper_params_cache[cache_key] = params

            debug(
                f"PepperDetector: Utworzono parametry pepper_vision dla kamery {camera_number}, sekcja: {section}",
                message_logger=self._message_logger,
            )

            return params

        except Exception as e:
            error(
                f"PepperDetector: Błąd tworzenia parametrów pepper_vision dla kamery {camera_number}: {e}",
                message_logger=self._message_logger,
            )
            return None

    def deserialize_fragment(self, fragment_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deserializuje fragment otrzymany przez sieć z powrotem do numpy arrays.

        Args:
            fragment_data: Zserializowany fragment

        Returns:
            Fragment z numpy arrays
        """
        try:
            fragment = {
                "fragment_id": fragment_data.get("fragment_id"),
                "camera_number": fragment_data.get("camera_number"),
                "timestamp": fragment_data.get("timestamp"),
                "roi_config": fragment_data.get("roi_config"),
            }

            # Dekoduj color fragment
            if fragment_data.get("color_fragment"):
                color_bytes = base64.b64decode(fragment_data["color_fragment"])
                color_array = np.frombuffer(color_bytes, dtype=np.uint8)
                fragment["color_fragment"] = cv2.imdecode(color_array, cv2.IMREAD_COLOR)

            # Dekoduj depth fragment
            if fragment_data.get("depth_fragment"):
                depth_bytes = base64.b64decode(fragment_data["depth_fragment"])
                depth_array = np.frombuffer(depth_bytes, dtype=np.uint8)
                fragment["depth_fragment"] = cv2.imdecode(
                    depth_array, cv2.IMREAD_UNCHANGED
                )

            # Dekoduj mask fragment
            if fragment_data.get("mask_fragment"):
                mask_bytes = base64.b64decode(fragment_data["mask_fragment"])
                mask_array = np.frombuffer(mask_bytes, dtype=np.uint8)
                fragment["mask_fragment"] = cv2.imdecode(
                    mask_array, cv2.IMREAD_GRAYSCALE
                )

            return fragment

        except Exception as e:
            error(
                f"PepperDetector: Błąd deserializacji fragmentu: {e}",
                message_logger=self._message_logger,
            )
            return {}

    def detect_pepper_in_fragment(self, fragment: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wykonuje detekcję papryczki w pojedynczym fragmencie (już przygotowanym przez FragmentProcessor).

        Args:
            fragment: Fragment przygotowany przez FragmentProcessor zawierający:
                     - color_fragment, depth_fragment, mask_fragment (numpy arrays)
                     - camera_number, fragment_id, timestamp

        Returns:
            Wynik detekcji zawierający search_state, overflow_state i debug info
        """
        try:
            camera_number = fragment.get("camera_number")
            fragment_id = fragment.get("fragment_id")
            color_fragment = fragment.get("color_fragment")
            depth_fragment = fragment.get("depth_fragment")
            mask_fragment = fragment.get("mask_fragment")

            if (
                camera_number is None
                or color_fragment is None
                or depth_fragment is None
                or mask_fragment is None
            ):
                return {
                    "success": False,
                    "error": "Niepełne dane fragmentu",
                    "search_state": False,
                    "overflow_state": False,
                }

            # Pobierz parametry pepper_vision dla tego fragmentu
            params = self._get_pepper_vision_params(camera_number, mask_fragment)
            if params is None:
                return {
                    "success": False,
                    "error": "Brak parametrów pepper_vision",
                    "search_state": False,
                    "overflow_state": False,
                }

            # Wykonaj detekcję papryczki w fragmencie
            search_result = search(
                color_fragment, depth_fragment, mask_fragment, params
            )

            # search_result to tupla: (search_state, overflow_state, inner_zone_mask, outer_zone_mask,
            #                         overflow_mask, inner_zone_for_color, outer_overflow_mask,
            #                         outer_zone_median_start, overflow_bias, overflow_outer_bias, debug)
            search_state = search_result[0]
            overflow_state = search_result[1]
            debug_info = search_result[-1]

            # Aktualizuj statystyki
            self.stats["total_fragments_processed"] += 1
            self.stats["cameras_processed"].add(camera_number)

            if search_state:
                self.stats["peppers_found"] += 1
            if overflow_state:
                self.stats["overflow_detected"] += 1

            self.stats["last_detection_time"] = time.time()

            debug(
                f"PepperDetector: Fragment {fragment_id} z kamery {camera_number} - "
                f"papryczka: {search_state}, overflow: {overflow_state}",
                message_logger=self._message_logger,
            )

            return {
                "success": True,
                "search_state": search_state,
                "overflow_state": overflow_state,
                "inner_zone_mask": search_result[2],
                "outer_zone_mask": search_result[3],
                "overflow_mask": search_result[4],
                "inner_zone_for_color": search_result[5],
                "outer_overflow_mask": search_result[6],
                "outer_zone_median_start": search_result[7],
                "overflow_bias": search_result[8],
                "overflow_outer_bias": search_result[9],
                "debug": debug_info,
            }

        except Exception as e:
            error(
                f"PepperDetector: Błąd detekcji papryczki w fragmencie: {e}",
                message_logger=self._message_logger,
            )
            return {
                "success": False,
                "error": str(e),
                "search_state": False,
                "overflow_state": False,
            }

    def process_fragments_from_cameras(
        self, fragments_list: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Przetwarza fragmenty otrzymane z różnych kamer i agreguje wyniki.

        Args:
            fragments_list: Lista fragmentów z różnych kamer

        Returns:
            Zagregowane wyniki detekcji z wszystkich fragmentów/kamer
        """
        try:
            aggregated_results = {
                "total_fragments": len(fragments_list),
                "cameras_processed": set(),
                "fragment_results": [],
                "overall_search_state": False,
                "overall_overflow_state": False,
                "timestamp": time.time(),
            }

            debug(
                f"PepperDetector: Przetwarzanie {len(fragments_list)} fragmentów z różnych kamer",
                message_logger=self._message_logger,
            )

            # Przetwórz każdy fragment
            for fragment in fragments_list:
                try:
                    # Wykonaj detekcję na fragmencie
                    detection_result = self.detect_pepper_in_fragment(fragment)

                    # Dodaj wynik do zagregowanych rezultatów
                    fragment_result = {
                        "camera_number": fragment.get("camera_number"),
                        "fragment_id": fragment.get("fragment_id"),
                        "search_state": detection_result.get("search_state", False),
                        "overflow_state": detection_result.get("overflow_state", False),
                        "detection_success": detection_result.get("success", False),
                        "timestamp": fragment.get("timestamp"),
                    }

                    aggregated_results["fragment_results"].append(fragment_result)
                    aggregated_results["cameras_processed"].add(
                        fragment.get("camera_number")
                    )

                    # Aktualizuj globalne stany
                    if detection_result.get("search_state", False):
                        aggregated_results["overall_search_state"] = True

                    if detection_result.get("overflow_state", False):
                        aggregated_results["overall_overflow_state"] = True

                except Exception as fragment_error:
                    error(
                        f"PepperDetector: Błąd przetwarzania fragmentu: {fragment_error}",
                        message_logger=self._message_logger,
                    )
                    continue

            # Konwertuj set na listę dla JSON serialization
            aggregated_results["cameras_processed"] = list(
                aggregated_results["cameras_processed"]
            )

            info(
                f"PepperDetector: Przetworzono fragmenty z {len(aggregated_results['cameras_processed'])} kamer, "
                f"znaleziono papryczki: {aggregated_results['overall_search_state']}, "
                f"overflow: {aggregated_results['overall_overflow_state']}",
                message_logger=self._message_logger,
            )

            return aggregated_results

        except Exception as e:
            error(
                f"PepperDetector: Błąd przetwarzania fragmentów z kamer: {e}",
                message_logger=self._message_logger,
            )
            return {
                "total_fragments": 0,
                "cameras_processed": [],
                "fragment_results": [],
                "overall_search_state": False,
                "overall_overflow_state": False,
                "error": str(e),
            }

    def get_system_state(
        self, aggregated_results: Dict[str, Any]
    ) -> CameraDetectionState:
        """
        Określa stan systemu na podstawie zagregowanych wyników z fragmentów.

        Args:
            aggregated_results: Zagregowane wyniki z process_fragments_from_cameras

        Returns:
            Stan systemu
        """
        try:
            if aggregated_results.get("total_fragments", 0) == 0:
                return CameraDetectionState.IDLE

            # Sprawdź czy jakiś fragment miał błąd
            if any(
                not result.get("detection_success", False)
                for result in aggregated_results.get("fragment_results", [])
            ):
                return CameraDetectionState.ERROR

            # Sprawdź overflow w jakimkolwiek fragmencie
            if aggregated_results.get("overall_overflow_state", False):
                return CameraDetectionState.OVERFLOW_DETECTED

            # Sprawdź czy znaleziono papryczki w jakimkolwiek fragmencie
            if aggregated_results.get("overall_search_state", False):
                return CameraDetectionState.PEPPER_FOUND

            # Jeśli nic nie znaleziono, ale przetwarzanie zakończone bez błędów
            return CameraDetectionState.NO_PEPPER

        except Exception as e:
            error(
                f"PepperDetector: Błąd określania stanu systemu: {e}",
                message_logger=self._message_logger,
            )
            return CameraDetectionState.ERROR

    def get_stats(self) -> Dict[str, Any]:
        """
        Zwraca statystyki detektora.

        Returns:
            Słownik ze statystykami
        """
        stats_copy = self.stats.copy()
        # Konwertuj set na listę dla JSON serialization
        if "cameras_processed" in stats_copy:
            stats_copy["cameras_processed"] = list(stats_copy["cameras_processed"])
        return stats_copy

    def reset_stats(self):
        """Resetuje statystyki detektora."""
        self.stats = {
            "total_fragments_processed": 0,
            "peppers_found": 0,
            "overflow_detected": 0,
            "last_detection_time": None,
            "cameras_processed": set(),
        }

        debug(
            "PepperDetector: Zresetowano statystyki detektora głównego systemu",
            message_logger=self._message_logger,
        )
