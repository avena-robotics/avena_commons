import asyncio
import concurrent.futures
import os
import threading
import traceback
from enum import Enum
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
    debug,
    error,
    info,
)
from avena_commons.util.worker import Connector, Worker

from .fill_functions import (
    depth_measurement_in_mask,
    if_pepper_is_filled,
    if_pepper_mask_is_white,
    overflow_detection,
)
from .final_functions import config, create_masks, exclude_masks
from .search_functions import (
    check_mask_size,
)
from .utils_functions import (
    get_white_percentage_in_mask,
)


class PepperState(Enum):
    """Stany pracy Pepper Vision Worker.

    Enum odzwierciedla cykl życia procesu pepper vision.
    """

    IDLE = 0  # idle
    INITIALIZING = 1  # init pepper vision
    INITIALIZED = 2  # init completed
    STARTING = 3  # start processing
    STARTED = 4  # ready for processing
    PROCESSING = 5  # processing fragments
    STOPPING = 6  # stop processing
    STOPPED = 7  # stopped
    ERROR = 255  # error


class PepperWorker(Worker):
    """Asynchroniczny worker obsługujący pepper vision processing.

    Worker process uruchamiany na dedykowanym core (domyślnie core 2)
    do przetwarzania fragmentów obrazu z pepper vision functions.
    """

    def __init__(self, name: str, message_logger: Optional[MessageLogger] = None):
        """Zainicjalizuj Pepper Vision Worker.

        Args:
            message_logger: Logger do komunikatów (zostanie utworzony lokalny).
        """
        self._message_logger = None  # Będzie utworzony lokalny w _async_run
        self.name = name
        self.device_name = "PepperWorker"
        super().__init__(message_logger=None)
        self.state = PepperState.IDLE

        # Pepper vision configuration
        self.pepper_config = None
        self.fragment_to_section = {
            0: "top_left",
            1: "top_right",
            2: "bottom_left",
            3: "bottom_right",
        }

        # Cache for nozzle masks (załadowane z konfiguracji)
        self._nozzle_masks_cache = {}  # fragment_id (0-3) → np.ndarray

        self._process_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=4,
        )

        # Results storage
        self.last_result = None

    @property
    def state(self) -> PepperState:
        return self.__state

    @state.setter
    def state(self, value: PepperState) -> None:
        debug(
            f"{self.device_name} - State changed to {value.name}", self._message_logger
        )
        self.__state = value

    # ============================================================================
    # MARK: SEARCH AND FILL STAGES
    # ============================================================================

    @staticmethod
    def search_static(rgb, depth, nozzle_mask, params):
        """Static version of search method for multiprocessing."""
        debug_dict = {}

        (
            search_state,
            inner_zone_mask,
            outer_zone_mask,
            overflow_mask,
            outer_overflow_mask,
            inner_zone_for_color,
            exclusion_mask,
            debug_masks,
        ) = create_masks(rgb, depth, nozzle_mask, params)

        debug_dict["inner_zone_mask"] = inner_zone_mask
        debug_dict["outer_zone_mask"] = outer_zone_mask
        debug_dict["overflow_mask"] = overflow_mask
        debug_dict["inner_zone_for_color"] = inner_zone_for_color
        debug_dict["exclusion_mask"] = exclusion_mask
        debug_dict["masks"] = debug_masks

        if not search_state:
            return (
                search_state,
                False,
                inner_zone_mask,
                outer_zone_mask,
                overflow_mask,
                inner_zone_for_color,
                outer_overflow_mask,
                0,
                0,
                0,
                debug_dict,
            )

        masks = [
            inner_zone_mask,
            outer_zone_mask,
            overflow_mask,
            outer_overflow_mask,
            inner_zone_for_color,
            debug_masks["hole_mask"],
        ]

        excluded_masks = exclude_masks(masks, exclusion_mask)

        debug_dict["final_hole_mask"] = excluded_masks[5]
        outer_zone_median_start, _, _ = depth_measurement_in_mask(
            depth, outer_zone_mask
        )

        overflow_state = True
        if check_mask_size(
            inner_zone_mask, params["min_mask_size_config"]["inner_zone_mask"]
        ):
            search_state = False
        if check_mask_size(
            outer_zone_mask, params["min_mask_size_config"]["outer_zone_mask"]
        ):
            search_state = False
        if check_mask_size(
            overflow_mask, params["min_mask_size_config"]["overflow_mask"]
        ):
            overflow_state = False
        if check_mask_size(
            inner_zone_for_color, params["min_mask_size_config"]["inner_zone_for_color"]
        ):
            search_state = False

        hsv_range = params["if_pepper_mask_is_white_config"]["hsv_white_range"]
        overflow_bias = get_white_percentage_in_mask(rgb, overflow_mask, hsv_range)[0]
        overflow_outer_bias = get_white_percentage_in_mask(
            rgb, outer_overflow_mask, hsv_range
        )[0]

        return (
            search_state,
            overflow_state,
            excluded_masks[0],
            excluded_masks[1],
            excluded_masks[2],
            excluded_masks[4],
            excluded_masks[3],
            outer_zone_median_start,
            overflow_bias,
            overflow_outer_bias,
            debug_dict,
        )

    @staticmethod
    def fill_static(
        rgb,
        depth,
        inner_zone_mask,
        outer_zone_mask,
        inner_zone_for_color,
        outer_zone_median_start,
        overflow_mask,
        overflow_bias,
        overflow_outer_mask,
        overflow_outer_bias,
        params,
        overflow_only=False,
    ):
        """Static version of fill method for multiprocessing."""
        debug_dict = {}

        pepper_filled = False
        pepper_overflow = False

        if not overflow_only:
            inner_zone_median, inner_zone_non_zero_perc, debug_inner = (
                depth_measurement_in_mask(depth, inner_zone_mask)
            )
            outer_zone_median, outer_zone_non_zero_perc, debug_outer = (
                depth_measurement_in_mask(depth, outer_zone_mask)
            )

            debug_dict["inner_zone_median"] = inner_zone_median
            debug_dict["inner_zone_non_zero_perc"] = inner_zone_non_zero_perc
            debug_dict["outer_zone_median"] = outer_zone_median
            debug_dict["outer_zone_non_zero_perc"] = outer_zone_non_zero_perc
            debug_dict["debug_inner"] = debug_inner
            debug_dict["debug_outer"] = debug_outer

            is_filled, debug_filled = if_pepper_is_filled(
                inner_zone_median,
                inner_zone_non_zero_perc,
                outer_zone_median,
                outer_zone_median_start,
                params,
            )

            debug_dict["is_filled"] = is_filled
            debug_dict["debug_filled"] = debug_filled

            white_good, debug_white = if_pepper_mask_is_white(
                rgb, inner_zone_for_color, params
            )

            debug_dict["white_good"] = white_good
            debug_dict["debug_white"] = debug_white

            if is_filled and white_good:
                pepper_filled = True

        hsv_range = params["if_pepper_mask_is_white_config"]["hsv_white_range"]

        is_overflow, debug_overflow = overflow_detection(
            rgb,
            overflow_mask,
            hsv_range,
            params["overflow_detection_config"]["inner_overflow_max_perc"],
            overflow_bias,
        )
        is_overflow_outer, debug_overflow_outer = overflow_detection(
            rgb,
            overflow_outer_mask,
            hsv_range,
            params["overflow_detection_config"]["outer_overflow_max_perc"],
            overflow_outer_bias,
        )

        debug_dict["is_overflow"] = is_overflow
        debug_dict["debug_overflow"] = debug_overflow
        debug_dict["is_overflow_outer"] = is_overflow_outer
        debug_dict["debug_overflow_outer"] = debug_overflow_outer

        if is_overflow or is_overflow_outer:
            pepper_overflow = True

        return pepper_filled, pepper_overflow, debug_dict

    # ============================================================================
    # MARK: MAIN PROCESSING
    # ============================================================================

    def _load_nozzle_mask(self, mask_path: str) -> np.ndarray:
        """Wczytuje nozzle mask z pliku PNG.

        Args:
            mask_path: Ścieżka do pliku maski (np. .../nozzle_rgb_top_left.png)

        Returns:
            Maska jako numpy array (grayscale)
        """
        try:
            if not os.path.exists(mask_path):
                error(f"Nie znaleziono pliku maski: {mask_path}", self._message_logger)
                # Fallback: stwórz prostą maskę
                return self.create_simple_nozzle_mask((400, 640), "top_left")

            mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
            debug(
                f"Załadowano nozzle mask z {mask_path}: {mask.shape}",
                self._message_logger,
            )
            return mask
        except Exception as e:
            error(f"Błąd ładowania maski z {mask_path}: {e}", self._message_logger)
            return self.create_simple_nozzle_mask((400, 640), "top_left")

    def create_simple_nozzle_mask(self, fragment_shape, section):
        """Create a simple nozzle mask for fragment (fallback)."""
        h, w = fragment_shape[:2]
        nozzle_mask = np.zeros((h, w), dtype=np.uint8)

        # Create a simple circular mask in the center as placeholder
        center_x, center_y = w // 2, h // 2
        radius = min(w, h) // 6
        cv2.circle(nozzle_mask, (center_x, center_y), radius, 255, -1)

        return nozzle_mask

    @staticmethod
    def _process_search_sync(
        fragment_key: str,
        fragment_data: Dict[str, Any],
        pepper_config: Optional[Dict],
        nozzle_masks_cache: Dict[int, np.ndarray],
        fragment_to_section: Dict[int, str],
    ) -> Tuple[str, Dict[str, Any]]:
        """Synchroniczne przetwarzanie fazy SEARCH dla pojedynczego fragmentu.

        Args:
            fragment_key: Klucz identyfikujący fragment
            fragment_data: Dane fragmentu z 'color', 'depth', 'fragment_id'
            pepper_config: Konfiguracja pepper vision
            nozzle_masks_cache: Cache masek nozzle
            fragment_to_section: Mapowanie fragment_id na sekcję

        Returns:
            Tuple[str, Dict]: Para (fragment_id, wyniki_search)
        """
        fragment_id = fragment_data.get("fragment_id", fragment_key)
        section = fragment_to_section.get(fragment_id, "top_left")

        try:
            with Catchtime() as config_timer:
                color = fragment_data["color"]
                depth = fragment_data["depth"]

                # Get nozzle mask: 1) cache, 2) fragment_data, 3) placeholder
                nozzle_mask = nozzle_masks_cache.get(fragment_id)

                if nozzle_mask is None:
                    nozzle_mask = fragment_data.get("nozzle_mask")

                if nozzle_mask is None:
                    # Create simple mask as fallback
                    h, w = color.shape[:2]
                    nozzle_mask = np.zeros((h, w), dtype=np.uint8)
                    center_x, center_y = w // 2, h // 2
                    radius = min(w, h) // 6
                    cv2.circle(nozzle_mask, (center_x, center_y), radius, 255, -1)

                # Get pepper_type and reflective_nozzle from config
                pepper_detection_config = (
                    pepper_config.get("pepper_detection", {}) if pepper_config else {}
                )
                pepper_type = pepper_detection_config.get("pepper_type", "big_pepper")
                reflective_nozzle = pepper_detection_config.get(
                    "reflective_nozzle", False
                )

                # Config
                params = config(
                    nozzle_mask,
                    section,
                    pepper_type,
                    reflective_nozzle=reflective_nozzle,
                )

            # Search
            with Catchtime() as search_timer:
                (
                    search_state,
                    overflow_state,
                    inner_zone,
                    outer_zone,
                    overflow_mask,
                    inner_zone_color,
                    outer_overflow,
                    outer_zone_median_start,
                    overflow_bias,
                    overflow_outer_bias,
                    debug_search,
                ) = PepperWorker.search_static(color, depth, nozzle_mask, params)

            search_result = {
                "search_state": search_state,
                "overflow_state": overflow_state,
                "section": section,
                "masks": {
                    "inner_zone": inner_zone,
                    "outer_zone": outer_zone,
                    "overflow_mask": overflow_mask,
                    "inner_zone_color": inner_zone_color,
                    "outer_overflow": outer_overflow,
                },
                "measurements": {
                    "outer_zone_median_start": outer_zone_median_start,
                    "overflow_bias": overflow_bias,
                    "overflow_outer_bias": overflow_outer_bias,
                },
                "params": params,
                "color": color,
                "depth": depth,
                "config_time_ms": round(config_timer.ms, 2),
                "search_time_ms": round(search_timer.ms, 2),
                "success": True,
            }

            return fragment_id, search_result

        except Exception as e:
            return fragment_id, {
                "search_state": False,
                "overflow_state": False,
                "success": False,
                "error": str(e),
            }

    @staticmethod
    def _process_fill_sync(
        fragment_id: str,
        search_result: Dict[str, Any],
    ) -> Tuple[str, Dict[str, Any]]:
        """Synchroniczne przetwarzanie fazy FILL dla pojedynczego fragmentu.

        Args:
            fragment_id: Identyfikator fragmentu
            search_result: Wyniki fazy SEARCH dla tego fragmentu

        Returns:
            Tuple[str, Dict]: Para (fragment_id, wyniki_fill)
        """
        try:
            # Determine if we do full fill or overflow-only
            overflow_only = not search_result["search_state"]

            with Catchtime() as fill_timer:
                pepper_filled, pepper_overflow, debug_fill = PepperWorker.fill_static(
                    search_result["color"],
                    search_result["depth"],
                    search_result["masks"]["inner_zone"],
                    search_result["masks"]["outer_zone"],
                    search_result["masks"]["inner_zone_color"],
                    search_result["measurements"]["outer_zone_median_start"],
                    search_result["masks"]["overflow_mask"],
                    search_result["measurements"]["overflow_bias"],
                    search_result["masks"]["outer_overflow"],
                    search_result["measurements"]["overflow_outer_bias"],
                    search_result["params"],
                    overflow_only=overflow_only,
                )

            fill_result = {
                "search_state": search_result["search_state"],
                "overflow_state": search_result["overflow_state"] or pepper_overflow,
                "is_filled": pepper_filled,
                "success": True,
                "phase": "search_and_fill",
                "config_time_ms": search_result["config_time_ms"],
                "search_time_ms": search_result["search_time_ms"],
                "fill_time_ms": round(fill_timer.ms, 2),
            }

            return fragment_id, fill_result

        except Exception as e:
            return fragment_id, {
                "search_state": search_result.get("search_state", False),
                "overflow_state": search_result.get("overflow_state", False),
                "is_filled": False,
                "success": False,
                "error": str(e),
                "phase": "fill_error",
            }

    def _process_fragments_two_phase_sync(
        self, fragments: Dict[str, Dict], min_found: int = 2
    ) -> Dict:
        """Dwufazowe przetwarzanie z równoległym przetwarzaniem fragmentów (synchroniczne).

        FAZA 1: SEARCH - równolegle na wszystkich fragmentach w osobnych procesach
        FAZA 2: FILL (warunkowo) - jeśli znaleziono >= min_found, równolegle na wszystkich

        Args:
            fragments: Dict fragmentów z 'color', 'depth', 'nozzle_mask'
            min_found: Minimalna liczba fragmentów ze znalezioną papryczką (default: 2)

        Returns:
            Dict z wynikami i metrykami
        """
        self.state = PepperState.PROCESSING

        try:
            with Catchtime() as total_timer:
                # ===== FAZA 1: PARALLEL SEARCH =====
                debug(
                    f"PHASE 1: Parallel SEARCH in {len(fragments)} fragments",
                    self._message_logger,
                )

                # Submit all search tasks to process pool
                search_futures = {}
                for fragment_key, fragment_data in fragments.items():
                    future = self._process_pool.submit(
                        self._process_search_sync,
                        fragment_key,
                        fragment_data,
                        self.pepper_config,
                        self._nozzle_masks_cache,
                        self.fragment_to_section,
                    )
                    search_futures[fragment_key] = future

                # Log czas po submit
                debug(
                    f"PHASE 1: Search tasks submitted waiting for results...",
                    self._message_logger,
                )

                # Collect results
                search_results = {}
                error_count = 0
                for fragment_key, future in search_futures.items():
                    try:
                        fragment_id, search_result = future.result(
                            timeout=0.02  # 20ms
                        )
                        search_results[fragment_id] = search_result
                        if (
                            not search_result.get("success", False)
                            and "error" in search_result
                        ):
                            error(
                                f"Search failed for {fragment_key}: {search_result['error']}",
                                self._message_logger,
                            )
                    except Exception as e:
                        error_count += 1
                        error(
                            f"Search task failed for {fragment_key} with exception: {e}",
                            self._message_logger,
                        )
                        error_id = f"error_{error_count}"
                        search_results[error_id] = {
                            "search_state": False,
                            "overflow_state": False,
                            "success": False,
                            "error": str(e),
                        }

                # Log czas po collect search
                debug(
                    f"PHASE 1 COMPLETE: Collected search results",
                    self._message_logger,
                )

                # COUNT: How many fragments found peppers?
                found_count = sum(
                    1
                    for r in search_results.values()
                    if r.get("search_state", False) and r.get("success", False)
                )

                info(
                    f"PHASE 1 COMPLETE: {found_count}/{len(fragments)} fragments found peppers",
                    self._message_logger,
                )

                # ===== DECISION POINT =====
                if found_count < min_found:
                    debug(
                        f"ABORT: Only {found_count}/{min_found} fragments found peppers - skipping FILL phase",
                        self._message_logger,
                    )

                    # Return results from search only
                    final_results = {}
                    for fid, sres in search_results.items():
                        final_results[fid] = {
                            "search_state": sres.get("search_state", False),
                            "overflow_state": sres.get("overflow_state", False),
                            "is_filled": False,
                            "success": sres.get("success", False),
                            "phase": "search_only",
                            "config_time_ms": sres.get("config_time_ms", 0.0),
                            "search_time_ms": sres.get("search_time_ms", 0.0),
                            "fill_time_ms": 0.0,
                        }
                        if "error" in sres:
                            final_results[fid]["error"] = sres["error"]

                    self.state = PepperState.STARTED

                    # Store result in self.last_result
                    self.last_result = {
                        "results": final_results,
                        "total_processing_time_ms": round(total_timer.ms, 2),
                        "fragments_count": len(fragments),
                        "found_count": found_count,
                        "min_required": min_found,
                        "phase_completed": "search_only",
                        "success": True,
                    }

                    return self.last_result

                # ===== FAZA 2: PARALLEL FILL =====
                debug(
                    f"PHASE 2: Parallel FILL on all fragments (found >= {min_found})",
                    self._message_logger,
                )
                # Submit all fill tasks to process pool
                fill_futures = {}
                for fragment_id, search_result in search_results.items():
                    if not search_result.get("success", False):
                        continue
                    future = self._process_pool.submit(
                        self._process_fill_sync, fragment_id, search_result
                    )
                    fill_futures[fragment_id] = future

                # Log czas po submit fill
                debug(
                    f"PHASE 2: Fill tasks submitted, waiting for results...",
                    self._message_logger,
                )

                # Collect fill results
                final_results = {}
                for fragment_id, future in fill_futures.items():
                    try:
                        fid, fill_result = future.result(
                            timeout=0.02  # Zmniejszono z 0.2 do 0.1 s
                        )
                        final_results[fid] = fill_result
                        if (
                            not fill_result.get("success", False)
                            and "error" in fill_result
                        ):
                            error(
                                f"Fill failed for {fragment_id}: {fill_result['error']}",
                                self._message_logger,
                            )
                    except Exception as e:
                        error(
                            f"Fill task failed for {fragment_id} with exception: {e}",
                            self._message_logger,
                        )
                        # Fallback: use search result with fill error
                        search_result = search_results.get(fragment_id, {})
                        final_results[fragment_id] = {
                            "search_state": search_result.get("search_state", False),
                            "overflow_state": search_result.get(
                                "overflow_state", False
                            ),
                            "is_filled": False,
                            "success": False,
                            "phase": "fill_error",
                            "error": str(e),
                            "config_time_ms": search_result.get("config_time_ms", 0.0),
                            "search_time_ms": search_result.get("search_time_ms", 0.0),
                            "fill_time_ms": 0.0,
                        }

                # Log czas po collect fill
                debug(
                    f"PHASE 2 COMPLETE: Collected fill results",
                    self._message_logger,
                )

                # Add fragments that failed in search (no fill executed)
                for fragment_id, search_result in search_results.items():
                    if fragment_id not in final_results:
                        final_results[fragment_id] = {
                            "search_state": search_result.get("search_state", False),
                            "overflow_state": search_result.get(
                                "overflow_state", False
                            ),
                            "is_filled": False,
                            "success": search_result.get("success", False),
                            "phase": "search_failed",
                            "config_time_ms": search_result.get("config_time_ms", 0.0),
                            "search_time_ms": search_result.get("search_time_ms", 0.0),
                            "fill_time_ms": 0.0,
                        }
                        if "error" in search_result:
                            final_results[fragment_id]["error"] = search_result["error"]

                info(
                    f"PHASE 2 COMPLETE: All fragments processed",
                    self._message_logger,
                )

            self.state = PepperState.STARTED

            # Store result in self.last_result
            self.last_result = {
                "results": final_results,
                "total_processing_time_ms": round(total_timer.ms, 2),
                "fragments_count": len(fragments),
                "found_count": found_count,
                "min_required": min_found,
                "phase_completed": "search_and_fill",
                "success": True,
            }

            return self.last_result

        except Exception as e:
            error(f"Error in process_fragments_two_phase: {e}", self._message_logger)
            error(f"Traceback: {traceback.format_exc()}", self._message_logger)
            self.state = PepperState.ERROR

            # Store error result in self.last_result
            self.last_result = {
                "results": {},
                "total_processing_time_ms": 0.0,
                "fragments_count": 0,
                "found_count": 0,
                "min_required": min_found,
                "phase_completed": "error",
                "success": False,
                "error": str(e),
            }

            return self.last_result

    def _process_fragments_sync(self, fragments: Dict[str, Dict]) -> Dict:
        """Process list of image fragments with pepper vision using two-phase strategy (synchroniczne).

        Używa dwufazowego przetwarzania z cross-fragment logic (min 2/4 found).
        Dla pojedynczego fragmentu min_found=1.

        Args:
            fragments: Dict of fragment dicts with 'color', 'depth', 'fragment_id', 'nozzle_mask'

        Returns:
            Dict with processing results for each fragment
        """
        # Determine min_found based on fragment count
        if len(fragments) <= 1:
            min_found = 1
            debug(
                f"Using TWO-PHASE processing for {len(fragments)} fragment (min 1/1 required)",
                self._message_logger,
            )
        else:
            min_found = 2
            debug(
                f"Using TWO-PHASE processing for {len(fragments)} fragments (min 2/{len(fragments)} required)",
                self._message_logger,
            )

        return self._process_fragments_two_phase_sync(fragments, min_found=min_found)

    async def init_pepper(self, pepper_settings: dict):
        """Initialize pepper vision worker with settings.

        Args:
            pepper_settings: Configuration dict for pepper vision

        Returns:
            bool: True if initialization successful
        """
        try:
            self.state = PepperState.INITIALIZING
            debug(
                f"{self.device_name} - Initializing pepper vision", self._message_logger
            )

            self.pepper_config = pepper_settings

            # Load nozzle masks from configuration
            nozzle_masks_paths = pepper_settings.get("nozzle_masks_paths", {})
            camera_to_section = pepper_settings.get("camera_to_section", {})

            if nozzle_masks_paths:
                info(
                    f"Loading {len(nozzle_masks_paths)} nozzle masks from configuration",
                    self._message_logger,
                )

                for camera_num_str, mask_path in nozzle_masks_paths.items():
                    try:
                        camera_num = int(camera_num_str)

                        # Map camera number (1-4) to fragment_id (0-3)
                        # Konfiguracja: 1→top_left, 2→top_right, 3→bottom_left, 4→bottom_right
                        # Kod: 0→top_left, 1→top_right, 2→bottom_left, 3→bottom_right
                        fragment_id = camera_num - 1

                        # Załaduj maskę z pliku
                        mask = self._load_nozzle_mask(mask_path)

                        if mask is not None and mask.size > 0:
                            self._nozzle_masks_cache[fragment_id] = mask

                            section = camera_to_section.get(camera_num, "unknown")
                            info(
                                f"Cached nozzle mask for camera {camera_num} → fragment {fragment_id} ({section})",
                                self._message_logger,
                            )
                        else:
                            error(
                                f"Failed to load nozzle mask for camera {camera_num} from {mask_path}",
                                self._message_logger,
                            )

                    except Exception as mask_error:
                        error(
                            f"Error loading nozzle mask for camera {camera_num_str}: {mask_error}",
                            self._message_logger,
                        )

                info(
                    f"Successfully cached {len(self._nozzle_masks_cache)} nozzle masks",
                    self._message_logger,
                )
            else:
                debug(
                    "No nozzle_masks_paths in configuration - will use placeholder masks",
                    self._message_logger,
                )

            self.state = PepperState.INITIALIZED
            debug(
                f"{self.device_name} - Pepper vision initialized", self._message_logger
            )
            return True

        except Exception as e:
            error(f"{self.device_name} - Init failed: {e}", self._message_logger)
            error(f"Traceback: {traceback.format_exc()}", self._message_logger)
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
            filename=f"temp/pepper_worker_{self.name}.log",
            debug=False,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=10,
            colors=False,
        )
        _pipe_loop_freq = 1000  # Hz

        debug(
            f"{self.device_name} - Worker started with local logger on PID: {os.getpid()}",
            self._message_logger,
        )

        try:
            while True:
                if pipe_in.poll(1 / _pipe_loop_freq):  # Czekaj na dane z pipe
                    data = pipe_in.recv()

                    match data[0]:
                        case "PEPPER_INIT":
                            try:
                                debug(
                                    f"{self.device_name} - Received PEPPER_INIT: {data[1]}",
                                    self._message_logger,
                                )
                                result = await self.init_pepper(data[1])
                                pipe_in.send(result)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error in PEPPER_INIT: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(False)

                        case "PEPPER_START":
                            try:
                                debug(
                                    f"{self.device_name} - Starting pepper processing",
                                    self._message_logger,
                                )
                                result = await self.start_pepper()
                                pipe_in.send(result)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error starting pepper: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(False)

                        case "PEPPER_STOP":
                            try:
                                debug(
                                    f"{self.device_name} - Stopping pepper processing",
                                    self._message_logger,
                                )
                                result = await self.stop_pepper()
                                pipe_in.send(result)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error stopping pepper: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(False)

                        case "GET_STATE":
                            try:
                                state = self.state
                                pipe_in.send(state)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error getting state: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(None)

                        case "PROCESS_FRAGMENTS":
                            try:
                                debug(
                                    f"{self.device_name} - Received PROCESS_FRAGMENTS with {len(data[1])} fragments",
                                    self._message_logger,
                                )
                                fragments = data[1]

                                pipe_in.send(True)

                                # Uruchom w dedykowanym wątku
                                processing_thread = threading.Thread(
                                    target=self._process_fragments_sync,
                                    args=(fragments,),
                                    name=f"PepperProcessing_{self.name}",
                                    daemon=True,
                                )
                                processing_thread.start()

                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error scheduling fragments processing: {e}",
                                    self._message_logger,
                                )
                                # Zapisz błąd do last_result
                                self.last_result = {
                                    "results": {},
                                    "success": False,
                                    "error": str(e),
                                }

                        case "GET_LAST_RESULT":
                            try:
                                pipe_in.send(self.last_result)
                                self.last_result = None  # Clear after sending
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error getting last result: {e}",
                                    self._message_logger,
                                )
                                pipe_in.send(None)

                        case _:
                            error(
                                f"{self.device_name} - Unknown command: {data[0]}",
                                self._message_logger,
                            )

        except asyncio.CancelledError:
            info(f"{self.device_name} - Task was cancelled", self._message_logger)
        except Exception as e:
            error(f"{self.device_name} - Error in Worker: {e}", self._message_logger)
            error(f"Traceback:\n{traceback.format_exc()}", self._message_logger)
        finally:
            # Cleanup process pool with wait=True for stability
            self._process_pool.shutdown(wait=True)
            info(f"{self.device_name} - Worker has shut down", self._message_logger)


