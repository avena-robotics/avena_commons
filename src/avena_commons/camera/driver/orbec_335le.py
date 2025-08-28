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
    Device,
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

# class CameraState(Enum):
#     IDLE = 0  # idle
#     INITIALIZING = 1  # init camera
#     INITIALIZED = 2  # init camera
#     STARTING = 3  # start camera pipeline
#     STARTED = 4  # start camera pipeline
#     STOPPING = 6  # stop camera pipeline
#     STOPPED = 7  # stop camera pipeline
#     SHUTDOWN = 8  # stop camera pipeline
#     ERROR = 255  # error


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

    def set_int_property(self, device: Device, property_id: OBPropertyID, value: int):
        try:
            device.set_int_property(property_id, value)
            debug(
                f"Ustawiono właściwość {property_id} na {value}", self._message_logger
            )
        except Exception as e:
            error(
                f"Błąd podczas ustawiania właściwości {property_id}: {e}",
                self._message_logger,
            )
            raise e

    def set_bool_property(self, device: Device, property_id: OBPropertyID, value: bool):
        try:
            device.set_bool_property(property_id, value)
            debug(
                f"Ustawiono właściwość {property_id} na {value}", self._message_logger
            )
        except Exception as e:
            error(
                f"Błąd podczas ustawiania właściwości {property_id}: {e}",
                self._message_logger,
            )
            raise e

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

            # MARK: SETTINGS
            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_COLOR_EXPOSURE_INT,
                color_settings.get("exposure", 500),
            )
            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_COLOR_GAIN_INT,
                color_settings.get("gain", 10),
            )
            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_COLOR_WHITE_BALANCE_INT,
                color_settings.get("white_balance", 4000),
            )
            # Depth stream settings
            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_DEPTH_EXPOSURE_INT,
                depth_settings.get("exposure", 500),
            )
            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_DEPTH_GAIN_INT,
                depth_settings.get("gain", 10),
            )

            self.set_int_property(
                dev,
                OBPropertyID.OB_PROP_LASER_POWER_LEVEL_CONTROL_INT,
                depth_settings.get("laser_power", 5),
            )

            # Disparity
            self.set_bool_property(
                dev,
                OBPropertyID.OB_PROP_DISPARITY_TO_DEPTH_BOOL,
                camera_settings.get("disparity_to_depth", True),
            )

            # MARK: PROFILES & ALIGNMENT
            # use_hardware_align = camera_settings.get("align", True)

            # Najpierw pobierz dostępne profile bez ustawiania trybu wyrównania
            color_profile_list = self.camera_pipeline.get_stream_profile_list(
                OBSensorType.COLOR_SENSOR
            )
            print(f"CAMERA_INIT: Dostępne profile koloru: {color_profile_list}")

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

            width = color_settings.get("width", 1280)
            height = color_settings.get("height", 800)
            fps = color_settings.get("fps", 30)

            color_profile = color_profile_list.get_video_stream_profile(
                width, height, color_format, fps
            )

            if not color_profile:
                error(
                    f"Nie znaleziono pasującego profilu koloru dla {width}x{height}@{fps} {color_format}",
                    self._message_logger,
                )
                self.state = CameraState.ERROR
                raise ValueError("Błąd konfiguracji profilu koloru")

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
                        self.align_filter = AlignFilter(align_to_stream=OBStreamType.COLOR_STREAM)
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

            # MARK: FILTERS
            filter_settings = camera_settings.get("filters", {})
            if filter_settings.get("spatial", False):
                self.spatial_filter = SpatialAdvancedFilter()
                debug(f"CAMERA_INIT: Włączono filtr przestrzenny", self._message_logger)
            if filter_settings.get("temporal", False):
                self.temporal_filter = TemporalFilter()
                debug(f"CAMERA_INIT: Włączono filtr czasowy", self._message_logger)

            info(
                f"Konfiguracja kamery została zakończona",
                self._message_logger,
            )
            return True
        except Exception as e:
            error(f"{self.device_name} - Init failed: {e}", self._message_logger)
            return False

    async def start(self):
        """Start camera frame grabbing"""
        try:
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
            return True
        except Exception as e:
            error(f"{self.device_name} - Starting failed: {e}", self._message_logger)
            return False

    async def stop(self):
        """Stop camera frame grabbing"""
        try:
            debug(f"{self.device_name} - Stopping camera", self._message_logger)
            self.camera_pipeline.stop()
            return True
        except Exception as e:
            error(f"{self.device_name} - Stopping failed: {e}", self._message_logger)
            return False

    async def grab_frames_from_camera(self):
        """Initialize camera connection and resources"""
        try:
            # Pobierz oryginalne ramki (zawsze FrameSet)
            frames = self.camera_pipeline.wait_for_frames(3)
            if frames is None:
                return None

            debug(f"Pobrano ramki: {type(frames)}", self._message_logger)

            # ZAWSZE pobierz ramki z oryginalnego FrameSet PRZED filtrami
            frame_color = frames.get_color_frame()
            frame_depth = frames.get_depth_frame() # ← ZACHOWAJ ORYGINALNĄ

            if frame_color is None:
                debug("Brak ramki kolorowej", self._message_logger)
                return None

            if frame_depth is None:
                debug("Brak ramki głębi", self._message_logger)
                return None

            # Zastosuj filtry na kopii
            if self.align_filter:
                aligned_frames = self.align_filter.process(frames)
                aligned_frames = aligned_frames.as_frame_set()
                frame_depth = aligned_frames.get_depth_frame() # ← ZACHOWAJ ORYGINALNĄ
                debug("Filtr wyrównania zastosowany", self._message_logger)

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

            depth_data = frame_depth.get_data()

            try:
                depth_image = np.frombuffer(depth_data, dtype=np.uint16).reshape((
                    frame_depth.get_height(),
                    frame_depth.get_width(),
                ))

                debug(
                    f"Pomyślnie utworzono ramkę głębi {frame_depth.get_width()}x{frame_depth.get_height()}",
                    self._message_logger,
                )

            except ValueError as reshape_error:
                error(
                    f"ODRZUCAM RAMKĘ - błąd reshape ramki głębi: {reshape_error}. ",
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
