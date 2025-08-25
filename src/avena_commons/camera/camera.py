import asyncio
import base64
import threading
import time
import traceback

import cv2
import numpy as np
from dotenv import load_dotenv
from pyorbbecsdk import (
    AlignFilter,
    Config,
    Context,
    OBAlignMode,
    OBFormat,
    OBPermissionType,
    OBPropertyID,
    OBPropertyType,
    OBSensorType,
    OBStreamType,
    Pipeline,
    SpatialAdvancedFilter,
    TemporalFilter,
    VideoStreamProfile,
)

from avena_commons.camera.driver.orbec_335le import OrbecGemini335Le
from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
    Result,
)
from avena_commons.util.logger import MessageLogger, debug, error, info

load_dotenv(override=True)


class Camera(EventListener):
    """
    Main logic class for handling events and managing the state of the Munchies system.
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
        Initializes the Camera with necessary configurations and state.

        Args:
            message_logger (Optional[MessageLogger]): Logger for logging messages.

        Raises:
            ValueError: If required environment variables are missing.
        """

        if not port:
            raise ValueError(
                "Brak wymaganej zmiennej środowiskowej CAMERA_LISTENER_PORT"
            )

        self._check_local_data_frequency = 100
        self.name = name

        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
        )

        debug(f"camera init", self._message_logger)

        # print(self._configuration)

        if self._configuration.get("camera_ip", None) is None:
            error(
                f"EVENT_LISTENER_INIT: Brak konfiguracji CAMERA_IP dla kamery",
                self._message_logger,
            )
            raise ValueError(f"Brak konfiguracji CAMERA_IP dla kamery")
        self.camera_address = self._configuration["camera_ip"]

        self.camera_pipeline = None
        self.camera_config = None

        self.camera_running = False

        # czat insetrion
        self.align_filter = None
        self.spatial_filter = None
        self.temporal_filter = None

        # Bufory dla synchronizacji ramek
        self.latest_color_frame = None
        self.latest_depth_frame = None
        self.last_color_timestamp = 0
        self.last_depth_timestamp = 0
        self.frame_sync_timeout = 500  # ms - maksymalna różnica czasowa między ramkami (zwiększone dla stabilności)

        debug(
            f"EVENT_LISTENER_INIT: Event listener kamery został zainicjalizowany dla ip {self.camera_address}",
            self._message_logger,
        )
        self.camera = OrbecGemini335Le(self.camera_address, self._message_logger)

    async def on_initializing(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZING.
        Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
        self.camera.init(self._configuration["camera_settings"])

    async def on_starting(self):
        """Metoda wywoływana podczas przejścia w stan STARTING.
        Tu komponent przygotowuje się do uruchomienia głównych operacji."""
        self.camera.start()

    async def on_stopping(self):
        self.camera.stop()

    # MARK: CHECK LOCAL DATA
    async def _check_local_data(self):
        """
        Periodically checks and processes local data

        Raises:
            Exception: If an error occurs during data processing.
        """
        if self.camera.state == CameraState.ERROR:
            self.set_state(EventListenerState.ON_ERROR)

        # if self.camera_running:
        #     # debug("Sprawdzanie lokalnych danych kamery", self._message_logger)

        #     # Zwiększ timeout i dodaj error handling dla czekania na ramki
        #     try:
        #         frames = self.camera_pipeline.wait_for_frames(3)
        #         if frames is None:
        #             # error(
        #             #     f"Timeout przy pobieraniu ramek z kamery {self.name}",
        #             #     self._message_logger,
        #             # )
        #             return

        #         debug(f"Pobrano ramki: {type(frames)}", self._message_logger)

        #         # Zastosuj filtry
        #         if self.align_filter:
        #             frames = self.align_filter.process(frames)
        #             debug("Filtr wyrównania zastosowany", self._message_logger)
        #         if self.spatial_filter:
        #             frames = self.spatial_filter.process(frames)
        #             debug("Filtr przestrzenny zastosowany", self._message_logger)
        #         if self.temporal_filter:
        #             frames = self.temporal_filter.process(frames)
        #             debug("Filtr czasowy zastosowany", self._message_logger)

        #         # Przetwórz ramki
        #         debug("Rozpoczęcie przetwarzania ramek", self._message_logger)
        #         # rois = self._process_frames(frames)

        #         # if len(rois) > 0:
        #         #     info(
        #         #         f"Wytworzono {len(rois)} ROI, wysyłanie ramek",
        #         #         self._message_logger,
        #         #     )
        #         #     await self._send_frames(rois)
        #         # else:
        #         #     debug(
        #         #         "Brak ROI - sprawdź poprzednie komunikaty diagnostyczne",
        #         #         self._message_logger,
        #         #     )

        #     except Exception as pipeline_error:
        #         error(
        #             f"Błąd pipeline kamery {self.name}: {pipeline_error}",
        #             self._message_logger,
        #         )
        #         error(
        #             f"Kamera IP: {self.camera_address}, Port pipeline: prawdopodobnie 8090",
        #             self._message_logger,
        #         )
        #         # Możliwe przyczyny: problema sieciowe, kamera offline, konflikt IP
        # else:
        #     debug(
        #         "Kamera nie jest uruchomiona - pomijanie sprawdzania danych",
        #         self._message_logger,
        # )

    # MARK: HELPER_CLASSES


#     def _init_camera(self):
#         """
#         Init camera:
#         - find device by ip
#         - create pipeline
#         - create config
#         - enable stream
#         - enable settings
#         """

#         camera_settings = self._configuration["camera_settings"]
#         color_settings = camera_settings.get("color", {})
#         depth_settings = camera_settings.get("depth", {})

#         ctx = Context()
#         try:
#             dev = ctx.create_net_device(self.camera_address, 8090)
#             debug(
#                 f"CAMERA_INIT: Otwarta kamera {self.name} na ip {self.camera_address}",
#                 self._message_logger,
#             )
#             debug(
#                 f"CAMERA_INIT: camera info: {dev.get_device_info()}",
#                 self._message_logger,
#             )
#         except Exception as e:
#             error(
#                 f"CAMERA_INIT: Błąd podczas otwierania kamery {self.name} na ip {self.camera_address}: {e}",
#                 self._message_logger,
#             )
#             self._change_fsm_state(EventListenerState.ON_ERROR)
#             raise e

#         # MARK: Disparity Settings
#         try:
#             disparity_settings = camera_settings.get("disparity", {})
#             if disparity_settings:
#                 disparity_pid = OBPropertyID.OB_STRUCT_DISPARITY_RANGE_MODE
#                 if not dev.is_property_supported(
#                     disparity_pid, OBPermissionType.PERMISSION_READ_WRITE
#                 ):
#                     error(
#                         f"CAMERA_INIT: Zmiana trybu zakresu dysparycji nie jest obsługiwana w kamerze {self.name}. Sprawdź wersję firmware.",
#                         self._message_logger,
#                     )
#                 else:
#                     # Set Disparity Range Mode
#                     desired_mode_name = disparity_settings.get("range_mode")
#                     if desired_mode_name:
#                         current_mode = dev.get_disparity_range_mode()
#                         debug(
#                             f"CAMERA_INIT: Aktualny tryb zakresu dysparycji: {current_mode.name}",
#                             self._message_logger,
#                         )

#                         available_modes = dev.get_disparity_range_mode_list()
#                         is_mode_set = False
#                         available_mode_names = []
#                         for i in range(available_modes.get_count()):
#                             mode = available_modes.get_disparity_range_mode_by_index(i)
#                             available_mode_names.append(mode.name)
#                             if mode.name == desired_mode_name:
#                                 dev.set_disparity_range_mode(mode.name)
#                                 debug(
#                                     f"CAMERA_INIT: Ustawiono tryb zakresu dysparycji na {mode.name}",
#                                     self._message_logger,
#                                 )
#                                 is_mode_set = True
#                                 break

#                         if not is_mode_set:
#                             error(
#                                 f"CAMERA_INIT: Żądany tryb zakresu dysparycji '{desired_mode_name}' nie został znaleziony. Dostępne tryby: {available_mode_names}. Używam bieżącego: {current_mode.name}",
#                                 self._message_logger,
#                             )

#             # Set Disparity Search Offset
#             offset_pid = OBPropertyID.OB_STRUCT_DISPARITY_SEARCH_OFFSET
#             if not dev.is_property_supported(
#                 offset_pid, OBPermissionType.PERMISSION_READ_WRITE
#             ):
#                 debug(
#                     f"CAMERA_INIT: Przesunięcie wyszukiwania dysparycji nie jest obsługiwane w kamerze {self.name}",
#                     self._message_logger,
#                 )
#             else:
#                 disparity_offset = disparity_settings.get("search_offset")
#                 if disparity_offset and disparity_offset > 0:
#                     dev.set_int_property(offset_pid, disparity_offset)
#                     debug(
#                         f"CAMERA_INIT: Ustawiono przesunięcie wyszukiwania dysparycji na {disparity_offset}",
#                         self._message_logger,
#                     )
#         except AttributeError as e:
#             error(
#                 f"CAMERA_INIT: Używana wersja pyorbbecsdk nie obsługuje zmiany trybu dysparycji. Wymagana jest wersja >= 2.2.x. Ta funkcja zostanie pominięta. Błąd: {e}",
#                 self._message_logger,
#             )

#         self.camera_pipeline = Pipeline(dev)
#         self.camera_config = Config()

#         # MARK: SETTINGS
#         color_exposure = color_settings.get("exposure", 500)
#         dev.set_int_property(OBPropertyID.OB_PROP_COLOR_EXPOSURE_INT, color_exposure)
#         debug(
#             f"CAMERA_INIT: Ustawiono OB_PROP_COLOR_EXPOSURE_INT na {color_exposure}",
#             self._message_logger,
#         )

#         color_gain = color_settings.get("gain", 10)
#         dev.set_int_property(OBPropertyID.OB_PROP_COLOR_GAIN_INT, color_gain)
#         debug(
#             f"CAMERA_INIT: Ustawiono OB_PROP_COLOR_GAIN_INT na {color_gain}",
#             self._message_logger,
#         )

#         color_white_balance = color_settings.get("white_balance", 4000)
#         dev.set_int_property(
#             OBPropertyID.OB_PROP_COLOR_WHITE_BALANCE_INT, color_white_balance
#         )
#         debug(
#             f"CAMERA_INIT: Ustawiono OB_PROP_COLOR_WHITE_BALANCE_INT na {color_white_balance}",
#             self._message_logger,
#         )

#         # Depth stream settings
#         depth_exposure = depth_settings.get("exposure", 500)
#         dev.set_int_property(OBPropertyID.OB_PROP_DEPTH_EXPOSURE_INT, depth_exposure)
#         debug(
#             f"CAMERA_INIT: Ustawiono OB_PROP_DEPTH_EXPOSURE_INT na {depth_exposure}",
#             self._message_logger,
#         )

#         depth_gain = depth_settings.get("gain", 10)
#         dev.set_int_property(OBPropertyID.OB_PROP_DEPTH_GAIN_INT, depth_gain)
#         debug(
#             f"CAMERA_INIT: Ustawiono OB_PROP_DEPTH_GAIN_INT na {depth_gain}",
#             self._message_logger,
#         )

#         laser_power = depth_settings.get("laser_power", 5)
#         dev.set_int_property(
#             OBPropertyID.OB_PROP_LASER_POWER_LEVEL_CONTROL_INT, laser_power
#         )
#         debug(
#             f"CAMERA_INIT: Ustawiono OB_PROP_LASER_POWER_LEVEL_CONTROL_INT na {laser_power}",
#             self._message_logger,
#         )

#         # Disparity
#         disparity_to_depth = camera_settings.get("disparity_to_depth", True)
#         dev.set_bool_property(
#             OBPropertyID.OB_PROP_DISPARITY_TO_DEPTH_BOOL, disparity_to_depth
#         )
#         debug(
#             f"CAMERA_INIT: Ustawiono OB_PROP_DISPARITY_TO_DEPTH_BOOL na {disparity_to_depth}",
#             self._message_logger,
#         )

#         # MARK: PROFILES & ALIGNMENT
#         use_hardware_align = camera_settings.get("align", True)

#         # Najpierw pobierz dostępne profile bez ustawiania trybu wyrównania
#         color_profile_list = self.camera_pipeline.get_stream_profile_list(
#             OBSensorType.COLOR_SENSOR
#         )

#         match color_settings.get("format", "BGR"):
#             case "BGR":
#                 color_format = OBFormat.BGR
#             case "RGB":
#                 color_format = OBFormat.RGB
#             case "MJPG":
#                 color_format = OBFormat.MJPG
#             case _:
#                 error(
#                     f"CAMERA_INIT: Nieznany format koloru: {color_settings.get('format', 'BGR')} - używam BGR",
#                     self._message_logger,
#                 )
#                 color_format = OBFormat.BGR  # Ustaw domyślny format

#         width = color_settings.get("width", 640)
#         height = color_settings.get("height", 400)
#         fps = color_settings.get("fps", 30)

#         debug(
#             f"CAMERA_INIT: Wyszukuję profil koloru dla {width}x{height}@{fps} {color_format}",
#             self._message_logger,
#         )
#         color_profile = color_profile_list.get_video_stream_profile(
#             width, height, color_format, fps
#         )

#         if not color_profile:
#             error(
#                 f"CAMERA_INIT: Nie znaleziono pasującego profilu koloru dla {width}x{height}@{fps} {color_format}",
#                 self._message_logger,
#             )
#             # Spróbuj z domyślnymi parametrami jako fallback
#             debug(
#                 "CAMERA_INIT: Próbuję z domyślnymi parametrami profilu",
#                 self._message_logger,
#             )
#             color_profile = color_profile_list.get_video_stream_profile(
#                 640, 400, OBFormat.MJPG, 30
#             )
#             if not color_profile:
#                 error(
#                     "CAMERA_INIT: Nie można znaleźć żadnego profilu koloru",
#                     self._message_logger,
#                 )
#                 self._change_fsm_state(EventListenerState.ON_ERROR)
#                 raise ValueError("Brak dostępnych profili koloru")

#         # Sprawdź czy sprzętowe wyrównanie jest obsługiwane dla tego profilu
#         hardware_align_configured = False
#         if use_hardware_align and color_profile:
#             try:
#                 debug(
#                     f"CAMERA_INIT: Sprawdzam dostępność sprzętowego wyrównania dla profilu {width}x{height}@{fps} {color_format}",
#                     self._message_logger,
#                 )

#                 # DODAJ DIAGNOSTYKĘ WSZYSTKICH DOSTĘPNYCH KOMBINACJI
#                 info(
#                     f"CAMERA_INIT: === ANALIZA OBSŁUGI SPRZĘTOWEGO WYRÓWNANIA D2C ===",
#                     self._message_logger,
#                 )

#                 # Pobierz wszystkie dostępne profile koloru
#                 supported_hw_combinations = []

#                 debug(
#                     f"CAMERA_INIT: Sprawdzanie wszystkich dostępnych profili koloru...",
#                     self._message_logger,
#                 )
#                 for i in range(color_profile_list.get_count()):
#                     test_color_profile = color_profile_list.get_profile(i)
#                     if hasattr(test_color_profile, "get_width"):
#                         try:
#                             # Sprawdź czy ten profil koloru obsługuje sprzętowe D2C
#                             test_hw_d2c_list = (
#                                 self.camera_pipeline.get_d2c_depth_profile_list(
#                                     test_color_profile, OBAlignMode.HW_MODE
#                                 )
#                             )

#                             profile_info = f"{test_color_profile.get_width()}x{test_color_profile.get_height()}@{test_color_profile.get_fps()} {test_color_profile.get_format()}"

#                             if test_hw_d2c_list and len(test_hw_d2c_list) > 0:
#                                 supported_hw_combinations.append({
#                                     "color_profile": test_color_profile,
#                                     "depth_profiles": test_hw_d2c_list,
#                                     "info": profile_info,
#                                 })

#                                 info(
#                                     f"CAMERA_INIT: ✓ OBSŁUGIWANE - Color: {profile_info}",
#                                     self._message_logger,
#                                 )

#                                 # Wylistuj dostępne profile głębi dla tej kombinacji
#                                 for j, depth_prof in enumerate(test_hw_d2c_list):
#                                     depth_info = f"{depth_prof.get_width()}x{depth_prof.get_height()}@{depth_prof.get_fps()} {depth_prof.get_format()}"
#                                     info(
#                                         f"CAMERA_INIT:   -> Depth {j}: {depth_info}",
#                                         self._message_logger,
#                                     )
#                             else:
#                                 debug(
#                                     f"CAMERA_INIT: ✗ NIEOBSŁUGIWANE - Color: {profile_info}",
#                                     self._message_logger,
#                                 )

#                         except Exception as test_error:
#                             debug(
#                                 f"CAMERA_INIT: Błąd testowania profilu {i}: {test_error}",
#                                 self._message_logger,
#                             )

#                 # Podsumowanie
#                 if supported_hw_combinations:
#                     info(
#                         f"CAMERA_INIT: === PODSUMOWANIE OBSŁUGIWANYCH KOMBINACJI ({len(supported_hw_combinations)}) ===",
#                         self._message_logger,
#                     )

#                     # Grupuj po rozdzielczości dla lepszej czytelności
#                     resolution_groups = {}
#                     for combo in supported_hw_combinations:
#                         prof = combo["color_profile"]
#                         res_key = f"{prof.get_width()}x{prof.get_height()}"
#                         if res_key not in resolution_groups:
#                             resolution_groups[res_key] = []
#                         resolution_groups[res_key].append(combo)

#                     for resolution, combos in resolution_groups.items():
#                         info(
#                             f"CAMERA_INIT: Rozdzielczość {resolution}:",
#                             self._message_logger,
#                         )
#                         for combo in combos:
#                             prof = combo["color_profile"]
#                             info(
#                                 f"CAMERA_INIT:   - {prof.get_fps()}fps {prof.get_format()} ({len(combo['depth_profiles'])} depth profiles)",
#                                 self._message_logger,
#                             )

#                     # Znajdź najwyższą obsługiwaną rozdzielczość
#                     max_pixels = 0
#                     best_combo = None
#                     for combo in supported_hw_combinations:
#                         prof = combo["color_profile"]
#                         pixels = prof.get_width() * prof.get_height()
#                         if pixels > max_pixels:
#                             max_pixels = pixels
#                             best_combo = combo

#                     if best_combo:
#                         best_prof = best_combo["color_profile"]
#                         info(
#                             f"CAMERA_INIT: 🏆 NAJWYŻSZA OBSŁUGIWANA ROZDZIELCZOŚĆ: {best_prof.get_width()}x{best_prof.get_height()}@{best_prof.get_fps()} {best_prof.get_format()}",
#                             self._message_logger,
#                         )

#                         # Pokaż przykładową konfigurację JSON
#                         info(
#                             f"CAMERA_INIT: === PRZYKŁADOWA KONFIGURACJA JSON ===",
#                             self._message_logger,
#                         )
#                         example_depth = best_combo["depth_profiles"][0]
#                         format_name = str(best_prof.get_format()).replace(
#                             "OBFormat.", ""
#                         )
#                         depth_format_name = str(example_depth.get_format()).replace(
#                             "OBFormat.", ""
#                         )

#                         example_config = f'''{{
#   "camera_ip": "192.168.1.10",
#   "camera_settings": {{
#     "align": true,
#     "disparity_to_depth": true,
#     "color": {{
#       "width": {best_prof.get_width()},
#       "height": {best_prof.get_height()},
#       "fps": {best_prof.get_fps()},
#       "format": "{format_name}",
#       "exposure": 500,
#       "gain": 10,
#       "white_balance": 4000
#     }},
#     "depth": {{
#       "width": {example_depth.get_width()},
#       "height": {example_depth.get_height()},
#       "fps": {example_depth.get_fps()},
#       "format": "{depth_format_name}",
#       "exposure": 500,
#       "gain": 10,
#       "laser_power": 5
#     }}
#   }}
# }}'''
#                         info(f"CAMERA_INIT: {example_config}", self._message_logger)
#                 else:
#                     error(
#                         f"CAMERA_INIT: ❌ BRAK OBSŁUGIWANYCH KOMBINACJI dla sprzętowego D2C",
#                         self._message_logger,
#                     )
#                     info(
#                         f"CAMERA_INIT: Ta kamera może nie obsługiwać sprzętowego wyrównania lub wymaga aktualizacji firmware",
#                         self._message_logger,
#                     )

#                 info(f"CAMERA_INIT: === KONIEC ANALIZY D2C ===", self._message_logger)

#                 # Teraz sprawdź oryginalnie żądany profil
#                 hw_d2c_profile_list = self.camera_pipeline.get_d2c_depth_profile_list(
#                     color_profile, OBAlignMode.HW_MODE
#                 )
#                 if not hw_d2c_profile_list or len(hw_d2c_profile_list) == 0:
#                     info(
#                         f"CAMERA_INIT: Żądany profil {width}x{height}@{fps} {color_format} NIE OBSŁUGUJE sprzętowego wyrównania. Przełączam na programowe.",
#                         self._message_logger,
#                     )
#                     use_hardware_align = False
#                 else:
#                     # Sprzętowe wyrównanie jest obsługiwane dla żądanego profilu
#                     self.camera_config.set_align_mode(OBAlignMode.HW_MODE)
#                     depth_profile = hw_d2c_profile_list[0]

#                     self.camera_config.enable_stream(depth_profile)
#                     self.camera_config.enable_stream(color_profile)

#                     debug(
#                         f"CAMERA_INIT: Włączono strumień głębi (HW Align): {depth_profile}",
#                         self._message_logger,
#                     )
#                     debug(
#                         f"CAMERA_INIT: Włączono strumień koloru (HW Align): {color_profile}",
#                         self._message_logger,
#                     )
#                     info(
#                         f"CAMERA_INIT: ✅ Sprzętowe wyrównanie zostało pomyślnie skonfigurowane dla żądanego profilu",
#                         self._message_logger,
#                     )
#                     hardware_align_configured = True

#             except Exception as hw_align_error:
#                 error(
#                     f"CAMERA_INIT: Błąd podczas analizy sprzętowego wyrównania: {hw_align_error}. Przełączam na programowe wyrównanie.",
#                     self._message_logger,
#                 )
#                 use_hardware_align = False

#         # Konfiguracja programowego wyrównania lub niezależnych strumieni
#         if not hardware_align_configured:
#             info(
#                 f"CAMERA_INIT: Konfiguracja programowego wyrównania lub niezależnych strumieni",
#                 self._message_logger,
#             )

#             # Utwórz programowy filtr wyrównujący jeśli wymagany
#             if camera_settings.get("align", True):
#                 self.align_filter = AlignFilter(OBStreamType.COLOR_STREAM)
#                 debug(
#                     f"CAMERA_INIT: Utworzono programowy filtr wyrównujący do strumienia koloru",
#                     self._message_logger,
#                 )

#             # Konfiguruj strumień koloru niezależnie
#             if not color_profile:  # Jeśli wcześniej nie znaleziono profilu
#                 color_profile_list = self.camera_pipeline.get_stream_profile_list(
#                     OBSensorType.COLOR_SENSOR
#                 )
#                 color_format = getattr(OBFormat, color_settings.get("format", "MJPG"))
#                 color_profile = color_profile_list.get_video_stream_profile(
#                     color_settings.get("width", 640),
#                     color_settings.get("height", 400),
#                     color_format,
#                     color_settings.get("fps", 30),
#                 )

#             if color_profile:
#                 self.camera_config.enable_stream(color_profile)
#                 debug(
#                     f"CAMERA_INIT: Włączono strumień koloru (SW): {color_profile}",
#                     self._message_logger,
#                 )
#             else:
#                 error(
#                     f"CAMERA_INIT: Nie znaleziono pasującego profilu koloru dla programowego wyrównania.",
#                     self._message_logger,
#                 )

#             # Konfiguruj strumień głębi niezależnie
#             depth_profile_list = self.camera_pipeline.get_stream_profile_list(
#                 OBSensorType.DEPTH_SENSOR
#             )
#             depth_format = getattr(OBFormat, depth_settings.get("format", "Y16"))
#             depth_profile = depth_profile_list.get_video_stream_profile(
#                 depth_settings.get("width", 640),
#                 depth_settings.get("height", 400),
#                 depth_format,
#                 depth_settings.get("fps", 30),
#             )
#             if depth_profile:
#                 self.camera_config.enable_stream(depth_profile)
#                 debug(
#                     f"CAMERA_INIT: Włączono strumień głębi (SW): {depth_profile}",
#                     self._message_logger,
#                 )
#             else:
#                 error(
#                     f"CAMERA_INIT: Nie znaleziono pasującego profilu głębi dla programowego wyrównania.",
#                     self._message_logger,
#                 )

#         # MARK: FILTERS
#         filter_settings = camera_settings.get("filters", {})
#         if filter_settings.get("spatial", {}).get("enable", False):
#             self.spatial_filter = SpatialAdvancedFilter()
#             debug(f"CAMERA_INIT: Włączono filtr przestrzenny", self._message_logger)
#         if filter_settings.get("temporal", {}).get("enable", False):
#             self.temporal_filter = TemporalFilter()
#             debug(f"CAMERA_INIT: Włączono filtr czasowy", self._message_logger)

#         info(
#             f"CAMERA_INIT: Konfiguracja kamery {self.name} została zakończona",
#             self._message_logger,
#         )

#         # event.result = Result(status="success")
#         # await self._reply(event)

# def _start_camera(self):
#     if self.camera_pipeline is None:
#         error(
#             "CAMERA_INIT: Pipeline nie został zainicjalizowany",
#             self._message_logger,
#         )
#         raise ValueError("Pipeline nie został zainicjalizowany")

#     if self.camera_config is None:
#         error(
#             "CAMERA_INIT: Config nie został zainicjalizowany", self._message_logger
#         )
#         raise ValueError("Config nie został zainicjalizowany")

#     self.camera_pipeline.start(self.camera_config)
#     self.camera_running = True

# def _stop_camera(self):
#     """
#     Stop camera:
#     - stop pipeline
#     """
#     self.camera_running = False
#     self.camera_pipeline.stop()

#     # Clear frame buffers
#     self.latest_color_frame = None
#     self.latest_depth_frame = None
#     self.last_color_timestamp = 0
#     self.last_depth_timestamp = 0

# def _process_frames(self, frames):
# """
# Process frames with frame synchronization buffering
# """

# rois = []
# try:
#     frame_color = frames.get_color_frame()
#     frame_depth = frames.get_depth_frame()

#     current_time = time.time() * 1000  # Convert to milliseconds

#     # Update buffers with new frames
#     if frame_color is not None:
#         self.latest_color_frame = frame_color
#         self.last_color_timestamp = current_time
#         debug(
#             f"Nowa ramka kolorowa zapisana w buforze (timestamp: {current_time:.0f})",
#             self._message_logger,
#         )

#     if frame_depth is not None:
#         self.latest_depth_frame = frame_depth
#         self.last_depth_timestamp = current_time
#         debug(
#             f"Nowa ramka głębi zapisana w buforze (timestamp: {current_time:.0f})",
#             self._message_logger,
#         )

#     # Debug: sprawdź dostępność ramek
#     debug(
#         f"Frame check - color: {frame_color is not None}, depth: {frame_depth is not None}",
#         self._message_logger,
#     )
#     debug(
#         f"Buffer status - color: {self.latest_color_frame is not None}, depth: {self.latest_depth_frame is not None}",
#         self._message_logger,
#     )

#     # Try to sync frames using buffers
#     use_color_frame = self.latest_color_frame
#     use_depth_frame = self.latest_depth_frame

#     if use_color_frame is None or use_depth_frame is None:
#         debug(
#             f"Brak ramek w buforach - color: {use_color_frame is not None}, depth: {use_depth_frame is not None}",
#             self._message_logger,
#         )
#         return rois

#     # Check if frames are reasonably synchronized
#     time_diff = abs(self.last_color_timestamp - self.last_depth_timestamp)
#     if time_diff > self.frame_sync_timeout:
#         debug(
#             f"Ramki zbyt desynchronizowane: różnica {time_diff:.0f}ms (limit: {self.frame_sync_timeout}ms)",
#             self._message_logger,
#         )
#         # Still try to process, but warn about sync
#         info(
#             f"Przetwarzanie desynchronizowanych ramek (różnica: {time_diff:.0f}ms)",
#             self._message_logger,
#         )

#     # Process color frame
#     color_image = None
#     if use_color_frame.get_format() == OBFormat.MJPG:
#         debug(
#             f"Dekodowanie MJPG ramki kolorowej {use_color_frame.get_width()}x{use_color_frame.get_height()}",
#             self._message_logger,
#         )
#         color_image = cv2.imdecode(use_color_frame.get_data(), cv2.IMREAD_COLOR)
#         if color_image is None:
#             error(
#                 f"Błąd dekodowania MJPG ramki kolorowej", self._message_logger
#             )
#             # Try to interpret as raw data
#             try:
#                 color_image = use_color_frame.get_data().reshape((
#                     use_color_frame.get_height(),
#                     use_color_frame.get_width(),
#                     3,
#                 ))
#                 debug(
#                     f"Użyto fallback raw data dla ramki kolorowej",
#                     self._message_logger,
#                 )
#             except Exception as fallback_error:
#                 error(
#                     f"Fallback raw data też zawiódł: {fallback_error}",
#                     self._message_logger,
#                 )
#                 return rois
#     else:
#         color_image = cv2.cvtColor(
#             use_color_frame.get_data().reshape((
#                 use_color_frame.get_height(),
#                 use_color_frame.get_width(),
#                 3,
#             )),
#             cv2.COLOR_RGB2BGR,
#         )

#     # Process depth frame
#     debug(
#         f"Przetwarzanie ramki głębi z bufora {use_depth_frame.get_width()}x{use_depth_frame.get_height()}",
#         self._message_logger,
#     )
#     depth_data = np.frombuffer(
#         bytes(use_depth_frame.get_data()), dtype=np.uint16
#     )
#     depth_image = depth_data.reshape((
#         use_depth_frame.get_height(),
#         use_depth_frame.get_width(),
#     ))

#     # Create ROIs from synchronized frames
#     if color_image is not None and depth_image is not None:
#         debug(
#             f"Tworzenie ROI z zsynchronizowanych ramek - {len(self._configuration['rois'])} regionów",
#             self._message_logger,
#         )
#         for i, roi_config in enumerate(self._configuration["rois"]):
#             roi_color = self._image_crop(color_image, roi_config)
#             roi_depth = self._image_crop(depth_image, roi_config)
#             rois.append({"color": roi_color, "depth": roi_depth})
#         info(
#             f"Utworzono {len(rois)} ROI z zsynchronizowanych ramek (sync diff: {time_diff:.0f}ms)",
#             self._message_logger,
#         )
#     else:
#         error(
#             f"Błąd tworzenia obrazów z zsynchronizowanych ramek",
#             self._message_logger,
#         )

#     return rois
# except Exception as e:
#     error(f"Błąd przetwarzania ramek: {e}", self._message_logger)
#     error(f"Traceback: {traceback.format_exc()}", self._message_logger)
#     return rois

# def _image_crop(self, image, config):
#     """
#     Crop image
#     config:
#     {
#         "crop_x": (x1, x2),
#         "crop_y": (y1, y2)
#     }
#     """
#     return image[config["y"][0] : config["y"][1], config["x"][0] : config["x"][1]]
