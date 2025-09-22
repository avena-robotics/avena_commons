import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from dotenv import load_dotenv

from avena_commons.camera.driver.general import CameraState
from avena_commons.camera.driver.orbec_335le import OrbecGemini335Le
from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
    Result,
)
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import MessageLogger, debug, error
from avena_commons.util.timing_stats import global_timing_stats

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

        self._check_local_data_frequency = 1
        self.name = name

        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
        )

        debug(f"camera init", self._message_logger)
        self.__camera_config = self._configuration.get("camera_configuration", {})
        debug(f"camera config: {self.__camera_config}", self._message_logger)
        self.__pipelines_config = self._configuration.get("pipelines", {})
        debug(f"pipelines config: {self.__pipelines_config}", self._message_logger)

        if self.__camera_config.get("camera_ip", None) is None:
            error(
                f"EVENT_LISTENER_INIT: Brak konfiguracji CAMERA_IP dla kamery",
                self._message_logger,
            )
            raise ValueError(f"Brak konfiguracji CAMERA_IP dla kamery")
        self.camera_address = self.__camera_config["camera_ip"]

        self.camera_running = False

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
        match self.__camera_config.get("model", None):
            case "orbec_gemini_335le":
                self.camera = OrbecGemini335Le(
                    self.camera_address, self._message_logger
                )
            case _:
                error(
                    f"EVENT_LISTENER_INIT: Brak obsługiwanej kamery {self.__camera_config.get('model', None)} obsługiwane modele: orbec_gemini_335le",
                    self._message_logger,
                )

    async def on_initializing(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZING.
        Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
        self.camera.init(self.__camera_config)

    async def on_starting(self):
        """Metoda wywoływana podczas przejścia w stan STARTING.
        Tu komponent przygotowuje się do uruchomienia głównych operacji."""
        # Uruchom kamerę
        # TODO: Odpowiedź na eventy aby wiedzieć, który postprocess użyć
        # self.camera.set_postprocess_configuration(
        #     detector="qr_detector",
        #     configuration=self.__pipelines_config["qr_detector"],
        # )
        # self.camera.set_postprocess_configuration(
        #     detector="box_detector",
        #     configuration=self.__pipelines_config["box_detector"],
        # )
        await self._analyze_event(
            Event(
                event_type="take_photo_qr",
                source=self.name,
                source_port=9999,
                destination_port=9998,
                is_processing=True,
            )
        )

        # self.camera.start()

    async def on_stopping(self):
        self.camera.stop()

    async def on_stopped(self):
        self.fsm_state = EventListenerState.INITIALIZING

    async def on_initialized(self):
        self.fsm_state = EventListenerState.STARTING

    def _clear_before_shutdown(self):
        __logger = self._message_logger  # Zapisz referencję jeśli potrzebna
        # Ustaw na None aby inne wątki nie próbowały używać
        self._message_logger = None

    async def _analyze_event(self, event):
        with Catchtime() as t:
            match event.event_type:
                case "take_photo_box":
                    self.camera.set_postprocess_configuration(
                        detector="box_detector",
                        configuration=self.__pipelines_config["box_detector"],
                    )
                case "take_photo_qr":
                    self.camera.set_postprocess_configuration(
                        detector="qr_detector",
                        configuration=self.__pipelines_config["qr_detector"],
                    )
                case _:
                    debug(f" Nieznany event {event.event_type}", self._message_logger)
                    return False
        self._current_event = event
        self._add_to_processing(event)
        global_timing_stats.add_measurement("camera_analyze_event_setup", t.ms)
        debug(f"analiz event setup time: {t.ms:.5f} s", self._message_logger)
        with Catchtime() as t2:
            self.camera.start()
        global_timing_stats.add_measurement("camera_start", t2.ms)
        debug(f"camera start time: {t2.ms:.5f} s", self._message_logger)

    async def _handle_event(self, event):
        match event.event_type:
            case "take_photo_box":
                if event.result and event.result.result == "success":
                    pass
            case "take_photo_qr":
                if event.result and event.result.result == "success":
                    pass
            case _:
                debug(f"Nieznany event {event.event_type}", self._message_logger)
        # self._find_and_remove_processing_event(event=event)
        return True

    async def _check_local_data(self):
        """
        Periodically checks and processes local data

        Raises:
            Exception: If an error occurs during data processing.
        """
        camera_state = self.camera.get_state()
        # debug(
        #     f"EVENT_LISTENER_CHECK_LOCAL_DATA: {camera_state} {type(camera_state)}",
        #     self._message_logger,
        # )
        match camera_state:
            case CameraState.ERROR:
                self.set_state(EventListenerState.ON_ERROR)
            case CameraState.STARTED:
                # Przykład zapisywania ramek (dla demonstracji)
                with Catchtime() as lt:
                    last_frame = self.camera.get_last_frame()
                global_timing_stats.add_measurement("camera_get_last_frame", lt.ms)
                debug(f"Get last frame time: {lt.ms:.5f}ms", self._message_logger)
                # pass
                if last_frame is not None:
                    self.latest_color_frame = last_frame["color"]
                    self.latest_depth_frame = last_frame["depth"]
                    debug(
                        f"Pobrano ramki Koloru i Głębi: {self.latest_color_frame.shape}, {self.latest_depth_frame.shape}",
                        self._message_logger,
                    )
                    with Catchtime() as ct:
                        result = self.camera.run_postprocess_workers(last_frame)
                        if result is not None:
                            debug(
                                f"Otrzymano wynik z run_postprocess_workers",
                                self._message_logger,
                            )
                            self.camera.stop()
                            event: Event = self._find_and_remove_processing_event(
                                event=self._current_event
                            )
                            event.result = Result(result="success")
                            event.data = result
                            # await self._reply(event)
                        else:
                            debug(
                                f"Brak wyniku z run_postprocess_workers",
                                self._message_logger,
                            )
                            self.camera.stop()
                            event: Event = self._find_and_remove_processing_event(
                                event=self._current_event
                            )
                            event.result = Result(result="failure")
                            event.data = {}
                            # await self._reply(event)

                    global_timing_stats.add_measurement(
                        "camera_run_postprocess_workers", ct.ms
                    )
                    debug(
                        f"result type: {type(result)}, result len: {len(result) if result else 0}, result: {result}",
                        self._message_logger,
                    )
                    debug(
                        f"run_postprocess_workers time: {ct.ms:.5f}ms",
                        self._message_logger,
                    )
                else:
                    error(
                        f"EVENT_LISTENER_CHECK_LOCAL_DATA: Brak ramki Koloru lub Głębi",
                        self._message_logger,
                    )
            # debug(
            #     f"EVENT_LISTENER_CHECK_LOCAL_DATA: Pobrano ramki Koloru i Głębi w {ct.t * 1_000:.2f}ms",
            #     self._message_logger,
            # )
            case _:
                pass
                # debug(
                #     f"EVENT_LISTENER_CHECK_LOCAL_DATA: {camera_state}",
                #     self._message_logger,
                # )
