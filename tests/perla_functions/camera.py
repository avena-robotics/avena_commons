import base64
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
    OBSensorType,
    OBStreamType,
    Pipeline,
    SpatialAdvancedFilter,
    TemporalFilter,
)

from avena_commons.event_listener import Event, EventListener, Result
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
            do_not_load_state (bool): Flag to skip loading state.

        Raises:
            ValueError: If required environment variables are missing.
        """

        if not port:
            raise ValueError(
                "Brak wymaganej zmiennej środowiskowej CAMERA_LISTENER_PORT"
            )

        self._check_local_data_frequency = 30

        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
            do_not_load_state=do_not_load_state,
        )

        debug(f"camera init", self._message_logger)
        self.camera_number = name.split("camera")[1]

        if (
            self._configuration.get("camera_ip_per_number", None) is None
            or self._configuration["camera_ip_per_number"].get(self.camera_number, None)
            is None
        ):
            error(
                f"EVENT_LISTENER_INIT: Brak konfiguracji CAMERA_IP_PER_NUMBER dla kamery {self.camera_number}",
                self._message_logger,
            )
            raise ValueError(
                f"Brak konfiguracji CAMERA_IP_PER_NUMBER dla kamery {self.camera_number}"
            )
        self.camera_address = self._configuration["camera_ip_per_number"][
            self.camera_number
        ]

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
            f"EVENT_LISTENER_INIT: Event listener kamery {self.camera_number} został zainicjalizowany dla ip {self.camera_address}",
            self._message_logger,
        )

    # MARK: ANALYZE EVENT
    async def _analyze_event(self, event: Event) -> bool:
        """
        Analyzes and routes events to the appropriate handler based on their source.

        Args:
            event (Event): The event to analyze.

        Returns:
            bool: True if the event was handled successfully, False otherwise.
        """
        if event.event_type == "camera_init":
            await self._init_camera(event)
        elif event.event_type == "camera_start":
            await self._start_camera(event)
        elif event.event_type == "camera_stop":
            self._stop_camera()

        return True

    # MARK: CHECK LOCAL DATA
    async def _check_local_data(self):
        """
        Periodically checks and processes local data, including orders, products, and system states.

        Raises:
            Exception: If an error occurs during data processing.
        """

        if self.camera_running:
            debug("Sprawdzanie lokalnych danych kamery", self._message_logger)

            # Zwiększ timeout i dodaj error handling dla czekania na ramki
            try:
                frames = self.pipeline.wait_for_frames(5000)  # 5 sekund timeout
                if frames is None:
                    error(
                        f"Timeout przy pobieraniu ramek z kamery {self.camera_number} (IP: {self.camera_address})",
                        self._message_logger,
                    )
                    return

                debug("Ramki pobrane, przetwarzanie filtrów", self._message_logger)

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

                # Przetwórz ramki
                debug("Rozpoczęcie przetwarzania ramek", self._message_logger)
                rois = self._process_frames(frames)

                if len(rois) > 0:
                    info(
                        f"Wytworzono {len(rois)} ROI, wysyłanie ramek",
                        self._message_logger,
                    )
                    await self._send_frames(rois)
                else:
                    debug(
                        "Brak ROI - sprawdź poprzednie komunikaty diagnostyczne",
                        self._message_logger,
                    )

            except Exception as pipeline_error:
                error(
                    f"Błąd pipeline kamery {self.camera_number}: {pipeline_error}",
                    self._message_logger,
                )
                error(
                    f"Kamera IP: {self.camera_address}, Port pipeline: prawdopodobnie 8090",
                    self._message_logger,
                )
                # Możliwe przyczyny: problema sieciowe, kamera offline, konflikt IP
        else:
            debug(
                "Kamera nie jest uruchomiona - pomijanie sprawdzania danych",
                self._message_logger,
            )

    # MARK: HELPER_CLASSES
    async def _init_camera(self, event: Event):
        """
        Init camera:
        - find device by ip
        - create pipeline
        - create config
        - enable stream
        - enable settings
        """

        camera_settings = self._configuration["camera_settings"]
        color_settings = camera_settings.get("color", {})
        depth_settings = camera_settings.get("depth", {})

        ctx = Context()
        try:
            dev = ctx.create_net_device(self.camera_address, 8090)
            debug(
                f"CAMERTA_INIT: Otwarta kamera {self.camera_number} na ip {self.camera_address}",
                self._message_logger,
            )
            debug(
                f"CAMERTA_INIT: camera info: {dev.get_device_info()}",
                self._message_logger,
            )
        except Exception as e:
            error(
                f"CAMERTA_INIT: Błąd podczas otwierania kamery {self.camera_number} na ip {self.camera_address}: {e}",
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
                        f"CAMERTA_INIT: Zmiana trybu zakresu dysparycji nie jest obsługiwana w kamerze {self.camera_number}. Sprawdź wersję firmware.",
                        self._message_logger,
                    )
                else:
                    # Set Disparity Range Mode
                    desired_mode_name = disparity_settings.get("range_mode")
                    if desired_mode_name:
                        current_mode = dev.get_disparity_range_mode()
                        debug(
                            f"CAMERTA_INIT: Aktualny tryb zakresu dysparycji: {current_mode.name}",
                            self._message_logger,
                        )

                        available_modes = dev.get_disparity_range_mode_list()
                        is_mode_set = False
                        available_mode_names = []
                        for i in range(available_modes.get_count()):
                            mode = available_modes.get_disparity_range_mode_by_index(i)
                            available_mode_names.append(mode.name)
                            if mode.name == desired_mode_name:
                                dev.set_disparity_range_mode(mode.name)
                                debug(
                                    f"CAMERTA_INIT: Ustawiono tryb zakresu dysparycji na {mode.name}",
                                    self._message_logger,
                                )
                                is_mode_set = True
                                break

                        if not is_mode_set:
                            error(
                                f"CAMERTA_INIT: Żądany tryb zakresu dysparycji '{desired_mode_name}' nie został znaleziony. Dostępne tryby: {available_mode_names}. Używam bieżącego: {current_mode.name}",
                                self._message_logger,
                            )

            # Set Disparity Search Offset
            offset_pid = OBPropertyID.OB_STRUCT_DISPARITY_SEARCH_OFFSET
            if not dev.is_property_supported(
                offset_pid, OBPermissionType.PERMISSION_READ_WRITE
            ):
                debug(
                    f"CAMERTA_INIT: Przesunięcie wyszukiwania dysparycji nie jest obsługiwane w kamerze {self.camera_number}",
                    self._message_logger,
                )
            else:
                disparity_offset = disparity_settings.get("search_offset")
                if disparity_offset and disparity_offset > 0:
                    dev.set_int_property(offset_pid, disparity_offset)
                    debug(
                        f"CAMERTA_INIT: Ustawiono przesunięcie wyszukiwania dysparycji na {disparity_offset}",
                        self._message_logger,
                    )
        except AttributeError:
            error(
                "CAMERTA_INIT: Używana wersja pyorbbecsdk nie obsługuje zmiany trybu dysparycji. Wymagana jest wersja >= 2.2.x. Ta funkcja zostanie pominięta.",
                self._message_logger,
            )

        self.pipeline = Pipeline(dev)
        self.camera_config = Config()

        # MARK: SETTINGS

        color_exposure = color_settings.get("exposure", 500)
        dev.set_int_property(OBPropertyID.OB_PROP_COLOR_EXPOSURE_INT, color_exposure)
        debug(
            f"CAMERTA_INIT: Ustawiono OB_PROP_COLOR_EXPOSURE_INT na {color_exposure}",
            self._message_logger,
        )

        color_gain = color_settings.get("gain", 10)
        dev.set_int_property(OBPropertyID.OB_PROP_COLOR_GAIN_INT, color_gain)
        debug(
            f"CAMERTA_INIT: Ustawiono OB_PROP_COLOR_GAIN_INT na {color_gain}",
            self._message_logger,
        )

        color_white_balance = color_settings.get("white_balance", 4000)
        dev.set_int_property(
            OBPropertyID.OB_PROP_COLOR_WHITE_BALANCE_INT, color_white_balance
        )
        debug(
            f"CAMERTA_INIT: Ustawiono OB_PROP_COLOR_WHITE_BALANCE_INT na {color_white_balance}",
            self._message_logger,
        )

        # Depth stream settings
        depth_exposure = depth_settings.get("exposure", 500)
        dev.set_int_property(OBPropertyID.OB_PROP_DEPTH_EXPOSURE_INT, depth_exposure)
        debug(
            f"CAMERTA_INIT: Ustawiono OB_PROP_DEPTH_EXPOSURE_INT na {depth_exposure}",
            self._message_logger,
        )

        depth_gain = depth_settings.get("gain", 10)
        dev.set_int_property(OBPropertyID.OB_PROP_DEPTH_GAIN_INT, depth_gain)
        debug(
            f"CAMERTA_INIT: Ustawiono OB_PROP_DEPTH_GAIN_INT na {depth_gain}",
            self._message_logger,
        )

        laser_power = depth_settings.get("laser_power", 5)
        dev.set_int_property(
            OBPropertyID.OB_PROP_LASER_POWER_LEVEL_CONTROL_INT, laser_power
        )
        debug(
            f"CAMERTA_INIT: Ustawiono OB_PROP_LASER_POWER_LEVEL_CONTROL_INT na {laser_power}",
            self._message_logger,
        )

        # Disparity
        disparity_to_depth = camera_settings.get("disparity_to_depth", True)
        dev.set_bool_property(
            OBPropertyID.OB_PROP_DISPARITY_TO_DEPTH_BOOL, disparity_to_depth
        )
        debug(
            f"CAMERTA_INIT: Ustawiono OB_PROP_DISPARITY_TO_DEPTH_BOOL na {disparity_to_depth}",
            self._message_logger,
        )

        # MARK: PROFILES & ALIGNMENT
        use_hardware_align = camera_settings.get("align", True)

        if use_hardware_align:
            self.camera_config.set_align_mode(OBAlignMode.HW_MODE)
            debug(
                f"CAMERTA_INIT: Ustawiono tryb wyrównania na HW_MODE",
                self._message_logger,
            )

            color_profile_list = self.pipeline.get_stream_profile_list(
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
                        f"CAMERTA_INIT: Nieznany format koloru: {color_settings.get('format', 'BGR')} - urzyty BGR",
                        self._message_logger,
                    )
                    # raise ValueError(f"Nieznany format koloru: {color_settings.get('format', 'BGR')}")

            width = color_settings.get("width", 640)
            height = color_settings.get("height", 400)
            fps = color_settings.get("fps", 30)

            debug(
                f"CAMERTA_INIT: Wyszukuję profil koloru dla {width}x{height}@{fps} {color_format}",
                self._message_logger,
            )
            color_profile = color_profile_list.get_video_stream_profile(
                width, height, color_format, fps
            )

            if not color_profile:
                error(
                    f"CAMERTA_INIT: Nie znaleziono pasującego profilu koloru dla {width}x{height}@{fps} {color_format}",
                    self._message_logger,
                )
                # Fallback or raise error
            else:
                hw_d2c_profile_list = self.pipeline.get_d2c_depth_profile_list(
                    color_profile, OBAlignMode.HW_MODE
                )
                if not hw_d2c_profile_list or len(hw_d2c_profile_list) == 0:
                    error(
                        f"CAMERTA_INIT: Nie znaleziono zgodnego profilu głębi dla wyrównania sprzętowego.",
                        self._message_logger,
                    )
                    use_hardware_align = False  # Fallback to software alignment
                else:
                    depth_profile = hw_d2c_profile_list[0]
                    self.camera_config.enable_stream(depth_profile)
                    debug(
                        f"CAMERTA_INIT: Włączono strumień głębi (HW Align): {depth_profile}",
                        self._message_logger,
                    )
                    self.camera_config.enable_stream(color_profile)
                    debug(
                        f"CAMERTA_INIT: Włączono strumień koloru (HW Align): {color_profile}",
                        self._message_logger,
                    )

        if not use_hardware_align:
            # Fallback or default behavior: configure streams independently
            if camera_settings.get("align", True):
                self.align_filter = AlignFilter(OBStreamType.COLOR_STREAM)
                debug(
                    f"CAMERTA_INIT: Utworzono programowy filtr wyrównujący do strumienia koloru",
                    self._message_logger,
                )

            color_profile_list = self.pipeline.get_stream_profile_list(
                OBSensorType.COLOR_SENSOR
            )
            color_format = getattr(OBFormat, color_settings.get("format", "MJPG"))
            color_profile = color_profile_list.get_video_stream_profile(
                color_settings.get("width", 640),
                color_settings.get("height", 400),
                color_format,
                color_settings.get("fps", 30),
            )
            if color_profile:
                self.camera_config.enable_stream(color_profile)
                debug(
                    f"CAMERTA_INIT: Włączono strumień koloru: {color_profile}",
                    self._message_logger,
                )
            else:
                error(
                    f"CAMERTA_INIT: Nie znaleziono pasującego profilu koloru.",
                    self._message_logger,
                )

            depth_profile_list = self.pipeline.get_stream_profile_list(
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
                    f"CAMERTA_INIT: Włączono strumień głębi: {depth_profile}",
                    self._message_logger,
                )
            else:
                error(
                    f"CAMERTA_INIT: Nie znaleziono pasującego profilu głębi.",
                    self._message_logger,
                )

        # MARK: FILTERS
        filter_settings = camera_settings.get("filters", {})
        if filter_settings.get("spatial", {}).get("enable", False):
            self.spatial_filter = SpatialAdvancedFilter()
            debug(f"CAMERTA_INIT: Włączono filtr przestrzenny", self._message_logger)
        if filter_settings.get("temporal", {}).get("enable", False):
            self.temporal_filter = TemporalFilter()
            debug(f"CAMERTA_INIT: Włączono filtr czasowy", self._message_logger)

        info(
            f"CAMERTA_INIT: Konfiguracja kamery {self.camera_number} została zakończona",
            self._message_logger,
        )

        event.result = Result(status="success")
        await self._reply(event)

    async def _start_camera(self, event: Event):
        """
        Start camera:
        - start pipeline
        """
        if self.pipeline is None:
            error(
                "CAMERTA_INIT: Pipeline nie został zainicjalizowany",
                self._message_logger,
            )
            raise ValueError("Pipeline nie został zainicjalizowany")

        if self.camera_config is None:
            error(
                "CAMERTA_INIT: Config nie został zainicjalizowany", self._message_logger
            )
            raise ValueError("Config nie został zainicjalizowany")

        self.pipeline.start(self.camera_config)
        self.camera_running = True

        event.result = Result(status="success")
        await self._reply(event)

    def _stop_camera(self):
        """
        Stop camera:
        - stop pipeline
        """
        self.camera_running = False
        self.pipeline.stop()

        # Clear frame buffers
        self.latest_color_frame = None
        self.latest_depth_frame = None
        self.last_color_timestamp = 0
        self.last_depth_timestamp = 0

    async def _send_frames(self, rois):
        """
        Send frames to server
        """
        for destination in self._configuration["destinations"]:
            print(
                "send frame to: ",
                destination,
                self._configuration["destinations"][destination]["address"],
                self._configuration["destinations"][destination]["port"],
            )
            roi = rois[self._configuration["destinations"][destination]["roi_number"]]

            await self._event(
                destination=f"{destination}",
                destination_address=self._configuration["destinations"][destination][
                    "address"
                ],
                destination_port=self._configuration["destinations"][destination][
                    "port"
                ],
                event_type="camera_frame",
                data=self._serialize_roi(roi),
                to_be_processed=False,
            )

    def _process_frames(self, frames):
        """
        Process frames with frame synchronization buffering
        """

        rois = []
        try:
            frame_color = frames.get_color_frame()
            frame_depth = frames.get_depth_frame()

            current_time = time.time() * 1000  # Convert to milliseconds

            # Update buffers with new frames
            if frame_color is not None:
                self.latest_color_frame = frame_color
                self.last_color_timestamp = current_time
                debug(
                    f"Nowa ramka kolorowa zapisana w buforze (timestamp: {current_time:.0f})",
                    self._message_logger,
                )

            if frame_depth is not None:
                self.latest_depth_frame = frame_depth
                self.last_depth_timestamp = current_time
                debug(
                    f"Nowa ramka głębi zapisana w buforze (timestamp: {current_time:.0f})",
                    self._message_logger,
                )

            # Debug: sprawdź dostępność ramek
            debug(
                f"Frame check - color: {frame_color is not None}, depth: {frame_depth is not None}",
                self._message_logger,
            )
            debug(
                f"Buffer status - color: {self.latest_color_frame is not None}, depth: {self.latest_depth_frame is not None}",
                self._message_logger,
            )

            # Try to sync frames using buffers
            use_color_frame = self.latest_color_frame
            use_depth_frame = self.latest_depth_frame

            if use_color_frame is None or use_depth_frame is None:
                debug(
                    f"Brak ramek w buforach - color: {use_color_frame is not None}, depth: {use_depth_frame is not None}",
                    self._message_logger,
                )
                return rois

            # Check if frames are reasonably synchronized
            time_diff = abs(self.last_color_timestamp - self.last_depth_timestamp)
            if time_diff > self.frame_sync_timeout:
                debug(
                    f"Ramki zbyt desynchronizowane: różnica {time_diff:.0f}ms (limit: {self.frame_sync_timeout}ms)",
                    self._message_logger,
                )
                # Still try to process, but warn about sync
                info(
                    f"Przetwarzanie desynchronizowanych ramek (różnica: {time_diff:.0f}ms)",
                    self._message_logger,
                )

            # Process color frame
            color_image = None
            if use_color_frame.get_format() == OBFormat.MJPG:
                debug(
                    f"Dekodowanie MJPG ramki kolorowej {use_color_frame.get_width()}x{use_color_frame.get_height()}",
                    self._message_logger,
                )
                color_image = cv2.imdecode(use_color_frame.get_data(), cv2.IMREAD_COLOR)
                if color_image is None:
                    error(
                        f"Błąd dekodowania MJPG ramki kolorowej", self._message_logger
                    )
                    # Try to interpret as raw data
                    try:
                        color_image = use_color_frame.get_data().reshape((
                            use_color_frame.get_height(),
                            use_color_frame.get_width(),
                            3,
                        ))
                        debug(
                            f"Użyto fallback raw data dla ramki kolorowej",
                            self._message_logger,
                        )
                    except Exception as fallback_error:
                        error(
                            f"Fallback raw data też zawiódł: {fallback_error}",
                            self._message_logger,
                        )
                        return rois
            else:
                color_image = cv2.cvtColor(
                    use_color_frame.get_data().reshape((
                        use_color_frame.get_height(),
                        use_color_frame.get_width(),
                        3,
                    )),
                    cv2.COLOR_RGB2BGR,
                )

            # Process depth frame
            debug(
                f"Przetwarzanie ramki głębi z bufora {use_depth_frame.get_width()}x{use_depth_frame.get_height()}",
                self._message_logger,
            )
            depth_data = np.frombuffer(
                bytes(use_depth_frame.get_data()), dtype=np.uint16
            )
            depth_image = depth_data.reshape((
                use_depth_frame.get_height(),
                use_depth_frame.get_width(),
            ))

            # Create ROIs from synchronized frames
            if color_image is not None and depth_image is not None:
                debug(
                    f"Tworzenie ROI z zsynchronizowanych ramek - {len(self._configuration['rois'])} regionów",
                    self._message_logger,
                )
                for i, roi_config in enumerate(self._configuration["rois"]):
                    roi_color = self._image_crop(color_image, roi_config)
                    roi_depth = self._image_crop(depth_image, roi_config)
                    rois.append({"color": roi_color, "depth": roi_depth})
                info(
                    f"Utworzono {len(rois)} ROI z zsynchronizowanych ramek (sync diff: {time_diff:.0f}ms)",
                    self._message_logger,
                )
            else:
                error(
                    f"Błąd tworzenia obrazów z zsynchronizowanych ramek",
                    self._message_logger,
                )

            return rois
        except Exception as e:
            error(f"Błąd przetwarzania ramek: {e}", self._message_logger)
            error(f"Traceback: {traceback.format_exc()}", self._message_logger)
            return rois

    def _image_crop(self, image, config):
        """
        Crop image
        config:
        {
            "crop_x": (x1, x2),
            "crop_y": (y1, y2)
        }
        """
        return image[config["y"][0] : config["y"][1], config["x"][0] : config["x"][1]]

    def _serialize_roi(self, roi):
        """
        Konwertuj ROI z numpy arrays do JSON-serializable format
        """
        serialized = {}

        # Konwertuj obraz kolorowy
        if roi.get("color") is not None:
            # Encode do JPEG i następnie do base64
            _, buffer = cv2.imencode(".jpg", roi["color"])
            serialized["color"] = base64.b64encode(buffer).decode("utf-8")
            serialized["color_shape"] = roi["color"].shape

        # Konwertuj obraz głębi
        if roi.get("depth") is not None:
            # Dla depth użyj PNG (bez kompresji) lub zapisz jako raw bytes
            _, buffer = cv2.imencode(".png", roi["depth"])
            serialized["depth"] = base64.b64encode(buffer).decode("utf-8")
            serialized["depth_shape"] = roi["depth"].shape

        return serialized
