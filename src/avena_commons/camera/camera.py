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

from dotenv import load_dotenv

from avena_commons.camera.driver.general import CameraState
from avena_commons.camera.driver.orbec_335le import OrbecGemini335Le
from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
    Result,
)
from avena_commons.event_listener.types import CameraAction
from avena_commons.util.logger import MessageLogger, debug, error, info
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
        load_state: bool = False,
    ):
        """
        Inicjalizuje kamerę z niezbędną konfiguracją i stanem.

        Args:
            name (str): Nazwa event listenera kamery.
            address (str): Adres IP event listenera kamery.
            port (str): Port event listenera kamery.
            message_logger (MessageLogger | None): Logger do zapisywania wiadomości; domyślnie None.
            load_state (bool): Flaga ładowania stanu (obecnie nieużywana); domyślnie False.

        Raises:
            ValueError: Gdy brak wymaganej zmiennej środowiskowej CAMERA_LISTENER_PORT lub CAMERA_IP.
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

        # Photo processing state management
        self._is_processing_photo = False

        debug(
            f"EVENT_LISTENER_INIT: Event listener kamery został zainicjalizowany dla ip {self.camera_address}",
            self._message_logger,
        )
        match self.__camera_config.get("model", None):
            case "orbec_gemini_335le":
                self.camera = OrbecGemini335Le(
                    core=self.__camera_config.get("core", 8),
                    camera_ip=self.camera_address,
                    message_logger=self._message_logger,
                )
            case _:
                error(
                    f"EVENT_LISTENER_INIT: Brak obsługiwanej kamery {self.__camera_config.get('model', None)} obsługiwane modele: orbec_gemini_335le",
                    self._message_logger,
                )

        # self.camera.init(self.__camera_config) #TODO: usunąć po testach performance
        # self.camera.start() #TODO: usunąć po testach performance

    async def on_initializing(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZING.
        Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
        self.camera.init(self.__camera_config)

    async def on_starting(self):
        """Metoda wywoływana podczas przejścia w stan STARTING.
        Tu komponent przygotowuje się do uruchomienia głównych operacji."""

    async def on_stopping(self):
        self.camera.stop()
        # Reset processing flag when stopping
        self._is_processing_photo = False
        debug(
            "Camera stopping, reset processing flag",
            self._message_logger,
        )

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
        match event.event_type:
            case "take_photo_box" | "take_photo_qr":
                # Sprawdź czy kamera już przetwarza zdjęcie
                if self._is_processing_photo:
                    debug(
                        f"Camera is already processing photo, rejecting event {event.event_type}",
                        self._message_logger,
                    )
                    event.result = Result(
                        result="failure",
                        error_message="Camera is already processing photo. Please wait for current processing to complete.",
                    )
                    await self._reply(event)
                    return True

                # Ustaw flagę przetwarzania
                self._is_processing_photo = True
                debug(
                    f"Starting photo processing for event {event.event_type}",
                    self._message_logger,
                )

                light_intensity = self._calculate_light_intensity(event)

                if event.event_type == "take_photo_box":
                    # Send light control event to supervisor
                    await self._send_light_event_to_supervisor(light_intensity)
                    # Request current position for accurate transformation
                    await self._get_current_position_of_supervisor()
                    self.camera.set_postprocess_configuration(
                        detector="box_detector",
                        configuration=self.__pipelines_config["box_detector"],
                    )
                else:  # take_photo_qr
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

        # Kontynuuj tylko dla eventów fotograficznych
        if event.event_type in ["take_photo_box", "take_photo_qr"]:
            self._current_event = event
            self._add_to_processing(event)

            if self.camera.get_state() not in [
                CameraState.STARTING,
                CameraState.STARTED,
                CameraState.RUNNING,
            ]:
                self.camera.start()

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
                to_be_processed=False,
                maximum_processing_time=5.0,
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
                last_frame = self.camera.get_last_frame()

                if last_frame is not None:
                    self.latest_color_frame = last_frame["color"]
                    self.latest_depth_frame = last_frame["depth"]
                    debug(
                        f"Pobrano ramki Koloru i Głębi: {self.latest_color_frame.shape}, {self.latest_depth_frame.shape}",
                        self._message_logger,
                    )
                    debug(f"Supervisor position: {self.supervisor_position}")
                    confirmed = self.camera.run_postprocess_workers(last_frame)
                    if not confirmed:
                        error(
                            f"Błąd w run_postprocess_workers",
                            self._message_logger,
                        )
                        self.camera.stop()
                        await self._send_light_event_to_supervisor(0)

                        # Reset processing flag on error
                        self._is_processing_photo = False
                        debug(
                            f"Photo processing failed, reset processing flag",
                            self._message_logger,
                        )

                        event: Event = self._find_and_remove_processing_event(
                            event=self._current_event
                        )
                        event.result = Result(
                            result="error", error_message="Postprocess error"
                        )
                        await self._reply(event)
                        self._change_fsm_state(EventListenerState.ON_ERROR)

                else:
                    error(
                        f"EVENT_LISTENER_CHECK_LOCAL_DATA: Brak ramki Koloru lub Głębi",
                        self._message_logger,
                    )

            case CameraState.RUNNING:
                last_result = self.camera.get_last_result()
                debug(
                    f"Otrzymano wynik z run_postprocess_workers: last_result type: {type(last_result)}, last_result len: {len(last_result) if last_result else 0}, last_result: {last_result}",
                    self._message_logger,
                )

                if last_result is not None:
                    self.camera.stop()

                    # Turn off light after photo processing
                    await self._send_light_event_to_supervisor(0)

                    event: Event = self._find_and_remove_processing_event(
                        event=self._current_event
                    )
                    
                    camera_data = CameraAction(**event.data)

                    # Reset processing flag before sending response
                    self._is_processing_photo = False
                    debug(
                        f"Photo processing completed, reset processing flag",
                        self._message_logger,
                    )

                    if isinstance(last_result, dict) and any(
                        v is not None for v in last_result.values()
                    ):
                        # For QR photos, extract specific QR based on event data
                        requested_qr = camera_data.qr
                        if requested_qr in last_result:
                            qr_result = last_result.get(requested_qr)

                            # Check if qr_result is not None
                            if qr_result is not None:
                                # Check qr_rotation and modify result if needed
                                qr_rotation = camera_data.qr_rotation
                                position = transform_camera_to_base(
                                    item_pose=list(qr_result),  # Convert tuple to list
                                    current_tcp=self.supervisor_position,
                                    camera_tool_offset=self.__camera_config["camera_tool_offset"],
                                    is_rotation=qr_rotation,
                                )
                                event.result = Result(result="success")
                                event.data = CameraAction(waypoint=position).model_dump()
                                debug(
                                    f"Zwrócono wynik dla QR {requested_qr}: position{position}, qr_result: {qr_result}",
                                    self._message_logger,
                                )
                            else:
                                debug(
                                    f"Wartość dla QR {requested_qr} jest None",
                                    self._message_logger,
                                )
                                event.result = Result(result="failure")
                        else:
                            debug(
                                f"Brak detekcji dla QR {requested_qr} w wyniku",
                                self._message_logger,
                            )
                            event.result = Result(result="failure")
                        
                    elif isinstance(last_result, tuple) and len(last_result) > 0:
                        event.result = Result(result="success")
                        position = transform_camera_to_base(
                            list(last_result),
                            self.supervisor_position,
                            self.__camera_config["camera_tool_offset"],
                        )
                        event.data = CameraAction(waypoint=position).model_dump()
                        debug(
                            f"Zwrócono wynik dla BOX: position{position}, result: {last_result}",
                            self._message_logger,
                        )
                    else:
                        debug(
                            f"Brak detekcji w wyniku. type: {type(last_result)}, len: {len(last_result) if last_result else 0}, last_result: {last_result}",
                            self._message_logger,
                        )
                        event.result = Result(result="failure")
                        
                    # SEND CURRENT EVENT REPLY
                    await self._reply(event)