class PepperConnector(Connector):
    """Wątkowo-bezpieczny łącznik do PepperWorker.

    Zapewnia synchroniczne API wykorzystujące wewnętrznie komunikację
    przez pipe do procesu pepper worker.
    """

    def __init__(
        self,
        core: int = 2,
        name="pepper_nozzle1",
        message_logger: Optional[MessageLogger] = None,
    ):
        """Utwórz pepper connector z dedykowanym core.

        Args:
            core: Numer rdzenia CPU dla pepper worker (domyślnie 2)
            message_logger: Zewnętrzny logger
        """
        self.__lock = threading.Lock()
        self.name = name
        super().__init__(core=core, message_logger=message_logger)
        super()._connect()
        self._local_message_logger = message_logger

    def _run(self, pipe_in, message_logger=None):
        """Uruchom pepper worker w osobnym procesie."""
        worker = PepperWorker(name=self.name, message_logger=message_logger)
        worker._run(pipe_in)

    def init(self, configuration: dict = {}):
        """Zainicjalizuj pepper vision przekazując konfigurację.

        Args:
            configuration: Parametry inicjalizacji pepper vision

        Returns:
            bool: True jeśli inicjalizacja się powiodła
        """
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["PEPPER_INIT", configuration]
            )
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
            value = super()._send_thru_pipe(
                self._pipe_out, ["PROCESS_FRAGMENTS", fragments]
            )
            return value

    def get_last_result(self):
        """Pobierz ostatni wynik przetwarzania.

        Returns:
            Dict: Wyniki przetwarzania lub None
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["GET_LAST_RESULT"])
            return value
