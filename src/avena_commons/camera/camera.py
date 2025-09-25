"""Moduł kamery do obsługi zdjęć w systemie event-driven.

Odpowiedzialność:
- Obsługa zdarzeń zdjęciowych (take_photo_box, take_photo_qr)
- Zarządzanie try_number i kontrolą oświetlenia
- Wysyłanie zdarzeń świetlnych do supervisora na podstawie try_number
- Przetwarzanie ramek i wyników detekcji

Eksponuje:
- Klasa `Camera` (główny event listener kamery)
"""

import os
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
from avena_commons.util.logger import MessageLogger, debug, error, info
from avena_commons.util.timing_stats import global_timing_stats
from avena_commons.vision.validation.transfor_to_base import transform_camera_to_base

load_dotenv(override=True)


class Camera(EventListener):
    """
    Główna klasa logiki kamery do obsługi zdarzeń zdjęciowych.

    Odpowiada za przetwarzanie zdarzeń take_photo_box i take_photo_qr,
    zarządzanie try_number, kontrolę oświetlenia oraz komunikację z supervisorem.

    Atrybuty:
        camera_address (str): Adres IP kamery.
        camera_running (bool): Status działania kamery.
        latest_color_frame: Ostatnia ramka kolorowa.
        latest_depth_frame: Ostatnia ramka głębi.
        current_try_number (int): Aktualny numer próby dla light control.
        current_supervisor_number (int): Numer supervisora do komunikacji świetlnej.
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

        self._port = port
        self._address = address
        self.supervisor_position = [
            177.5,
            -780.0,
            510.0,
            180.0,
            0.0,
            180.0,
        ]  # Domyślna pozycja supervisora

        # Bufory dla synchronizacji ramek
        self.latest_color_frame = None
        self.latest_depth_frame = None
        self.last_color_timestamp = 0
        self.last_depth_timestamp = 0
        self.frame_sync_timeout = 500  # ms - maksymalna różnica czasowa między ramkami (zwiększone dla stabilności)

        # Try number management for light control
        self.current_try_number = 0
        self.current_supervisor_number = 1
        self.current_product_id = 0

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
        # self.camera.set_postprocess_configuration(
        #     detector="qr_detector",
        #     configuration=self.__pipelines_config["qr_detector"],
        # )
        # self.camera.set_postprocess_configuration(
        #     detector="box_detector",
        #     configuration=self.__pipelines_config["box_detector"],
        # )
        # await self._analyze_event(
        #     Event(
        #         event_type="take_photo_box",
        #         source=self.name,
        #         source_port=9999,
        #         destination_port=9998,
        #         to_be_processed=True,
        #     )
        # )

        # self.camera.start()

    async def on_stopping(self):
        self.camera.stop()

    async def on_stopped(self):
        self.fsm_state = EventListenerState.INITIALIZING

    async def on_initialized(self):
        self.fsm_state = EventListenerState.STARTING

    def _clear_before_shutdown(self):
        """Czyści zasoby przed zamknięciem kamery.

        Ustawia logger na None aby inne wątki nie próbowały z niego korzystać
        podczas procesu zamykania.
        """
        __logger = self._message_logger  # Zapisz referencję jeśli potrzebna
        # Ustaw na None aby inne wątki nie próbowały używać
        self._message_logger = None

    async def _analyze_event(self, event):
        """Analizuje przychodzące zdarzenia i obsługuje logikę try_number z kontrolą światła.

        Args:
            event: Zdarzenie do przetworzenia (take_photo_box, take_photo_qr)

        Returns:
            bool: True jeśli zdarzenie zostało poprawnie przetworzone
        """
        with Catchtime() as t:
            # Extract try_number and supervisor info from event data

            match event.event_type:
                case "take_photo_box":
                    light_intensity = self._calculate_light_intensity(event)
                    # Send light control event to supervisor
                    await self._send_light_event_to_supervisor(light_intensity)
                    # Request current position for accurate transformation
                    await self._get_current_position_of_supervisor()
                    self.camera.set_postprocess_configuration(
                        detector="box_detector",
                        configuration=self.__pipelines_config["box_detector"],
                    )
                case "take_photo_qr":
                    light_intensity = self._calculate_light_intensity(event)
                    await self._send_light_event_to_supervisor(light_intensity)
                    # Request current position for accurate transformation
                    await self._get_current_position_of_supervisor()
                    self.camera.set_postprocess_configuration(
                        detector="qr_detector",
                        configuration=self.__pipelines_config["qr_detector"],
                    )
                case "current_position":
                    if event.result and event.result.result == "success" and event.data:
                        # Zapisz otrzymaną pozycję
                        self.supervisor_position = event.data.get(
                            "current_position", self.supervisor_position
                        )
                        debug(
                            f"Updated supervisor position: {self.supervisor_position}",
                            self._message_logger,
                        )
                        return True
                case _:
                    if event.result is not None:
                        return True
                    debug(f"Nieznany event {event.event_type}", self._message_logger)
                    return False
        self._current_event = event
        self._add_to_processing(event)
        global_timing_stats.add_measurement("camera_analyze_event_setup", t.ms)
        debug(f"analiz event setup time: {t.ms:.5f} s", self._message_logger)
        with Catchtime() as t2:
            if self.camera.get_state() not in [
                CameraState.STARTING,
                CameraState.STARTED,
                CameraState.RUNNING,
            ]:
                self.camera.start()
        global_timing_stats.add_measurement("camera_start", t2.ms)
        debug(f"camera start time: {t2.ms:.5f} s", self._message_logger)
        return True

    def _calculate_light_intensity(self, event: Event) -> int:
        """Oblicza intensywność światła na podstawie try_number.

        Args:
            event (Event): Zdarzenie zawierające dane try_number i supervisor_number

        Returns:
            int: Intensywność światła (0-100)
        """
        if hasattr(event, "data") and event.data:
            self.current_try_number = event.data.get("try_number", 0)
            self.current_supervisor_number = event.data.get("supervisor_number", 1)
            self.current_product_id = event.id

            # Calculate light intensity based on try_number: [0,10,20,30,...,100] with %11
            light_intensity = (self.current_try_number % 11) * 10
            if light_intensity > 100:
                light_intensity = 100

            debug(
                f"Camera: try_number={self.current_try_number}, light_intensity={light_intensity}%, supervisor={self.current_supervisor_number}",
                self._message_logger,
            )
        return light_intensity

    async def _send_light_event_to_supervisor(self, light_intensity: float):
        """Wysyła zdarzenie kontroli światła do supervisora.

        Args:
            light_intensity (float): Intensywność światła (0.0-100.0)
        """
        try:
            if light_intensity > 0:
                # Send light_on event to supervisor
                await self._event(
                    destination=f"supervisor_{self.current_supervisor_number}",
                    destination_address=os.getenv(
                        f"SUPERVISOR_{self.current_supervisor_number}_LISTENER_ADDRESS"
                    ),
                    destination_port=os.getenv(
                        f"SUPERVISOR_{self.current_supervisor_number}_LISTENER_PORT"
                    ),
                    event_type="light_on",
                    id=self.current_product_id,
                    data={"intensity": light_intensity},
                    to_be_processed=False,
                    maximum_processing_time=2.0,
                )
                info(
                    f"Wysłano event light_on z intensywnością {light_intensity}% do supervisor_{self.current_supervisor_number}",
                    self._message_logger,
                )
            else:
                # Send light_off event to supervisor
                await self._event(
                    destination=f"supervisor_{self.current_supervisor_number}",
                    destination_address=os.getenv(
                        f"SUPERVISOR_{self.current_supervisor_number}_LISTENER_ADDRESS"
                    ),
                    destination_port=os.getenv(
                        f"SUPERVISOR_{self.current_supervisor_number}_LISTENER_PORT"
                    ),
                    event_type="light_off",
                    id=self.current_product_id,
                    data={},
                    to_be_processed=False,
                    maximum_processing_time=2.0,
                )
                info(
                    f"Wysłano event light_off do supervisor_{self.current_supervisor_number}",
                    self._message_logger,
                )
        except Exception as e:
            error(f"Błąd podczas wysyłania light_on event: {e}", self._message_logger)
        return True

    async def _get_current_position_of_supervisor(self):
        """Wysyła zapytania o aktualną pozycję supervisora."""
        try:
            await self._event(
                destination=f"supervisor_{self.current_supervisor_number}",
                destination_address=os.getenv(
                    f"SUPERVISOR_{self.current_supervisor_number}_LISTENER_ADDRESS"
                ),
                destination_port=os.getenv(
                    f"SUPERVISOR_{self.current_supervisor_number}_LISTENER_PORT"
                ),
                event_type="current_position",
                id=self.current_product_id,
                data={},
                to_be_processed=True,
                maximum_processing_time=35.0,
            )
            info(
                f"Wysłano event z zapytaniem current_position do supervisor_{self.current_supervisor_number}",
                self._message_logger,
            )
        except Exception as e:
            error(
                f"Błąd podczas wysyłania current_position event: {e}",
                self._message_logger,
            )

    # async def _handle_event(self, event):
    #     match event.event_type:
    #         case "take_photo_box":
    #             if event.result and event.result.result == "success":
    #                 pass
    #         case "take_photo_qr":
    #             if event.result and event.result.result == "success":
    #                 pass
    #         case _:
    #             debug(f"Nieznany event {event.event_type}", self._message_logger)
    #     # self._find_and_remove_processing_event(event=event)
    #     return True

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
                self._change_fsm_state(EventListenerState.ON_ERROR)
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
                        debug(f"Supervisor position: {self.supervisor_position}")
                        confirmed = self.camera.run_postprocess_workers(last_frame)
                        if not confirmed:
                            error(
                                f"Błąd w run_postprocess_workers",
                                self._message_logger,
                            )
                            self.camera.stop()
                            await self._send_light_event_to_supervisor(0)
                            event: Event = self._find_and_remove_processing_event(
                                event=self._current_event
                            )
                            event.result = Result(
                                result="error", error_message="Postprocess error"
                            )
                            await self._reply(event)
                            self._change_fsm_state(EventListenerState.ON_ERROR)
                    global_timing_stats.add_measurement(
                        "camera_run_postprocess_workers", ct.ms
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

            case CameraState.RUNNING:
                result = self.camera.get_last_result()
                if result is not None:
                    debug(
                        f"Otrzymano wynik z run_postprocess_workers: result type: {type(result)}, result len: {len(result) if result else 0}, result: {result}",
                        self._message_logger,
                    )
                    self.camera.stop()

                    # Turn off light after photo processing
                    await self._send_light_event_to_supervisor(0)

                    event: Event = self._find_and_remove_processing_event(
                        event=self._current_event
                    )
                    if isinstance(result, dict) and any(
                        v is not None for v in result.values()
                    ):
                        # For QR photos, extract specific QR based on event data
                        requested_qr = event.data.get("qr", 0)
                        if requested_qr in result:
                            qr_result = result.get(requested_qr)

                            # Check qr_rotation and modify result if needed
                            qr_rotation = event.data.get("qr_rotation", False)
                            position = transform_camera_to_base(
                                list(qr_result),  # Convert tuple to list
                                self.supervisor_position,
                                self.__camera_config["camera_tool_offset"],
                                is_rotation=qr_rotation,
                            )
                            event.result = Result(result="success")
                            event.data = position
                            debug(
                                f"Zwrócono wynik dla QR {requested_qr}: position{position}, qr_result: {qr_result}",
                                self._message_logger,
                            )
                        else:
                            debug(
                                f"Brak detekcji dla QR {requested_qr} w wyniku",
                                self._message_logger,
                            )
                            event.result = Result(result="failure")
                            event.data = {}
                        await self._reply(event)
                    elif isinstance(result, list) and len(result) > 0:
                        event.result = Result(result="success")
                        position = transform_camera_to_base(
                            result,
                            self.supervisor_position,
                            self.__camera_config["camera_tool_offset"],
                        )
                        event.data = position
                        await self._reply(event)
                    else:
                        debug(
                            f"Brak detekcji w wyniku.",
                            self._message_logger,
                        )
                        event.result = Result(result="failure")
                        event.data = {}
                        await self._reply(event)
