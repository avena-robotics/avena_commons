import asyncio
import multiprocessing
import threading
import time
import traceback
from enum import Enum, auto
from typing import Optional

import cv2
import numpy as np
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

from avena_commons.camera.driver.general import (
    CameraState,
    GeneralCameraConnector,
    GeneralCameraWorker,
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


class OrbecGemini335LeWorker(GeneralCameraWorker):
    def __init__(self, camera_ip: str, message_logger: Optional[MessageLogger] = None):
        self.__camera_ip = camera_ip
        # NIE przechowuj MessageLogger - zostanie przekazany przez args w _run
        self._message_logger = None
        self.device_name = f"OrbecGemini335Le_{camera_ip}"
        # Przekaż None do super() - logger zostanie ustawiony w _run
        super().__init__(message_logger=message_logger)

        self.align_filter = None
        self.spatial_filter = None
        self.temporal_filter = None

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
                    self._change_fsm_state(EventListenerState.ON_ERROR)
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
            # self.state = CameraState.INITIALIZED
            return True
        except Exception as e:
            error(f"{self.device_name} - Init failed: {e}", self._message_logger)
            # self.state = CameraState.ERROR
            return False

    async def start(self):
        """Start camera frame grabbing"""
        try:
            # self.state = CameraState.STARTING
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
            # self.state = CameraState.STARTED
            return True
        except Exception as e:
            # self.state = CameraState.ERROR
            error(f"{self.device_name} - Starting failed: {e}", self._message_logger)
            return False

    async def stop(self):
        """Stop camera frame grabbing"""
        try:
            # self.state = CameraState.STOPPING
            debug(f"{self.device_name} - Stopping camera", self._message_logger)
            # Tu będzie logika stopowania grabowania
            self.camera_pipeline.stop()
            # self.state = CameraState.STOPPED
            return True
        except Exception as e:
            # self.state = CameraState.ERROR
            error(f"{self.device_name} - Stopping failed: {e}", self._message_logger)
            return False

    async def grab_frames_from_camera(self):
        """Initialize camera connection and resources"""
        try:
            # Pobierz oryginalne ramki (zawsze FrameSet)
            original_frames = self.camera_pipeline.wait_for_frames(3)
            if original_frames is None:
                return None

            debug(f"Pobrano ramki: {type(original_frames)}", self._message_logger)

            # ZAWSZE pobierz ramki z oryginalnego FrameSet PRZED filtrami
            frame_color = original_frames.get_color_frame()
            original_frame_depth = (
                original_frames.get_depth_frame()
            )  # ← ZACHOWAJ ORYGINALNĄ

            if frame_color is None:
                debug("Brak ramki kolorowej", self._message_logger)
                return None

            if original_frame_depth is None:
                debug("Brak ramki głębi", self._message_logger)
                return None

            # Zastosuj filtry na kopii
            frame_depth = original_frame_depth
            if self.align_filter:
                frame_depth = self.align_filter.process(original_frames)
            #     if aligned_depth is not None:
            #         frame_depth = aligned_depth
            #         debug(
            #             "Filtr wyrównania zastosowany na ramkę głębi",
            #             self._message_logger,
            #         )

            if self.spatial_filter and frame_depth:
                frame_depth = self.spatial_filter.process(frame_depth)
                debug("Filtr przestrzenny zastosowany", self._message_logger)

            if self.temporal_filter and frame_depth:
                frame_depth = self.temporal_filter.process(frame_depth)
                debug("Filtr czasowy zastosowany", self._message_logger)

            # Sprawdzenie finalnych ramek
            if frame_color is None or frame_depth is None:
                debug("Jedna z ramek jest None po filtrach", self._message_logger)
                return None

            debug(
                f"Ramka kolorowa: format {frame_color.get_format()}",
                self._message_logger,
            )
            debug(
                f"Ramka głębi: format {frame_depth.get_format()}", self._message_logger
            )

            # Process color frame
            color_image = None
            if frame_color.get_format() == OBFormat.MJPG:
                debug(
                    f"Dekodowanie MJPG ramki kolorowej {frame_color.get_width()}x{frame_color.get_height()}",
                    self._message_logger,
                )

                color_data = frame_color.get_data()
                color_image = cv2.imdecode(
                    np.frombuffer(color_data, np.uint8), cv2.IMREAD_COLOR
                )

                if color_image is None:
                    error(
                        f"Błąd dekodowania MJPG ramki kolorowej", self._message_logger
                    )
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

            # Process depth frame - SPRAWDŹ ROZMIARY PRZED RESHAPE
            # debug(
            #     f"Przetwarzanie ramki głębi (format: {frame_depth.get_format()})",
            #     self._message_logger,
            # )

            depth_data = frame_depth.get_data()

            # Sprawdź zgodność rozmiarów
            expected_height = original_frame_depth.get_height()
            expected_width = original_frame_depth.get_width()
            expected_pixels = expected_height * expected_width
            expected_bytes = expected_pixels * 2  # uint16 = 2 bajty na piksel

            actual_bytes = len(depth_data)
            actual_pixels = actual_bytes // 2

            debug(
                f"Rozmiary ramki głębi - oczekiwane: {expected_width}x{expected_height} ({expected_pixels} pikseli, {expected_bytes} bajtów), "
                f"rzeczywiste: {actual_pixels} pikseli ({actual_bytes} bajtów)",
                self._message_logger,
            )

            # Sprawdź czy rozmiary się pokrywają
            if actual_bytes != expected_bytes:
                error(
                    f"ODRZUCAM RAMKĘ - niezgodność rozmiarów danych głębi! "
                    f"Oczekiwano {expected_bytes} bajtów dla {expected_width}x{expected_height}, "
                    f"otrzymano {actual_bytes} bajtów ({actual_pixels} pikseli). "
                    f"Format ramki: {frame_depth.get_format()}",
                    self._message_logger,
                )
                return None

            try:
                depth_image = np.frombuffer(depth_data, dtype=np.uint16).reshape((
                    expected_height,
                    expected_width,
                ))

                debug(
                    f"Pomyślnie utworzono ramkę głębi {expected_width}x{expected_height}",
                    self._message_logger,
                )

            except ValueError as reshape_error:
                error(
                    f"ODRZUCAM RAMKĘ - błąd reshape ramki głębi: {reshape_error}. "
                    f"Dane: {actual_bytes} bajtów, próba reshape na ({expected_height}, {expected_width})",
                    self._message_logger,
                )
                return None

            debug(
                f"Utworzono obrazy - color: {color_image.shape if color_image is not None else None}, depth: {depth_image.shape}",
                self._message_logger,
            )

            return {"color": color_image, "depth": depth_image}

        except Exception as e:
            error(f"Błąd przetwarzania ramek: {e}", self._message_logger)
            error(f"Traceback: {traceback.format_exc()}", self._message_logger)
            return None


class OrbecGemini335Le(GeneralCameraConnector):
    def __init__(self, camera_ip: str, message_logger: Optional[MessageLogger] = None):
        self.camera_ip = camera_ip
        super().__init__(message_logger=message_logger)
        self._pipe_out, _pipe_in = multiprocessing.Pipe()
        self._process = multiprocessing.Process(
            target=self._run, args=(_pipe_in, camera_ip, None)
        )
        self._process.start()
        # self.core = self._core

    def _run(self, pipe_in, camera_ip, message_logger=None):
        # self.__lock = threading.Lock()
        worker = OrbecGemini335LeWorker(
            camera_ip=camera_ip, message_logger=message_logger
        )
        asyncio.run(worker._run(pipe_in))
