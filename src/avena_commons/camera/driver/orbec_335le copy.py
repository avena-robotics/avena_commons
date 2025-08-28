import asyncio
import threading
import time
import traceback
from enum import Enum, auto
from typing import Optional

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

# from pymodbus.client import ModbusTcpClient
from avena_commons.util.logger import MessageLogger, debug, error, info
from avena_commons.util.worker import Connector, Worker


class CameraState(Enum):
    IDLE = 0  # idle
    INITIALIZING = 1  # init camera
    INITIALIZED = 2  # init camera
    STARTING = 3  # start camera pipeline
    STARTED = 4  # start camera pipeline
    STOPPING = 6  # stop camera pipeline
    STOPPED = 7  # stop camera pipeline
    SHUTDOWN = 8  # stop camera pipeline
    ERROR = 255  # error


class OrbecGemini335LeWorker(Worker):
    def __init__(self, camera_ip: str, message_logger: Optional[MessageLogger] = None):
        self.__camera_ip = camera_ip
        # NIE przechowuj MessageLogger - zostanie przekazany przez args w _run
        self._message_logger = None
        self.device_name = f"OrbecGemini335Le_{camera_ip}"
        # Przekaż None do super() - logger zostanie ustawiony w _run
        super().__init__(message_logger=None)
        self.state = CameraState.IDLE

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

    async def init(self, camera_settings: dict):
        """Initialize camera connection and resources"""
        try:
            self.state = CameraState.INITIALIZING
            debug(f"{self.device_name} - Initializing camera", self._message_logger)
            # Tu będzie inicjalizacja kamery Orbbec

            """
            Init camera:
            - find device by ip
            - create pipeline
            - create config
            - enable stream
            - enable settings
            """

            # camera_settings = configuration
            color_settings = camera_settings.get("color", {})
            depth_settings = camera_settings.get("depth", {})

            ctx = Context()
            try:
                dev = ctx.create_net_device(self.__camera_ip, 8090)
                debug(
                    f"CAMERA_INIT: Otwarta kamera na ip {self.__camera_ip}",
                    self._message_logger,
                )
                debug(
                    f"CAMERA_INIT: camera info: {dev.get_device_info()}",
                    self._message_logger,
                )
            except Exception as e:
                error(
                    f"CAMERA_INIT: Błąd podczas otwierania kamery na ip {self.__camera_ip}: {e}",
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
                        f"CAMERA_INIT: Przesunięcie wyszukiwania dysparycji nie jest obsługiwane w kamerze",
                        self._message_logger,
                    )
                else:
                    disparity_offset = disparity_settings.get("search_offset")
                    if disparity_offset and disparity_offset > 0:
                        dev.set_int_property(offset_pid, disparity_offset)
                        debug(
                            f"CAMERA_INIT: Ustawiono przesunięcie wyszukiwania dysparycji na {disparity_offset}",
                            self._message_logger,
                        )
            except AttributeError as e:
                error(
                    f"CAMERA_INIT: Używana wersja pyorbbecsdk nie obsługuje zmiany trybu dysparycji. Wymagana jest wersja >= 2.2.x. Ta funkcja zostanie pominięta. Błąd: {e}",
                    self._message_logger,
                )

            self.camera_pipeline = Pipeline(dev)
            self.camera_config = Config()

            # MARK: SETTINGS
            color_exposure = color_settings.get("exposure", 500)
            dev.set_int_property(
                OBPropertyID.OB_PROP_COLOR_EXPOSURE_INT, color_exposure
            )
            debug(
                f"CAMERA_INIT: Ustawiono OB_PROP_COLOR_EXPOSURE_INT na {color_exposure}",
                self._message_logger,
            )

            color_gain = color_settings.get("gain", 10)
            dev.set_int_property(OBPropertyID.OB_PROP_COLOR_GAIN_INT, color_gain)
            debug(
                f"CAMERA_INIT: Ustawiono OB_PROP_COLOR_GAIN_INT na {color_gain}",
                self._message_logger,
            )

            color_white_balance = color_settings.get("white_balance", 4000)
            dev.set_int_property(
                OBPropertyID.OB_PROP_COLOR_WHITE_BALANCE_INT, color_white_balance
            )
            debug(
                f"CAMERA_INIT: Ustawiono OB_PROP_COLOR_WHITE_BALANCE_INT na {color_white_balance}",
                self._message_logger,
            )

            # Depth stream settings
            depth_exposure = depth_settings.get("exposure", 500)
            dev.set_int_property(
                OBPropertyID.OB_PROP_DEPTH_EXPOSURE_INT, depth_exposure
            )
            debug(
                f"CAMERA_INIT: Ustawiono OB_PROP_DEPTH_EXPOSURE_INT na {depth_exposure}",
                self._message_logger,
            )

            depth_gain = depth_settings.get("gain", 10)
            dev.set_int_property(OBPropertyID.OB_PROP_DEPTH_GAIN_INT, depth_gain)
            debug(
                f"CAMERA_INIT: Ustawiono OB_PROP_DEPTH_GAIN_INT na {depth_gain}",
                self._message_logger,
            )

            laser_power = depth_settings.get("laser_power", 5)
            dev.set_int_property(
                OBPropertyID.OB_PROP_LASER_POWER_LEVEL_CONTROL_INT, laser_power
            )
            debug(
                f"CAMERA_INIT: Ustawiono OB_PROP_LASER_POWER_LEVEL_CONTROL_INT na {laser_power}",
                self._message_logger,
            )

            # Disparity
            disparity_to_depth = camera_settings.get("disparity_to_depth", True)
            dev.set_bool_property(
                OBPropertyID.OB_PROP_DISPARITY_TO_DEPTH_BOOL, disparity_to_depth
            )
            debug(
                f"CAMERA_INIT: Ustawiono OB_PROP_DISPARITY_TO_DEPTH_BOOL na {disparity_to_depth}",
                self._message_logger,
            )

            # MARK: PROFILES & ALIGNMENT
            use_hardware_align = camera_settings.get("align", True)

            # Najpierw pobierz dostępne profile bez ustawiania trybu wyrównania
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
                        f"CAMERA_INIT: Nieznany format koloru: {color_settings.get('format', 'BGR')} - używam BGR",
                        self._message_logger,
                    )
                    color_format = OBFormat.BGR  # Ustaw domyślny format

            width = color_settings.get("width", 640)
            height = color_settings.get("height", 400)
            fps = color_settings.get("fps", 30)

            debug(
                f"CAMERA_INIT: Wyszukuję profil koloru dla {width}x{height}@{fps} {color_format}",
                self._message_logger,
            )
            color_profile = color_profile_list.get_video_stream_profile(
                width, height, color_format, fps
            )

            if not color_profile:
                error(
                    f"CAMERA_INIT: Nie znaleziono pasującego profilu koloru dla {width}x{height}@{fps} {color_format}",
                    self._message_logger,
                )
                # Spróbuj z domyślnymi parametrami jako fallback
                debug(
                    "CAMERA_INIT: Próbuję z domyślnymi parametrami profilu",
                    self._message_logger,
                )
                color_profile = color_profile_list.get_video_stream_profile(
                    640, 400, OBFormat.MJPG, 30
                )
                if not color_profile:
                    error(
                        "CAMERA_INIT: Nie można znaleźć żadnego profilu koloru",
                        self._message_logger,
                    )
                    self.state = CameraState.ERROR
                    raise ValueError("Brak dostępnych profili koloru")

            # Sprawdź czy sprzętowe wyrównanie jest obsługiwane dla tego profilu
            hardware_align_configured = False
            if use_hardware_align and color_profile:
                try:
                    debug(
                        f"CAMERA_INIT: Sprawdzam dostępność sprzętowego wyrównania dla profilu {width}x{height}@{fps} {color_format}",
                        self._message_logger,
                    )

                    # DODAJ DIAGNOSTYKĘ WSZYSTKICH DOSTĘPNYCH KOMBINACJI
                    info(
                        f"CAMERA_INIT: === ANALIZA OBSŁUGI SPRZĘTOWEGO WYRÓWNANIA D2C ===",
                        self._message_logger,
                    )

                    # Pobierz wszystkie dostępne profile koloru
                    supported_hw_combinations = []

                    debug(
                        f"CAMERA_INIT: Sprawdzanie wszystkich dostępnych profili koloru...",
                        self._message_logger,
                    )

                    # # DODAJ DIAGNOSTYKĘ WSZYSTKICH DOSTĘPNYCH PROFILI
                    # info(
                    #     f"CAMERA_INIT: === LISTA WSZYSTKICH DOSTĘPNYCH PROFILI KOLORU ===",
                    #     self._message_logger,
                    # )

                    # # Sprawdź wszystkie dostępne formaty
                    # available_formats = [
                    #     OBFormat.MJPG,
                    #     OBFormat.BGR,
                    #     OBFormat.RGB,
                    #     OBFormat.YUYV,
                    # ]
                    # available_resolutions = [
                    #     (640, 400),
                    #     (640, 480),
                    #     (1280, 720),
                    #     (1280, 800),
                    # ]
                    # available_fps = [15, 30, 60]

                    # total_profiles_found = 0
                    # for format_type in available_formats:
                    #     for width, height in available_resolutions:
                    #         for fps in available_fps:
                    #             try:
                    #                 test_profile = (
                    #                     color_profile_list.get_video_stream_profile(
                    #                         width, height, format_type, fps
                    #                     )
                    #                 )
                    #                 if test_profile:
                    #                     total_profiles_found += 1
                    #                     info(
                    #                         f"CAMERA_INIT: Dostępny profil: {width}x{height}@{fps} {format_type}",
                    #                         self._message_logger,
                    #                     )
                    #             except:
                    #                 pass  # Profil niedostępny

                    # info(
                    #     f"CAMERA_INIT: Znaleziono łącznie {total_profiles_found} dostępnych profili koloru",
                    #     self._message_logger,
                    # )

                    # # Sprawdź różne kombinacje rozdzielczości i formatów
                    # test_combinations = [
                    #     # Popularne rozdzielczości
                    #     {
                    #         "width": 640,
                    #         "height": 400,
                    #         "fps": 30,
                    #         "format": OBFormat.MJPG,
                    #     },
                    #     {
                    #         "width": 640,
                    #         "height": 400,
                    #         "fps": 30,
                    #         "format": OBFormat.BGR,
                    #     },
                    #     {
                    #         "width": 640,
                    #         "height": 400,
                    #         "fps": 15,
                    #         "format": OBFormat.MJPG,
                    #     },
                    #     {
                    #         "width": 1280,
                    #         "height": 720,
                    #         "fps": 30,
                    #         "format": OBFormat.MJPG,
                    #     },
                    #     {
                    #         "width": 1280,
                    #         "height": 720,
                    #         "fps": 15,
                    #         "format": OBFormat.MJPG,
                    #     },
                    #     {
                    #         "width": 1280,
                    #         "height": 800,
                    #         "fps": 30,
                    #         "format": OBFormat.MJPG,
                    #     },
                    #     {
                    #         "width": 1280,
                    #         "height": 800,
                    #         "fps": 15,
                    #         "format": OBFormat.MJPG,
                    #     },
                    # ]

                    # for combo in test_combinations:
                    #     try:
                    #         # Spróbuj znaleźć profil dla tej kombinacji
                    #         test_color_profile = (
                    #             color_profile_list.get_video_stream_profile(
                    #                 combo["width"],
                    #                 combo["height"],
                    #                 combo["format"],
                    #                 combo["fps"],
                    #             )
                    #         )

                    #         if test_color_profile:
                    #             # Sprawdź czy ten profil koloru obsługuje sprzętowe D2C
                    #             test_hw_d2c_list = (
                    #                 self.camera_pipeline.get_d2c_depth_profile_list(
                    #                     test_color_profile, OBAlignMode.HW_MODE
                    #                 )
                    #             )

                    #             profile_info = f"{combo['width']}x{combo['height']}@{combo['fps']} {combo['format']}"

                    #             if test_hw_d2c_list and len(test_hw_d2c_list) > 0:
                    #                 supported_hw_combinations.append({
                    #                     "color_profile": test_color_profile,
                    #                     "depth_profiles": test_hw_d2c_list,
                    #                     "info": profile_info,
                    #                 })

                    #                 info(
                    #                     f"CAMERA_INIT: ✅ SPRZĘTOWE D2C OBSŁUGIWANE - Color: {profile_info}",
                    #                     self._message_logger,
                    #                 )

                    #                 # Wylistuj dostępne profile głębi dla tej kombinacji
                    #                 for j, depth_prof in enumerate(test_hw_d2c_list):
                    #                     depth_info = f"{depth_prof.get_width()}x{depth_prof.get_height()}@{depth_prof.get_fps()} {depth_prof.get_format()}"
                    #                     info(
                    #                         f"CAMERA_INIT:   -> Compatible Depth {j}: {depth_info}",
                    #                         self._message_logger,
                    #                     )
                    #             else:
                    #                 debug(
                    #                     f"CAMERA_INIT: ❌ SPRZĘTOWE D2C NIEOBSŁUGIWANE - Color: {profile_info}",
                    #                     self._message_logger,
                    #                 )
                    #         else:
                    #             debug(
                    #                 f"CAMERA_INIT: Profil niedostępny - Color: {combo['width']}x{combo['height']}@{combo['fps']} {combo['format']}",
                    #                 self._message_logger,
                    #             )

                    #     except Exception as test_error:
                    #         debug(
                    #             f"CAMERA_INIT: Błąd testowania kombinacji {combo}: {test_error}",
                    #             self._message_logger,
                    # )

                    # Podsumowanie
                    if supported_hw_combinations:
                        info(
                            f"CAMERA_INIT: === PODSUMOWANIE OBSŁUGIWANYCH KOMBINACJI ({len(supported_hw_combinations)}) ===",
                            self._message_logger,
                        )

                        # Grupuj po rozdzielczości dla lepszej czytelności
                        resolution_groups = {}
                        for combo in supported_hw_combinations:
                            prof = combo["color_profile"]
                            res_key = f"{prof.get_width()}x{prof.get_height()}"
                            if res_key not in resolution_groups:
                                resolution_groups[res_key] = []
                            resolution_groups[res_key].append(combo)

                        for resolution, combos in resolution_groups.items():
                            info(
                                f"CAMERA_INIT: Rozdzielczość {resolution}:",
                                self._message_logger,
                            )
                            for combo in combos:
                                prof = combo["color_profile"]
                                info(
                                    f"CAMERA_INIT:   - {prof.get_fps()}fps {prof.get_format()} ({len(combo['depth_profiles'])} depth profiles)",
                                    self._message_logger,
                                )

                        # Znajdź najwyższą obsługiwaną rozdzielczość
                        max_pixels = 0
                        best_combo = None
                        for combo in supported_hw_combinations:
                            prof = combo["color_profile"]
                            pixels = prof.get_width() * prof.get_height()
                            if pixels > max_pixels:
                                max_pixels = pixels
                                best_combo = combo

                        if best_combo:
                            best_prof = best_combo["color_profile"]
                            info(
                                f"CAMERA_INIT: 🏆 NAJWYŻSZA OBSŁUGIWANA ROZDZIELCZOŚĆ: {best_prof.get_width()}x{best_prof.get_height()}@{best_prof.get_fps()} {best_prof.get_format()}",
                                self._message_logger,
                            )

                            # Pokaż przykładową konfigurację JSON
                            info(
                                f"CAMERA_INIT: === PRZYKŁADOWA KONFIGURACJA JSON ===",
                                self._message_logger,
                            )
                            example_depth = best_combo["depth_profiles"][0]
                            format_name = str(best_prof.get_format()).replace(
                                "OBFormat.", ""
                            )
                            depth_format_name = str(example_depth.get_format()).replace(
                                "OBFormat.", ""
                            )

                            info(f"CAMERA_INIT: {best_combo}", self._message_logger)
                    else:
                        error(
                            f"CAMERA_INIT: ❌ BRAK OBSŁUGIWANYCH KOMBINACJI dla sprzętowego D2C",
                            self._message_logger,
                        )
                        info(
                            f"CAMERA_INIT: Ta kamera może nie obsługiwać sprzętowego wyrównania lub wymaga aktualizacji firmware",
                            self._message_logger,
                        )

                    info(
                        f"CAMERA_INIT: === KONIEC ANALIZY D2C ===",
                        self._message_logger,
                    )

                    # Teraz sprawdź oryginalnie żądany profil
                    hw_d2c_profile_list = (
                        self.camera_pipeline.get_d2c_depth_profile_list(
                            color_profile, OBAlignMode.HW_MODE
                        )
                    )
                    if not hw_d2c_profile_list or len(hw_d2c_profile_list) == 0:
                        info(
                            f"CAMERA_INIT: Żądany profil {width}x{height}@{fps} {color_format} NIE OBSŁUGUJE sprzętowego wyrównania. Przełączam na programowe.",
                            self._message_logger,
                        )
                        use_hardware_align = False
                    else:
                        # Sprzętowe wyrównanie jest obsługiwane dla żądanego profilu
                        self.camera_config.set_align_mode(OBAlignMode.HW_MODE)
                        depth_profile = hw_d2c_profile_list[0]

                        self.camera_config.enable_stream(depth_profile)
                        self.camera_config.enable_stream(color_profile)

                        debug(
                            f"CAMERA_INIT: Włączono strumień głębi (HW Align): {depth_profile}",
                            self._message_logger,
                        )
                        debug(
                            f"CAMERA_INIT: Włączono strumień koloru (HW Align): {color_profile}",
                            self._message_logger,
                        )
                        info(
                            f"CAMERA_INIT: ✅ Sprzętowe wyrównanie zostało pomyślnie skonfigurowane dla żądanego profilu",
                            self._message_logger,
                        )
                        hardware_align_configured = True

                except Exception as hw_align_error:
                    error(
                        f"CAMERA_INIT: Błąd podczas analizy sprzętowego wyrównania: {hw_align_error}. Przełączam na programowe wyrównanie.",
                        self._message_logger,
                    )
                    use_hardware_align = False

            # Konfiguracja programowego wyrównania lub niezależnych strumieni
            if not hardware_align_configured:
                info(
                    f"CAMERA_INIT: Konfiguracja programowego wyrównania lub niezależnych strumieni",
                    self._message_logger,
                )

                # Utwórz programowy filtr wyrównujący jeśli wymagany
                if camera_settings.get("align", True):
                    self.align_filter = AlignFilter(OBStreamType.COLOR_STREAM)
                    debug(
                        f"CAMERA_INIT: Utworzono programowy filtr wyrównujący do strumienia koloru",
                        self._message_logger,
                    )

                # Konfiguruj strumień koloru niezależnie
                if not color_profile:  # Jeśli wcześniej nie znaleziono profilu
                    color_profile_list = self.camera_pipeline.get_stream_profile_list(
                        OBSensorType.COLOR_SENSOR
                    )
                    color_format = getattr(
                        OBFormat, color_settings.get("format", "MJPG")
                    )
                    color_profile = color_profile_list.get_video_stream_profile(
                        color_settings.get("width", 640),
                        color_settings.get("height", 400),
                        color_format,
                        color_settings.get("fps", 30),
                    )

                if color_profile:
                    self.camera_config.enable_stream(color_profile)
                    debug(
                        f"CAMERA_INIT: Włączono strumień koloru (SW): {color_profile}",
                        self._message_logger,
                    )
                else:
                    error(
                        f"CAMERA_INIT: Nie znaleziono pasującego profilu koloru dla programowego wyrównania.",
                        self._message_logger,
                    )

                # Konfiguruj strumień głębi niezależnie
                depth_profile_list = self.camera_pipeline.get_stream_profile_list(
                    OBSensorType.DEPTH_SENSOR
                )
                depth_format = getattr(OBFormat, depth_settings.get("format", "Y16"))
                depth_profile = depth_profile_list.get_video_stream_profile(
                    depth_settings.get("width", 640),
                    depth_settings.get("height", 400),
                    depth_format,
                    depth_settings.get("fps", 30),
                )
                if depth_profile:
                    self.camera_config.enable_stream(depth_profile)
                    debug(
                        f"CAMERA_INIT: Włączono strumień głębi (SW): {depth_profile}",
                        self._message_logger,
                    )
                else:
                    error(
                        f"CAMERA_INIT: Nie znaleziono pasującego profilu głębi dla programowego wyrównania.",
                        self._message_logger,
                    )

            # MARK: FILTERS
            filter_settings = camera_settings.get("filters", {})
            if filter_settings.get("spatial", {}).get("enable", False):
                self.spatial_filter = SpatialAdvancedFilter()
                debug(f"CAMERA_INIT: Włączono filtr przestrzenny", self._message_logger)
            if filter_settings.get("temporal", {}).get("enable", False):
                self.temporal_filter = TemporalFilter()
                debug(f"CAMERA_INIT: Włączono filtr czasowy", self._message_logger)

            info(
                f"CAMERA_INIT: Konfiguracja kamery została zakończona",
                self._message_logger,
            )
            self.state = CameraState.INITIALIZED
            return True
        except Exception as e:
            error(f"{self.device_name} - Init failed: {e}", self._message_logger)
            self.state = CameraState.ERROR
            return False

    async def start(self):
        """Start camera frame grabbing"""
        try:
            self.state = CameraState.STARTING
            debug(f"{self.device_name} - Starting camera", self._message_logger)
            # Tu będzie inicjalizacja kamery Orbbec
            if self.camera_pipeline is None:
                error(
                    "CAMERA_INIT: Pipeline nie został zainicjalizowany",
                    self._message_logger,
                )
                raise ValueError("Pipeline nie został zainicjalizowany")

            if self.camera_config is None:
                error(
                    "CAMERA_INIT: Config nie został zainicjalizowany",
                    self._message_logger,
                )
                raise ValueError("Config nie został zainicjalizowany")

            self.camera_pipeline.start(self.camera_config)
            self.state = CameraState.STARTED
            return True
        except Exception as e:
            self.state = CameraState.ERROR
            error(f"{self.device_name} - Starting failed: {e}", self._message_logger)
            return False

    async def stop(self):
        """Stop camera frame grabbing"""
        try:
            self.state = CameraState.STOPPING
            debug(f"{self.device_name} - Stopping camera", self._message_logger)
            # Tu będzie logika stopowania grabowania
            self.camera_pipeline.stop()
            self.state = CameraState.STOPPED
            return True
        except Exception as e:
            self.state = CameraState.ERROR
            error(f"{self.device_name} - Stopping failed: {e}", self._message_logger)
            return False

    def _process_frames(self, frames):
        """
        Process frames with frame synchronization buffering
        """
        rois = []
        try:
            # Sprawdź typ obiektu frames po przetworzeniu przez filtry
            if hasattr(frames, "get_color_frame"):
                # To jest FrameSet
                frame_color = frames.get_color_frame()
                frame_depth = frames.get_depth_frame()
                debug(f"Przetwarzanie FrameSet", self._message_logger)
            elif hasattr(frames, "as_color_frame"):
                # To jest Frame (po przetworzeniu przez filtry)
                frame_color = frames.as_color_frame()
                frame_depth = frames.as_depth_frame()
                debug(f"Przetwarzanie Frame (po filtrach)", self._message_logger)
            else:
                error(f"Nieznany typ frames: {type(frames)}", self._message_logger)
                return rois

            current_time = time.time() * 1000  # Convert to milliseconds

            # Sprawdź czy ramki istnieją
            if frame_color is None:
                debug("Brak ramki kolorowej", self._message_logger)
                return rois

            if frame_depth is None:
                debug("Brak ramki głębi", self._message_logger)
                return rois

            debug(
                f"Ramka kolorowa: {frame_color.get_width()}x{frame_color.get_height()}, format: {frame_color.get_format()}",
                self._message_logger,
            )
            debug(
                f"Ramka głębi: {frame_depth.get_width()}x{frame_depth.get_height()}, format: {frame_depth.get_format()}",
                self._message_logger,
            )

            # Process color frame
            color_image = None
            if frame_color.get_format() == OBFormat.MJPG:
                debug(
                    f"Dekodowanie MJPG ramki kolorowej {frame_color.get_width()}x{frame_color.get_height()}",
                    self._message_logger,
                )
                import cv2
                import numpy as np

                color_data = frame_color.get_data()
                color_image = cv2.imdecode(
                    np.frombuffer(color_data, np.uint8), cv2.IMREAD_COLOR
                )

                if color_image is None:
                    error(
                        f"Błąd dekodowania MJPG ramki kolorowej", self._message_logger
                    )
                    return rois
            else:
                # BGR/RGB format
                import cv2
                import numpy as np

                color_data = frame_color.get_data()
                color_image = np.frombuffer(color_data, dtype=np.uint8).reshape((
                    frame_color.get_height(),
                    frame_color.get_width(),
                    3,
                ))

                if frame_color.get_format() == OBFormat.RGB:
                    color_image = cv2.cvtColor(color_image, cv2.COLOR_RGB2BGR)

            # Process depth frame
            debug(
                f"Przetwarzanie ramki głębi {frame_depth.get_width()}x{frame_depth.get_height()}",
                self._message_logger,
            )
            import numpy as np

            depth_data = frame_depth.get_data()
            depth_image = np.frombuffer(depth_data, dtype=np.uint16).reshape((
                frame_depth.get_height(),
                frame_depth.get_width(),
            ))

            debug(
                f"Utworzono obrazy - color: {color_image.shape if color_image is not None else None}, depth: {depth_image.shape}",
                self._message_logger,
            )

            return {"color": color_image, "depth": depth_image}

        except Exception as e:
            error(f"Błąd przetwarzania ramek: {e}", self._message_logger)
            error(f"Traceback: {traceback.format_exc()}", self._message_logger)
            return rois

    async def _run(self, pipe_in):
        # Utwórz nowy MessageLogger w tym procesie (nie przekazuj przez pipe)
        from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger

        # Utwórz lokalny logger dla tego procesu
        self._message_logger = MessageLogger(
            filename=f"temp/camera_worker_{self.__camera_ip}.log",
            debug=True,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=10,
            colors=False,
        )

        debug(
            f"{self.device_name} - Worker started with local logger",
            self._message_logger,
        )

        try:
            while True:
                if pipe_in.poll(0.0005):
                    data = pipe_in.recv()
                    response = None
                    match data[0]:
                        case "CAMERA_INIT":
                            try:
                                debug(
                                    f"{self.device_name} - Received CAMERA_INIT: {data[1]}",
                                    self._message_logger,
                                )
                                # Tu będzie logika inicjalizacji z konfiguracją
                                await self.init(data[1])
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error in CAMERA_INIT: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(False)

                        case "CAMERA_START_GRABBING":
                            try:
                                debug(
                                    f"{self.device_name} - Starting frame grabbing",
                                    self._message_logger,
                                )
                                # Tu będzie logika startowania grabowania
                                await self.start()
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error starting grabbing: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(False)

                        case "CAMERA_STOP_GRABBING":
                            try:
                                debug(
                                    f"{self.device_name} - Stopping OrbecGemini335LeWorker subprocess",
                                    message_logger=self._message_logger,
                                )
                                await self.stop()
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error stopping grabbing: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(False)

                        case "GET_STATE":
                            try:
                                debug(
                                    f"{self.device_name} - Getting state",
                                    message_logger=self._message_logger,
                                )
                                state = self.state
                                pipe_in.send(state)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error getting state: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(None)

                        case _:
                            error(
                                f"{self.device_name} - Unknown command: {data[0]}",
                                message_logger=self._message_logger,
                            )

                if self.state == CameraState.STARTED:
                    frames = self.camera_pipeline.wait_for_frames(3)
                    if frames is None:
                        continue

                    debug(f"Pobrano ramki: {type(frames)}", self._message_logger)

                    # Zastosuj filtry
                    if self.align_filter:
                        frames = self.align_filter.process(frames)
                        debug("Filtr wyrównania zastosowany", self._message_logger)
                    if self.spatial_filter:
                        frames = self.spatial_filter.process(frames)
                        debug("Filtr przestrzenny zastosowany", self._message_logger)
                    if self.temporal_filter:
                        frames = self.temporal_filter.process(frames)
                        debug("Filtr czasowy zastosowany", self._message_logger)

                    # # Przetwórz ramki
                    # debug("Rozpoczęcie przetwarzania ramek", self._message_logger)
                    # rois = self._process_frames(frames)
                    # debug(f"Przetworzono ramki: {rois}", self._message_logger)

        except asyncio.CancelledError:
            info(
                f"{self.device_name} - Task was cancelled",
                message_logger=self._message_logger,
            )
        except Exception as e:
            error(
                f"{self.device_name} - Error in Worker: {e}",
                message_logger=self._message_logger,
            )
            error(
                f"Traceback:\n{traceback.format_exc()}",
                message_logger=self._message_logger,
            )
        finally:
            info(
                f"{self.device_name} - Worker has shut down",
                message_logger=self._message_logger,
            )


class OrbecGemini335Le(Connector):
    def __init__(self, camera_ip: str, message_logger: Optional[MessageLogger] = None):
        self.camera_ip = camera_ip
        # NIE przekazuj MessageLogger do super() - to powoduje problem pickle
        super().__init__(message_logger=None)  # Przekaż None
        # Nie wywołuj _connect() tutaj - zrobimy to ręcznie z camera_ip
        self.__lock = threading.Lock()

        # Zachowaj lokalną referencję dla logowania w głównym procesie
        self._local_message_logger = message_logger

        # Ręcznie utwórz proces z camera_ip jako argumentem
        self._connect_with_camera_ip()

        debug(
            f"OrbecGemini335Le Connector initialized on: {camera_ip}",
            message_logger=self._local_message_logger,
        )

    def _connect_with_camera_ip(self):
        """Niestandardowa metoda _connect która przekazuje camera_ip"""
        import multiprocessing

        self._pipe_out, _pipe_in = multiprocessing.Pipe()
        self._process = multiprocessing.Process(
            target=self._run, args=(_pipe_in, self.camera_ip, None)
        )
        self._process.start()
        self.core = self._core

    def _run(self, pipe_in, camera_ip: str, message_logger=None):
        self.__lock = threading.Lock()
        worker = OrbecGemini335LeWorker(camera_ip=camera_ip, message_logger=None)
        asyncio.run(worker._run(pipe_in))

    def init(self, configuration: dict = {}):
        """
        Initialize camera with configuration.
        Przekazuj tylko serializowalne dane przez pipe.
        """
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["CAMERA_INIT", configuration]
            )
            return value

    def start(self):
        """Start camera frame grabbing"""
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["CAMERA_START_GRABBING"])
            return value

    def stop(self):
        """Stop camera frame grabbing"""
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["CAMERA_STOP_GRABBING"])
            return value

    def get_state(self):
        """Get camera state"""
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["GET_STATE"])
            return value
