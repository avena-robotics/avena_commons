"""Moduł IO Event Listener.

Odpowiedzialność:
- Serwer IO dla urządzeń wirtualnych i rzeczywistych
- Routing zdarzeń, selekcja urządzeń, ładowanie konfiguracji, utrzymanie FSM
- Monitorowanie zdrowia magistrali i zarządzanie cyklem życia urządzeń

Eksponuje:
- Klasa `IO_server`
"""

import importlib
import json
import traceback
from typing import Any, Dict, Optional

from avena_commons.event_listener.event import Event, Result
from avena_commons.event_listener.event_listener import (
    EventListener,
    EventListenerState,
)
from avena_commons.io.virtual_device.virtual_device import VirtualDeviceState
from avena_commons.util.logger import MessageLogger, debug, error, warning
from avena_commons.util.measure_time import MeasureTime


class IO_server(EventListener):
    """Komponent serwera IO odpowiedzialny za obsługę operacji wejścia/wyjścia oraz zdarzeń.

    Args:
        name (str): Nazwa serwera IO.
        port (int): Port serwera IO.
        configuration_file (str): Ścieżka do lokalnego pliku konfiguracji.
        general_config_file (str): Ścieżka do ogólnego (domyślnego) pliku konfiguracji.
        message_logger (MessageLogger | None): Logger wiadomości (opcjonalny).
        debug (bool): Czy wypisywać komunikaty debug (domyślnie True).
        load_state (bool): Czy wczytywać zapisany stan urządzeń (domyślnie True).
    """

    def __init__(
        self,
        name: str,
        port: int,
        configuration_file: str,
        general_config_file: str,
        message_logger: MessageLogger | None = None,
        debug: bool = True,
        load_state: bool = True,
    ):
        """Inicjalizuje serwer IO oraz przygotowuje podstawowy stan.

        Args:
            name (str): Nazwa serwera IO.
            port (int): Port serwera IO.
            configuration_file (str): Ścieżka do lokalnego pliku konfiguracji urządzeń.
            general_config_file (str): Ścieżka do ogólnego pliku konfiguracji.
            message_logger (MessageLogger | None): Logger wiadomości używany do logowania.
            debug (bool): Włącza/wyłącza komunikaty debug.
            load_state (bool): Włącza/wyłącza wczytywanie poprzedniego stanu urządzeń.
        """
        self._message_logger = message_logger
        self._debug = debug
        self._load_state = load_state
        # Pola stanu błędu IO
        self._error = False
        self._error_message = None

        try:
            # Zachowaj parametry do użycia podczas INITIALIZING
            self._name = name
            self._port = port
            self._configuration_file = configuration_file
            self._general_config_file = general_config_file
            self.check_local_data_frequency: int = 50
            super().__init__(
                name=name,
                port=port,
                message_logger=self._message_logger,
                load_state=self._load_state,
            )
        except Exception as e:
            error(f"Initialisation error: {e}", message_logger=self._message_logger)

    # FSM Callback Methods
    async def on_initializing(self):
        """
        FSM Callback: STOPPED → INITIALIZED
        Inicjalizacja komponentu IO Server oraz ustawienie stanu (bez wykonywania operacji urządzeń)
        """
        if self._debug:
            debug(
                "FSM: Initializing IO server",
                message_logger=self._message_logger,
            )
        try:
            # Wczytaj konfigurację urządzeń
            self._load_device_configuration(
                self._configuration_file, self._general_config_file
            )
            # Zbuduj słownik stanu dla aktualnej konfiguracji
            self._state = self._build_state_dict(
                self._name,
                self._port,
                self._configuration_file,
                self._general_config_file,
            )
        except Exception as e:
            error(
                f"Initialisation error during on_initializing: {e}",
                message_logger=self._message_logger,
            )
            raise

        if self._debug:
            debug(
                "FSM: IO server initialized (devices not started)",
                message_logger=self._message_logger,
            )

    async def on_run(self):
        """Metoda wywoływana podczas przejścia w stan RUN.
        Tu komponent rozpoczyna swoje główne zadania operacyjne."""
        pass

    async def on_pause(self):
        """Metoda wywoływana podczas przejścia w stan PAUSE.
        Tu komponent jest wstrzymany ale gotowy do wznowienia."""
        pass

    async def on_stopping(self):
        """
        FSM Callback: RUN → auto PAUSE → STOPPED
        Sprzątanie przetwarzanych zdarzeń oraz wyłączenie zasobów związanych z IO
        """
        if self._debug:
            debug(
                "FSM: Stopping IO server operations",
                message_logger=self._message_logger,
            )

        try:
            self._execute_before_shutdown()
        except Exception:
            pass

        if self._debug:
            debug(
                "FSM: IO server stopped and cleaned up",
                message_logger=self._message_logger,
            )

    async def on_stopped(self):
        """Metoda wywoływana po przejściu w stan STOPPED.
        Tu komponent jest całkowicie zatrzymany i wyczyszczony."""
        pass

    async def on_ack(self):
        """
        FSM Callback: FAULT → INITIALIZED
        Potwierdza błąd i resetuje wewnętrzny stan błędu serwera IO.
        """
        if self._debug:
            debug("FSM: Acknowledging fault (IO)", message_logger=self._message_logger)
            debug(
                f"Previous error state: _error={self._error}, _error_message={self._error_message}",
                message_logger=self._message_logger,
            )

        # Update self._state for error recovery
        if hasattr(self, "_state") and isinstance(self._state, dict):
            # Update FSM device states from ERROR to IDLE
            virtual_devices = self._state.get("virtual_devices", {})
            for vname, vdata in virtual_devices.items():
                # FSM state recovery for virtual devices
                if isinstance(vdata, dict):
                    # If device has 'state_name' and is in ERROR, set to UNINITIALIZED
                    if vdata.get("state_name") == "ERROR":
                        vdata["state_name"] = "UNINITIALIZED"
                    # If device has '__fsm' and is in ERROR, set to IDLE
                    if vdata.get("__fsm") == "ERROR":
                        vdata["__fsm"] = "IDLE"
        self.update_state()

        # Resetuj lokalny stan błędu IO
        self._error = False
        self._error_message = None

    async def on_error(self):
        """Metoda wywoływana podczas przejścia w stan ON_ERROR.
        Tu komponent przechodzi w stan błędu i oczekuje na ACK operatora."""
        error("FSM: Entering error state (IO)", message_logger=self._message_logger)

        # 1) Spróbuj zatrzymać każde urządzenie wirtualne wywołując jego metodę __stop (jeśli istnieje)
        try:
            if hasattr(self, "virtual_devices") and isinstance(
                self.virtual_devices, dict
            ):
                for device_name, device in self.virtual_devices.items():
                    if device is None:
                        continue
                    try:
                        # Znajdź zamanglowaną metodę __stop (np. _ClassName__stop)
                        stop_attr_name = None
                        for attr_name in dir(device):
                            try:
                                if attr_name.endswith("__stop"):
                                    candidate = getattr(device, attr_name)
                                    if callable(candidate):
                                        stop_attr_name = attr_name
                                        break
                            except Exception:
                                continue

                        if stop_attr_name:
                            stop_callable = getattr(device, stop_attr_name)
                            # Spróbuj przekazać parametry z device.methods["stop"]
                            stop_kwargs = {}
                            try:
                                methods = getattr(device, "methods", {})
                                if isinstance(methods, dict) and "stop" in methods:
                                    stop_kwargs = methods["stop"]
                            except Exception:
                                stop_kwargs = {}

                            try:
                                if stop_kwargs:
                                    stop_callable(**stop_kwargs)
                                else:
                                    stop_callable()
                                debug(
                                    f"Sent __stop to virtual device {device_name}",
                                    message_logger=self._message_logger,
                                )
                            except Exception as call_exc:
                                error(
                                    f"Error calling __stop on {device_name}: {call_exc}",
                                    message_logger=self._message_logger,
                                )
                    except Exception as dev_exc:
                        error(
                            f"Error while trying to stop virtual device {device_name}: {dev_exc}",
                            message_logger=self._message_logger,
                        )
        except Exception as e:
            error(
                f"on_error: stopping virtual devices failed: {e}",
                message_logger=self._message_logger,
            )

    async def on_fault(self):
        """Metoda wywoływana podczas przejścia w stan FAULT.
        Tu komponent przechodzi w stan błędu i oczekuje na ACK operatora."""
        # error("FSM: Entering fault state (IO)", message_logger=self._message_logger)
        pass

    async def on_starting(self):
        """
        FSM Callback: INITIALIZED → RUN
        Włącza przetwarzanie IO i aktywuje moduły w razie potrzeby.
        """
        if self._debug:
            debug("FSM: Enabling IO operations", message_logger=self._message_logger)
        # IO_server nie posiada trybu ENABLE jak robot - brak dodatkowych akcji

    async def on_pausing(self):
        """
        FSM Callback: RUN → PAUSE
        Zatrzymuje trwające operacje IO w kontrolowany sposób.
        """
        if self._debug:
            debug("FSM: Pausing IO operations", message_logger=self._message_logger)
        # Brak specyficznej logiki - urządzenia wirtualne obsługują pauzę w swoich tick()

    async def on_resuming(self):
        """
        FSM Callback: PAUSE → RUN
        Ponownie włącza operacje IO i wznawia przetwarzanie.
        """
        if self._debug:
            debug("FSM: Resuming IO operations", message_logger=self._message_logger)
        # Brak specyficznych akcji

    async def on_soft_stopping(self):
        """
        FSM Callback: RUN → INITIALIZED (łagodne zatrzymanie)
        Wstrzymuje przyjmowanie nowych zdarzeń i pozwala bieżącym zakończyć się naturalnie.
        """
        if self._debug:
            debug(
                "FSM: Soft stopping - waiting for operations to complete (IO)",
                message_logger=self._message_logger,
            )
        # NIE wymuszamy zatrzymania - pozwalamy dokończyć przetwarzanie zdarzeń

    async def on_hard_stopping(self):
        """
        FSM Callback: RUN → auto PAUSE → STOPPED
        Natychmiast sprząta kolejkę zdarzeń i wyłącza zasoby IO.
        """
        if self._debug:
            debug(
                "FSM: Hard stopping IO operations", message_logger=self._message_logger
            )

        try:
            self._execute_before_shutdown()
        except Exception:
            pass

        if self._debug:
            debug(
                "FSM: IO server hard stopped and cleaned up",
                message_logger=self._message_logger,
            )

    async def get_status(self):
        """Aktualizuje wewnętrzny stan serwera IO (z uwzględnieniem FSM)."""
        try:
            if hasattr(self, "update_state"):
                self._state = self.update_state()
        except Exception:
            pass

    async def _analyze_event(self, event: Event) -> Result:
        """
        Analizuje oraz kieruje nadejście zdarzeń do właściwych obsługujących je elementów.

        Metoda wykorzystuje `device_selector`, aby wskazać urządzenie wirtualne odpowiedzialne
        za obsługę zdarzenia. Jeżeli urządzenie zwróci zdarzenie odpowiedzi, zostanie ono wysłane,
        w przeciwnym razie zdarzenie zostanie dodane do kolejki przetwarzania.

        Args:
            event (Event): Zdarzenie wejściowe do przetworzenia.

        Returns:
            bool: True w przypadku poprawnej obsługi i/lub dodania do przetwarzania.

        Exceptions:
            ValueError: Gdy źródło lub typ zdarzenia jest nieprawidłowe lub nieobsługiwane.
        """
        if self._debug:
            debug(
                f"Analyzing event {event.event_type} from {event.source}",
                message_logger=self._message_logger,
            )
        add_to_processing = await self.device_selector(event)
        if add_to_processing:
            self._add_to_processing(event)
        return True

    async def device_selector(self, event: Event) -> bool:
        """
        Wybiera właściwe urządzenie wirtualne na podstawie danych zdarzenia i typu akcji.

        Metoda odczytuje `device_id` z danych zdarzenia oraz analizuje `event_type`, aby zbudować
        nazwę urządzenia wirtualnego i wskazać jego metodę `execute_event`. Jeżeli metoda zwróci
        obiekt `Event`, odpowiedź zostanie odesłana bez dodawania do kolejki; w przeciwnym wypadku
        zdarzenie trafi do kolejki przetwarzania.

        Args:
            event (Event): Zdarzenie do obsłużenia.

        Returns:
            bool: True, gdy zdarzenie należy dodać do kolejki przetwarzania; False w przeciwnym wypadku.
        """
        device_id = event.data.get("device_id")
        if device_id is None:
            error(
                "Device ID not found in event data", message_logger=self._message_logger
            )
            return False

        # Extract device name and specific action from event_type
        event_type = event.event_type
        if not event_type:
            error(
                "Action type is missing in the event",
                message_logger=self._message_logger,
            )
            return False
        # Split event_type to extract device prefix and specific action
        parts = event_type.split("_", 1)  # Split at first underscore only
        if len(parts) < 2:
            error(
                f"Invalid event_type format: {event_type}. Expected format: device_action",
                message_logger=self._message_logger,
            )
            return False

        device_prefix = parts[0].lower()
        action = "execute_event"  # Default method to call on the device

        # Create device name by combining prefix with device_id
        device_name = f"{device_prefix}{device_id}"

        # Search directly for the device in virtual_devices dictionary
        if hasattr(self, "virtual_devices") and device_name in self.virtual_devices:
            device = self.virtual_devices[device_name]
            # Check if the specific action method exists on the device
            if hasattr(device, action) and callable(getattr(device, action)):
                try:
                    # Call the method with event data
                    event = getattr(device, action)(event)
                    if isinstance(event, Event):
                        # If the method returns an Event, we can safely reply that event
                        await self._reply(event)
                        return False  # Do not add to processing
                    return True  # Add to processing
                except Exception as e:
                    error(
                        f"Error calling method {action} on device {device_name}: {str(e)}",
                        message_logger=self._message_logger,
                    )
            else:
                error(
                    f"Method {action} not found on device {device_name}",
                    message_logger=self._message_logger,
                )
        else:
            error(
                f"Virtual device {device_name} not found",
                message_logger=self._message_logger,
            )

        return False  # move to processing False

    async def _check_local_data(self):
        """
        Przetwarza urządzenia wirtualne i obsługuje zakończone zdarzenia.

        Metoda cyklicznie sprawdza wszystkie urządzenia wirtualne, wywołuje ich metodę `tick()`
        (jeżeli istnieje) oraz przetwarza listę zakończonych zdarzeń. W razie wykrycia błędu
        na urządzeniu (wirtualnym lub fizycznym) wykonuje eskalację do stanu ON_ERROR FSM.

        Główne kroki:
        - iteracja po urządzeniach wirtualnych i wywołanie `tick()`;
        - obsługa listy `finished_events` oraz usuwanie zdarzeń z kolejki przetwarzania;
        - proaktywna detekcja błędów urządzeń i magistral.
        """
        with MeasureTime(
            label="io - checking local data",
            max_execution_time=20.0,
            message_logger=self._message_logger,
        ):
            try:
                # Process all virtual devices
                if hasattr(self, "virtual_devices") and isinstance(
                    self.virtual_devices, dict
                ):
                    for device_name, device in self.virtual_devices.items():
                        if device is None:
                            continue

                            # Call the tick method if it exists
                        with MeasureTime(
                            label=f"io - tick({device_name})",
                            message_logger=self._message_logger,
                        ):
                            if hasattr(device, "tick") and callable(device.tick):
                                try:
                                    device.tick()
                                except Exception as e:
                                    error(
                                        f"Error calling tick() on virtual device {device_name}: {str(e)}, {traceback.format_exc()}",
                                        message_logger=self._message_logger,
                                    )
                                    raise e

                            # Proactive error detection: if any virtual device reports ERROR, trigger IO FSM ON_ERROR
                            try:
                                if hasattr(device, "get_current_state") and callable(
                                    device.get_current_state
                                ):
                                    current_state = device.get_current_state()
                                    if current_state == VirtualDeviceState.ERROR:
                                        # Zapisz źródło błędu
                                        self._error = True
                                        self._error_message = device._error_message
                                        if self.fsm_state not in {
                                            EventListenerState.ON_ERROR,
                                            EventListenerState.FAULT,
                                        }:
                                            error(
                                                f"Virtual device {device_name} in ERROR; switching IO FSM to ON_ERROR",
                                                message_logger=self._message_logger,
                                            )
                                            self._change_fsm_state(
                                                EventListenerState.ON_ERROR
                                            )
                                            return
                            except Exception as e:
                                error(
                                    f"Error checking state for {device_name}: {str(e)}",
                                    message_logger=self._message_logger,
                                )

                            # Check if device has a finished events list and process any finished events
                        with MeasureTime(
                            label=f"io - finished_events({device_name})",
                            message_logger=self._message_logger,
                        ):
                            if hasattr(device, "finished_events") and callable(
                                device.finished_events
                            ):
                                list_of_events = device.finished_events()
                                if list_of_events:
                                    debug(
                                        f"Processing finished events for device {device_name}"
                                    )
                                    try:
                                        # Process finished events
                                        for event in list_of_events:
                                            if not isinstance(event, Event):
                                                error(
                                                    f"Finished event is not of type Event: {event}",
                                                    message_logger=self._message_logger,
                                                )
                                                continue
                                            # Find and remove the event from processing
                                            original_event = event  # Zachowaj oryginalny event dla komunikatu błędu
                                            processed_event: Event = (
                                                self._find_and_remove_processing_event(
                                                    event=event
                                                )
                                            )
                                            if processed_event:
                                                await self._reply(processed_event)
                                                if self._debug:
                                                    debug(
                                                        f"Processing event for device {device_name}: {processed_event.event_type}",
                                                        message_logger=self._message_logger,
                                                    )
                                            else:
                                                if self._debug:
                                                    debug(
                                                        f"Event not found in processing: {original_event.event_type} for device: {device_name}",
                                                        message_logger=self._message_logger,
                                                    )
                                    except Exception as e:
                                        error(
                                            f"Error processing events for {device_name}: {str(e)}",
                                            message_logger=self._message_logger,
                                        )
                                        raise e
            except Exception as e:
                error(
                    f"Error in _check_local_data: {str(e)}",
                    message_logger=self._message_logger,
                )
                self._change_fsm_state(EventListenerState.ON_ERROR)
                return

            # Proaktywna detekcja błędów urządzeń fizycznych (eskalacja do ON_ERROR przy problemie ruchu)
            try:
                if hasattr(self, "physical_devices") and isinstance(
                    self.physical_devices, dict
                ):
                    for device_name, device in self.physical_devices.items():
                        if device is None:
                            continue
                        try:
                            # Preferuj atrybuty _error/_error_message gdy dostępne
                            dev_error = False
                            dev_error_message = None

                            if hasattr(device, "_error"):
                                try:
                                    dev_error = bool(getattr(device, "_error"))
                                except Exception:
                                    dev_error = False
                            # Dodatkowo spróbuj odczytać error z to_dict() gdy dostępne
                            if (
                                not dev_error
                                and hasattr(device, "to_dict")
                                and callable(device.to_dict)
                            ):
                                try:
                                    d = device.to_dict() or {}
                                    dev_error = bool(d.get("error", False))
                                    dev_error_message = d.get("error_message")
                                except Exception:
                                    pass
                            if dev_error_message is None and hasattr(
                                device, "_error_message"
                            ):
                                try:
                                    dev_error_message = getattr(
                                        device, "_error_message"
                                    )
                                except Exception:
                                    dev_error_message = None

                            if dev_error:
                                # Ustaw lokalny stan błędu IO i przełącz FSM do ON_ERROR
                                self._error = True
                                self._error_message = f"{device_name}: {dev_error_message if dev_error_message else 'unknown device error'}"
                                error(
                                    f"Detected physical device error → IO ON_ERROR: {self._error_message}",
                                    message_logger=self._message_logger,
                                )
                                if self.fsm_state not in {
                                    EventListenerState.ON_ERROR,
                                    EventListenerState.FAULT,
                                }:
                                    self._change_fsm_state(EventListenerState.ON_ERROR)
                                    return
                        except Exception as dev_scan_exc:
                            # Nie blokuj przetwarzania w razie problemów w pojedynczym urządzeniu
                            warning(
                                f"Error while scanning physical device '{device_name}': {dev_scan_exc}",
                                message_logger=self._message_logger,
                            )
            except Exception as scan_exc:
                # Nie przerywaj dalszej logiki w razie błędów skanowania urządzeń fizycznych
                warning(
                    f"Error while scanning physical devices: {scan_exc}",
                    message_logger=self._message_logger,
                )

            # Proaktywny health-check magistral (eskalacja do ON_ERROR przy problemie)
            self._assert_bus_healthy(escalate_on_failure=True)

    def _assert_bus_healthy(
        self,
        escalate_on_failure: bool = True,
        during_initialization: bool = False,
    ) -> bool:
        """
        Sprawdza stan zdrowia wszystkich magistral (BUS) przypiętych do serwera IO.

        Zasady wykrywania stanu magistrali (kolejność priorytetów):
        - Jeżeli obiekt magistrali udostępnia metodę `check_device_connection()`,
          wywołuje ją i interpretuje wynik jako bool (True = OK, False = problem).
          Wyjątek z tej metody traktowany jest jako błąd magistrali.
        - W przeciwnym razie, jeżeli obiekt ma atrybut/metodę `is_connected`,
          odczytuje wartość (lub wynik wywołania) i interpretuje jako bool.
        - Przy wykryciu problemu próbuje pozyskać szczegóły z `_error_message`,
          a jeśli to niemożliwe, to z `to_dict().get('error_message')`.

        Reakcja zależy od kontekstu:
        - during_initialization=True: fail-fast. Ustawia lokalny stan błędu, loguje
          i rzuca `RuntimeError`, aby przerwać inicjalizację.
        - during_initialization=False i `escalate_on_failure=True`: loguje, ustawia
          lokalny stan błędu i przełącza FSM IO do ON_ERROR (o ile nie jest już w
          ON_ERROR/FAULT), po czym zwraca False.

        Args:
            escalate_on_failure: Eskalować błąd do ON_ERROR w trakcie pracy.
            during_initialization: Czy sprawdzenie jest wykonywane w trakcie inicjalizacji.

        Returns:
            bool: True, jeżeli wszystkie magistrale są zdrowe; False, jeżeli wykryto
                  błąd i został on obsłużony lokalnie (tryb runtime).

        Raises:
            RuntimeError: Gdy `during_initialization=True` i health-check wykryje błąd
                          lub zostanie rzucony wyjątek podczas sprawdzania.
        """
        try:
            if not (hasattr(self, "buses") and isinstance(self.buses, dict)):
                return True

            for bus_name, bus in self.buses.items():
                if bus is None:
                    continue

                try:
                    # 1) Preferuj check_device_connection()
                    if hasattr(bus, "check_device_connection") and callable(
                        bus.check_device_connection
                    ):
                        ok = bool(bus.check_device_connection())
                        if not ok:
                            details = None
                            try:
                                details = getattr(bus, "_error_message", None)
                            except Exception:
                                details = None
                            if not details and hasattr(bus, "to_dict"):
                                try:
                                    d = bus.to_dict() or {}
                                    details = d.get("error_message")
                                except Exception:
                                    details = None

                            if during_initialization:
                                self._error = True
                                self._error_message = f"{bus_name}: {details if details else 'unknown reason'}"
                                error(
                                    f"Initial bus health check failed for {bus_name}: {self._error_message}",
                                    message_logger=self._message_logger,
                                )
                                raise RuntimeError(
                                    f"Bus {bus_name} health check failed during initialization: {self._error_message}"
                                )
                            else:
                                raise RuntimeError(
                                    f"Bus {bus_name} health check failed: {details if details else 'unknown reason'}"
                                )

                    # 2) Fallback do is_connected (akceptuj property lub metodę)
                    elif hasattr(bus, "is_connected"):
                        is_connected = (
                            bus.is_connected
                            if not callable(bus.is_connected)
                            else bus.is_connected()
                        )
                        if is_connected is False:
                            details = None
                            try:
                                details = getattr(bus, "_error_message", None)
                            except Exception:
                                details = None

                            if during_initialization:
                                self._error = True
                                self._error_message = f"{bus_name}: {details if details else 'unknown reason'}"
                                error(
                                    f"Initial bus health check failed for {bus_name}: {self._error_message}",
                                    message_logger=self._message_logger,
                                )
                                raise RuntimeError(
                                    f"Bus {bus_name} health check failed during initialization: {self._error_message}"
                                )
                            else:
                                raise RuntimeError(
                                    f"Bus {bus_name} reported disconnected state{(': ' + str(details)) if details else ''}"
                                )

                except Exception as inner_exc:
                    if during_initialization:
                        # Semantyka: log i propagacja wyjątku w trakcie inicjalizacji
                        self._error = True
                        self._error_message = f"{bus_name}: {inner_exc}"
                        error(
                            f"Initial bus health check raised for {bus_name}: {inner_exc}",
                            message_logger=self._message_logger,
                        )
                        raise
                    else:
                        if escalate_on_failure:
                            error(
                                f"Bus health check failed for {bus_name if bus_name else 'unknown'}: {inner_exc}",
                                message_logger=self._message_logger,
                            )
                            self._error = True
                            self._error_message = (
                                f"{bus_name if bus_name else 'unknown'}: {inner_exc}"
                            )
                            if self.fsm_state not in {
                                EventListenerState.ON_ERROR,
                                EventListenerState.FAULT,
                            }:
                                self._change_fsm_state(EventListenerState.ON_ERROR)
                            return False
                        else:
                            raise

            return True
        except Exception:
            # Propaguj błąd dalej (zachowuje się identycznie względem poprzedniej logiki)
            if during_initialization:
                raise
            else:
                raise

    def _execute_before_shutdown(
        self,
    ):  # TODO: Stworzyć kaskadowe zamykanie wszystkich urządzeń. Bus STOP, del VirtualDevice -> del device -> del BUS
        """
        Wykonuje operacje przed zamknięciem serwera IO.

        Aktualizuje stan urządzeń i wykonuje kaskadowe zamykanie wszystkich urządzeń.
        Kolejność zamykania: Virtual Devices -> Physical Devices -> Buses
        """
        try:
            # Aktualizuj stan przed zamknięciem
            if hasattr(self, "_state"):
                self._state = self._build_state_dict(
                    name=self._state.get("io_server", {}).get("name", "unknown"),
                    port=self._state.get("io_server", {}).get("port", 0),
                    configuration_file=self._state.get("io_server", {}).get(
                        "configuration_file", ""
                    ),
                    general_config_file=self._state.get("io_server", {}).get(
                        "general_config_file", ""
                    ),
                )

                if self._debug:
                    debug(
                        f"State updated before shutdown with {len(self._state.get('virtual_devices', {}))} virtual devices",
                        message_logger=self._message_logger,
                    )

            # Implementacja kaskadowego zamykania urządzeń
            # 1. Zatrzymaj wszystkie virtual devices
            # 2. Zatrzymaj wszystkie physical devices
            # 3. Zatrzymaj wszystkie buses

            def _try_shutdown(obj, obj_name: str, obj_kind: str):
                """Spróbuj grzecznie zamknąć obiekt wywołując jedną ze standardowych metod.

                Priorytet: shutdown → stop → close → disconnect. Każde wywołanie jest opcjonalne.
                Błędy są logowane i ignorowane, aby nie blokować dalszego zamykania.
                """
                for method_name in ("shutdown", "stop", "close", "disconnect"):
                    try:
                        if hasattr(obj, method_name):
                            method = getattr(obj, method_name)
                            if callable(method):
                                method()
                                if self._debug:
                                    debug(
                                        f"{obj_kind} {obj_name}: executed {method_name}()",
                                        message_logger=self._message_logger,
                                    )
                                # Nie przerywamy po pierwszym sukcesie - niektóre klasy mają semantykę
                                # idempotentną i wykonanie kilku metod jest bezpieczne.
                    except Exception as e:
                        error(
                            f"Error while shutting down {obj_kind} {obj_name} using {method_name}(): {e}",
                            message_logger=self._message_logger,
                        )

            # 1) Virtual Devices → usuń referencje do urządzeń fizycznych, wywołaj metody zamykania i usuń z kontenera
            if hasattr(self, "virtual_devices") and isinstance(
                self.virtual_devices, dict
            ):
                for vname in list(self.virtual_devices.keys()):
                    vdev = self.virtual_devices.pop(vname, None)
                    if vdev is None:
                        continue
                    try:
                        _try_shutdown(vdev, vname, "virtual_device")
                        # Odłącz referencje do podłączonych urządzeń, by ułatwić GC i zwolnienie magistral
                        try:
                            if hasattr(vdev, "devices"):
                                vdev.devices = {}
                        except Exception:
                            pass
                    except Exception as e:
                        error(
                            f"Error during virtual device shutdown {vname}: {e}",
                            message_logger=self._message_logger,
                        )

            # 2) Physical Devices → zatrzymaj wątki/połączenia i usuń z kontenera
            if hasattr(self, "physical_devices") and isinstance(
                self.physical_devices, dict
            ):
                for dname in list(self.physical_devices.keys()):
                    dev = self.physical_devices.pop(dname, None)
                    if dev is None:
                        continue
                    try:
                        _try_shutdown(dev, dname, "physical_device")
                        # Spróbuj zatrzymać wątki urządzenia (jeśli występują) i poczekać na ich zakończenie
                        try:
                            # Ustawie sygnały stop
                            if hasattr(dev, "_di_stop_event"):
                                getattr(dev, "_di_stop_event").set()
                            if hasattr(dev, "_do_stop_event"):
                                getattr(dev, "_do_stop_event").set()
                            if hasattr(dev, "_stop_event"):
                                getattr(dev, "_stop_event").set()

                            # Dołącz do znanych wątków jeśli żyją
                            for thread_attr in (
                                "_di_thread",
                                "_do_thread",
                                "_jog_thread",
                                "_status_thread",
                            ):
                                try:
                                    if hasattr(dev, thread_attr):
                                        t = getattr(dev, thread_attr)
                                        if t is not None and getattr(t, "is_alive")():
                                            getattr(t, "join")(timeout=1.0)
                                            setattr(dev, thread_attr, None)
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        # Jeżeli urządzenie jest Connector'em - spróbuj wysłać STOP do procesu i go zakończyć
                        try:
                            if hasattr(dev, "_send_thru_pipe") and hasattr(
                                dev, "_pipe_out"
                            ):
                                dev._send_thru_pipe(dev._pipe_out, ["STOP"])  # type: ignore[attr-defined]
                                if (
                                    hasattr(dev, "_process")
                                    and getattr(dev, "_process") is not None
                                ):
                                    proc = getattr(dev, "_process")
                                    try:
                                        if getattr(proc, "is_alive")():
                                            getattr(proc, "terminate")()
                                            getattr(proc, "join")()
                                    except Exception:
                                        pass
                                if self._debug:
                                    debug(
                                        f"physical_device {dname}: sent STOP to connector process",
                                        message_logger=self._message_logger,
                                    )
                        except Exception as e:
                            error(
                                f"Error while sending STOP to physical_device {dname}: {e}",
                                message_logger=self._message_logger,
                            )
                        # Odłącz referencję do magistrali, aby umożliwić jej zwolnienie
                        try:
                            if hasattr(dev, "bus"):
                                dev.bus = None
                        except Exception:
                            pass
                    except Exception as e:
                        error(
                            f"Error during physical device shutdown {dname}: {e}",
                            message_logger=self._message_logger,
                        )

            # 3) Buses → zatrzymaj procesy/połączenia i usuń z kontenera
            if hasattr(self, "buses") and isinstance(self.buses, dict):
                for bname in list(self.buses.keys()):
                    bus = self.buses.pop(bname, None)
                    if bus is None:
                        continue
                    try:
                        _try_shutdown(bus, bname, "bus")
                        # Jeżeli magistrala jest Connector'em - wyślij STOP do procesu i poczekaj na zakończenie
                        try:
                            if hasattr(bus, "_send_thru_pipe") and hasattr(
                                bus, "_pipe_out"
                            ):
                                bus._send_thru_pipe(bus._pipe_out, ["STOP"])  # type: ignore[attr-defined]
                                if (
                                    hasattr(bus, "_process")
                                    and getattr(bus, "_process") is not None
                                ):
                                    proc = getattr(bus, "_process")
                                    try:
                                        if getattr(proc, "is_alive")():
                                            getattr(proc, "terminate")()
                                            getattr(proc, "join")()
                                    except Exception:
                                        pass
                                if self._debug:
                                    debug(
                                        f"bus {bname}: sent STOP to connector process",
                                        message_logger=self._message_logger,
                                    )
                        except Exception as e:
                            error(
                                f"Error while sending STOP to bus {bname}: {e}",
                                message_logger=self._message_logger,
                            )
                    except Exception as e:
                        error(
                            f"Error during bus shutdown {bname}: {e}",
                            message_logger=self._message_logger,
                        )

            # Upewnij się, że kontenery są puste - ponowna inicjalizacja stworzy świeże obiekty/procesy
            try:
                self.virtual_devices = {}
            except Exception:
                pass
            try:
                self.physical_devices = {}
            except Exception:
                pass
            try:
                self.buses = {}
            except Exception:
                pass

        except Exception as e:
            error(
                f"Error during shutdown preparation: {e}",
                message_logger=self._message_logger,
            )

    def _load_device_configuration(
        self, configuration_file: str, general_config_file: str = None
    ):
        """
        Wczytuje i przetwarza konfigurację urządzeń z plików JSON, łącząc konfigurację ogólną z lokalną.

        Metoda najpierw wczytuje konfigurację ogólną (jeśli podana), następnie lokalną, dokonuje głębokiego
        scalenia (lokalne wartości mają pierwszeństwo), po czym inicjalizuje kolejno: magistrale (BUS),
        urządzenia fizyczne oraz urządzenia wirtualne.

        Kroki:
        1) Parsowanie plików JSON i scalanie konfiguracji;
        2) Inicjalizacja wszystkich magistral;
        3) Inicjalizacja urządzeń fizycznych, z przekazaniem referencji do bus;
        4) Inicjalizacja urządzeń wirtualnych, z mapowaniem metod na urządzenia fizyczne.

        Struktura przykładowej konfiguracji:
        ```json
        {
            "bus": {
                "modbus_1": { "class": "ModbusRTU", "configuration": {} }
            },
            "device": {
                "device_name": {
                    "class": "motor_driver/DriverClass",
                    "configuration": {},
                    "bus": "modbus_1"
                }
            },
            "virtual_device": {
                "feeder1": {
                    "class": "Feeder",
                    "methods": {
                        "method_name": { "device": "device_name", "method": "device_method" }
                    }
                }
            }
        }
        ```

        Args:
            configuration_file (str): Ścieżka do lokalnego pliku konfiguracji JSON.
            general_config_file (str | None): Ścieżka do ogólnego (domyślnego) pliku konfiguracji.

        Exceptions:
            FileNotFoundError: Gdy wymagany plik nie istnieje.
            ValueError: Gdy plik konfiguracji zawiera nieprawidłowy JSON.
            RuntimeError: Gdy nie udało się poprawnie zainicjalizować któregoś urządzenia.
            Exception: Inne błędy podczas wczytywania konfiguracji.
        """
        if self._debug:
            debug(
                f"Loading configuration from general file: {general_config_file} and local file: {configuration_file}",
                message_logger=self._message_logger,
            )

        # Initialize device containers
        self.buses = {}
        self.physical_devices = {}
        self.virtual_devices = {}

        # Track initialization failures
        initialization_failures = []

        # Store device configurations by type for ordered initialization
        bus_configs = {}
        device_configs = {}
        virtual_device_configs = {}

        try:
            # Load and merge configurations
            merged_config = self._load_and_merge_configs(
                general_config_file, configuration_file
            )

            # Extract configuration sections by type
            bus_configs = merged_config.get("bus", {})
            device_configs = merged_config.get("device", {})
            virtual_device_configs = merged_config.get("virtual_device", {})

            # STEP 1: Initialize all buses
            if self._debug:
                debug(
                    f"Initializing {len(bus_configs)} buses",
                    message_logger=self._message_logger,
                )

            for bus_name, bus_config in bus_configs.items():
                if "class" not in bus_config:
                    warning(
                        f"Bus {bus_name} missing class definition, skipping",
                        message_logger=self._message_logger,
                    )
                    continue

                # Initialize the bus
                class_name = bus_config["class"]

                bus = self._init_class_from_config(
                    device_name=bus_name,
                    class_name=class_name,
                    folder_name="bus",
                    config=bus_config,  # Pass the full config
                )

                if bus:
                    self.buses[bus_name] = bus
                else:
                    initialization_failures.append(
                        f"Failed to initialize bus {bus_name}"
                    )

            debug(f"Buses: {self.buses}", message_logger=self._message_logger)

            # STEP 1.1: Initial bus health check (fail-fast before devices)
            # Jeżeli którykolwiek BUS jest w stanie błędu już na starcie, eskalujemy.
            self._assert_bus_healthy(
                escalate_on_failure=True, during_initialization=True
            )

            # STEP 2: Initialize standalone physical devices
            if self._debug:
                debug(
                    f"Initializing {len(device_configs)} physical devices",
                    message_logger=self._message_logger,
                )

            for device_name, device_config in device_configs.items():
                if "class" not in device_config:
                    warning(
                        f"Device {device_name} missing class definition, skipping",
                        message_logger=self._message_logger,
                    )
                    continue

                # Get bus reference (if any)
                bus_name = device_config.get("bus")
                parent_bus = None

                if bus_name:
                    # Check if the referenced bus exists
                    if bus_name in self.buses:
                        parent_bus = self.buses[bus_name]
                    else:
                        warning(
                            f"Device {device_name} references non-existent bus {bus_name}",
                            message_logger=self._message_logger,
                        )

                # Create a copy of config without the bus reference
                device_init_config = {
                    k: v for k, v in device_config.items() if k != "bus"
                }

                # Initialize the device with parent_bus reference
                class_name = device_config["class"]

                device = self._init_class_from_config(
                    device_name=device_name,
                    class_name=class_name,
                    folder_name="device",
                    config=device_init_config,
                    parent=parent_bus,
                )

                if device:
                    # Store in physical_devices container
                    self.physical_devices[device_name] = device
                else:
                    initialization_failures.append(
                        f"Failed to initialize device {device_name}"
                    )

            # step 2.5: CONFIG BUS #TODO: Verify
            for bus_name, bus in self.buses.items():
                if hasattr(bus, "configure") and callable(bus.configure):
                    try:
                        bus.configure(self.physical_devices)
                    except Exception as e:
                        error(
                            f"Error configuring bus {bus_name}: {str(e)}",
                            message_logger=self._message_logger,
                        )
                        # print(traceback.format_exc())
                        error(
                            f"Traceback:\n{traceback.format_exc()}",
                            message_logger=self._message_logger,
                        )

                        raise

            # step 2.75: CHECK DEVICE CONNECTIONS #TODO: Verify
            for device_name, device in self.physical_devices.items():
                # if hasattr(device, "check_device_connection") and callable(device.check_device_connection):
                try:
                    device.check_device_connection()
                except Exception as e:
                    error(
                        f"Error checking device connection {device_name}: {str(e)}",
                        message_logger=self._message_logger,
                    )

            # STEP 3: Initialize virtual devices with references to physical devices
            if self._debug:
                debug(
                    f"Initializing {len(virtual_device_configs)} virtual devices",
                    message_logger=self._message_logger,
                )

            for (
                virtual_device_name,
                virtual_device_config,
            ) in virtual_device_configs.items():
                if "class" not in virtual_device_config:
                    warning(
                        f"Virtual device {virtual_device_name} missing class definition, skipping",
                        message_logger=self._message_logger,
                    )
                    continue

                # Prepare the device dictionary based on methods configuration
                referenced_devices = {}

                # Analyze methods to identify referenced physical devices
                if "methods" in virtual_device_config and isinstance(
                    virtual_device_config["methods"], dict
                ):
                    methods_config = virtual_device_config["methods"]

                    for method_name, method_config in methods_config.items():
                        if (
                            isinstance(method_config, dict)
                            and "device" in method_config
                        ):
                            device_name = method_config["device"]

                            # Find the referenced physical device
                            if device_name in self.physical_devices:
                                referenced_devices[device_name] = self.physical_devices[
                                    device_name
                                ]
                            elif device_name not in referenced_devices:
                                warning(
                                    f"Virtual device {virtual_device_name} references non-existent device {device_name}",
                                    message_logger=self._message_logger,
                                )

                # Add devices dictionary to configuration
                virtual_device_config["devices"] = referenced_devices

                # Initialize the virtual device
                class_name = virtual_device_config["class"]

                virtual_device = self._init_class_from_config(
                    device_name=virtual_device_name,
                    class_name=class_name,
                    folder_name="virtual_device",
                    config=virtual_device_config,
                )

                if virtual_device:
                    self.virtual_devices[virtual_device_name] = virtual_device
                else:
                    initialization_failures.append(
                        f"Failed to initialize virtual device {virtual_device_name}"
                    )

            # Check if any devices failed to initialize
            if initialization_failures:
                error_message = f"Configuration loading failed. The following devices could not be initialized: {initialization_failures}"
                error(error_message, message_logger=self._message_logger)
                raise RuntimeError(error_message)

            if self._debug:
                debug(
                    f"Configuration loaded successfully: {len(self.buses)} buses, {len(self.physical_devices)} physical devices, {len(self.virtual_devices)} virtual devices",
                    message_logger=self._message_logger,
                )

        except FileNotFoundError:
            error(f"Configuration file not found", message_logger=self._message_logger)
            raise FileNotFoundError(f"Configuration file not found")
        except json.JSONDecodeError as e:
            error(
                f"Invalid JSON in configuration file: {str(e)}",
                message_logger=self._message_logger,
            )
            raise ValueError(f"Invalid JSON in configuration file: {str(e)}")
        except RuntimeError:
            # Re-raise runtime errors (these are our initialization failures)
            error(traceback.format_exc(), message_logger=self._message_logger)
            raise RuntimeError
        except Exception as e:
            error(
                f"Error loading configuration: {str(e)}",
                message_logger=self._message_logger,
            )
            raise

    def _load_and_merge_configs(
        self, general_config_file: str, local_config_file: str
    ) -> dict:
        """
        Wczytuje i scala konfiguracje ogólną oraz lokalną.

        Stosowana jest strategia głębokiego scalania:
        1) Najpierw wczytywana jest konfiguracja ogólna (bazowa),
        2) Następnie wczytywana i nakładana jest konfiguracja lokalna,
        3) Wartości lokalne mają pierwszeństwo przy konflikcie,
        4) Dla zagnieżdżonych słowników scalanie wykonywane jest rekurencyjnie.

        Args:
            general_config_file (str): Ścieżka do ogólnego (domyślnego) pliku konfiguracji.
            local_config_file (str): Ścieżka do lokalnego pliku konfiguracji z nadpisaniami.

        Returns:
            dict: Słownik ze scaloną konfiguracją.

        Exceptions:
            FileNotFoundError: Gdy wymagany plik nie istnieje.
            json.JSONDecodeError: Gdy plik konfiguracji zawiera nieprawidłowy JSON.
        """
        # Initialize with empty dictionary
        merged_config = {}

        # Load general configuration if provided
        if general_config_file:
            try:
                with open(general_config_file, "r") as f:
                    general_config = json.load(f)
                merged_config = general_config
                if self._debug:
                    debug(
                        f"Loaded general configuration from {general_config_file}",
                        message_logger=self._message_logger,
                    )
            except FileNotFoundError:
                warning(
                    f"General configuration file not found: {general_config_file}",
                    message_logger=self._message_logger,
                )
            except json.JSONDecodeError as e:
                error(
                    f"Invalid JSON in general configuration file: {str(e)}",
                    message_logger=self._message_logger,
                )
                raise

        # Load local configuration if provided
        if local_config_file:
            try:
                with open(local_config_file, "r") as f:
                    local_config = json.load(f)

                # Deep merge the configurations
                merged_config = self._deep_merge(merged_config, local_config)
                if self._debug:
                    debug(
                        f"Merged local configuration from {local_config_file}",
                        message_logger=self._message_logger,
                    )
            except FileNotFoundError:
                warning(
                    f"Local configuration file not found: {local_config_file}",
                    message_logger=self._message_logger,
                )
            except json.JSONDecodeError as e:
                error(
                    f"Invalid JSON in local configuration file: {str(e)}",
                    message_logger=self._message_logger,
                )
                raise

        return merged_config

    def _deep_merge(self, base_dict: dict, override_dict: dict) -> dict:
        """
        Rekurencyjnie scala dwa słowniki z uwzględnieniem struktur zagnieżdżonych.

        Args:
            base_dict (dict): Słownik bazowy, do którego scalane są wartości.
            override_dict (dict): Słownik z wartościami nadpisującymi bazę.

        Returns:
            dict: Wynik scalania słowników.
        """
        result = base_dict.copy()

        for key, value in override_dict.items():
            # If both values are dictionaries, recursively merge them
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                # Otherwise, override the value
                result[key] = value

        return result

    def _apply_io_state_values(
        self, device_instance, device_name: str, folder_name: str
    ):
        """
        Zastosuj wartości stanu do urządzenia po jego inicjalizacji, korzystając
        w pierwszej kolejności z już wczytanego stanu w pamięci (`self._state`).

        Args:
            device_instance: instancja urządzenia
            device_name: nazwa urządzenia
            folder_name: typ urządzenia ("device", "virtual_device", "bus")
        """
        if self._debug:
            debug(
                f"Applying IO state values for {device_name} ({folder_name}) - load_state is True",
                message_logger=self._message_logger,
            )

        try:
            # Preferuj stan w pamięci ustawiony przez EventListener.__load_state
            memory_state = {}
            try:
                if isinstance(self._state, dict):
                    memory_state = self._state
            except Exception:
                memory_state = {}

            # Znajdź dane stanu urządzenia w pamięci
            device_state_data = None

            if folder_name == "virtual_device":
                virtual_devices = memory_state.get("virtual_devices", {})
                if device_name in virtual_devices:
                    device_state_data = virtual_devices[device_name]

            elif folder_name == "device":
                virtual_devices = memory_state.get("virtual_devices", {})
                for _vdev_name, vdev_data in virtual_devices.items():
                    connected_devices = vdev_data.get("connected_devices", {})
                    if device_name in connected_devices:
                        device_state_data = connected_devices[device_name]
                        break

            elif folder_name == "bus":
                buses = memory_state.get("buses", {})
                if device_name in buses:
                    device_state_data = buses[device_name]

            # Jeśli nie znaleziono stanu w pamięci, nie wykonuj nic (plik mógł zostać usunięty)
            if not device_state_data:
                return

            # Zastosuj wartości stanu do urządzenia
            values_applied = []

            if folder_name == "device":
                # Dla urządzeń fizycznych - przywróć stan operacyjny
                if "di_value" in device_state_data and hasattr(
                    device_instance, "di_value"
                ):
                    value_from_file = device_state_data["di_value"]
                    device_instance.di_value = value_from_file
                    values_applied.append("di_value")
                    if self._debug:
                        debug(
                            f"Applied di_value to {device_name}: {value_from_file}",
                            message_logger=self._message_logger,
                        )

                if "do_current_state" in device_state_data and hasattr(
                    device_instance, "do_current_state"
                ):
                    value_from_file = device_state_data["do_current_state"]
                    device_instance.do_current_state = value_from_file[:]
                    values_applied.append("do_current_state")
                    if self._debug:
                        debug(
                            f"Applied do_current_state to {device_name}: {value_from_file}",
                            message_logger=self._message_logger,
                        )

                if "coil_state" in device_state_data and hasattr(
                    device_instance, "coil_state"
                ):
                    value_from_file = device_state_data["coil_state"]
                    device_instance.coil_state = value_from_file[:]
                    values_applied.append("coil_state")
                    if self._debug:
                        debug(
                            f"Applied coil_state to {device_name}: {value_from_file}",
                            message_logger=self._message_logger,
                        )

                if "inputs_ports" in device_state_data and hasattr(
                    device_instance, "inputs_ports"
                ):
                    value_from_file = device_state_data["inputs_ports"]
                    device_instance.inputs_ports = value_from_file[:]
                    values_applied.append("inputs_ports")
                    if self._debug:
                        debug(
                            f"Applied inputs_ports to {device_name}: {value_from_file}",
                            message_logger=self._message_logger,
                        )

                if "outputs_ports" in device_state_data and hasattr(
                    device_instance, "outputs_ports"
                ):
                    value_from_file = device_state_data["outputs_ports"]
                    device_instance.outputs_ports = value_from_file[:]
                    values_applied.append("outputs_ports")
                    if self._debug:
                        debug(
                            f"Applied outputs_ports to {device_name}: {value_from_file}",
                            message_logger=self._message_logger,
                        )

            if folder_name == "virtual_device":
                # Przywracanie wewnętrznego FSM urządzenia wirtualnego (jeśli dostępny w pamięci)
                try:
                    from enum import Enum as _EnumType

                    fsm_serialized = device_state_data.get("__fsm")
                    fsm_obj = None
                    fsm_attr_name = None

                    # Znajdź obiekt/atrybut FSM na urządzeniu (name-mangling __fsm lub alternatywy)
                    try:
                        private_fsm_attrs = [
                            attr
                            for attr in vars(device_instance).keys()
                            if attr.endswith("__fsm")
                        ]
                        if private_fsm_attrs:
                            fsm_attr_name = private_fsm_attrs[0]
                            fsm_obj = getattr(device_instance, fsm_attr_name, None)
                    except Exception:
                        pass
                    if fsm_obj is None:
                        for candidate in ("_fsm", "fsm"):
                            if hasattr(device_instance, candidate):
                                fsm_attr_name = candidate
                                fsm_obj = getattr(device_instance, candidate)
                                break

                    if fsm_serialized is not None and fsm_obj is not None:
                        try:
                            # Ustal docelową wartość stanu zgodną z typem aktualnego FSM
                            target_state_value = fsm_serialized

                            # Przypadek 1: __fsm jest bezpośrednio Enumem → ustawiamy atrybut na instancji
                            if (
                                isinstance(fsm_obj, _EnumType)
                                and fsm_attr_name is not None
                            ):
                                state_type = type(fsm_obj)
                                try:
                                    if isinstance(fsm_serialized, str) and hasattr(
                                        state_type, fsm_serialized
                                    ):
                                        target_enum = getattr(
                                            state_type, fsm_serialized
                                        )
                                    else:
                                        target_enum = state_type(fsm_serialized)
                                except Exception:
                                    # Ostateczny fallback: pozostaw oryginalną wartość
                                    target_enum = fsm_obj
                                setattr(device_instance, fsm_attr_name, target_enum)
                                values_applied.append("__fsm")
                                if self._debug:
                                    debug(
                                        f"Applied virtual device FSM (enum) for {device_name}: {fsm_serialized}",
                                        message_logger=self._message_logger,
                                    )
                            else:
                                # Przypadek 2: __fsm jest obiektem z polem state/current_state lub metodą set_state
                                for state_field in ("state", "current_state"):
                                    if hasattr(fsm_obj, state_field):
                                        current_state_obj = getattr(
                                            fsm_obj, state_field
                                        )
                                        try:
                                            if isinstance(current_state_obj, _EnumType):
                                                state_type = type(current_state_obj)
                                                if isinstance(
                                                    fsm_serialized, str
                                                ) and hasattr(
                                                    state_type, fsm_serialized
                                                ):
                                                    target_state_value = getattr(
                                                        state_type, fsm_serialized
                                                    )
                                                else:
                                                    try:
                                                        target_state_value = state_type(
                                                            fsm_serialized
                                                        )
                                                    except Exception:
                                                        target_state_value = (
                                                            fsm_serialized
                                                        )
                                        except Exception:
                                            pass

                                if hasattr(fsm_obj, "set_state") and callable(
                                    getattr(fsm_obj, "set_state")
                                ):
                                    getattr(fsm_obj, "set_state")(target_state_value)
                                elif hasattr(fsm_obj, "state"):
                                    setattr(fsm_obj, "state", target_state_value)
                                elif hasattr(fsm_obj, "current_state"):
                                    setattr(
                                        fsm_obj, "current_state", target_state_value
                                    )

                                values_applied.append("__fsm")
                                if self._debug:
                                    debug(
                                        f"Applied virtual device FSM for {device_name}: {fsm_serialized}",
                                        message_logger=self._message_logger,
                                    )
                        except Exception as fsm_set_err:
                            warning(
                                f"Could not apply FSM state for {device_name}: {fsm_set_err}",
                                message_logger=self._message_logger,
                            )
                except Exception as e:
                    warning(
                        f"Error applying virtual device FSM state for {device_name}: {e}",
                        message_logger=self._message_logger,
                    )

        except Exception as e:
            warning(
                f"Error applying state values to {device_name}: {str(e)}",
                message_logger=self._message_logger,
            )

    def _init_class_from_config(
        self,
        device_name: str,
        class_name: str,
        folder_name: str,
        config: Dict[str, Any],
        parent: Optional[Any] = None,
    ) -> Any:
        """
        Inicjalizuje klasę na podstawie konfiguracji, wykorzystując dynamiczną ścieżkę modułu.

        Args:
            device_name (str): Nazwa instancji urządzenia.
            class_name (str): Nazwa klasy do zainicjalizowania (może zawierać podfolder, np. "test/Example").
            folder_name (str): Katalog logiczny poszukiwania (np. "bus", "device", "virtual_device").
            config (Dict[str, Any]): Słownik konfiguracji dla danej instancji.
            parent (Optional[Any]): Obiekt nadrzędny (np. bus dla urządzenia fizycznego).

        Returns:
            Any: Zainicjalizowaną instancję lub None w razie niepowodzenia.
        """
        try:
            # Check if class_name contains a path separator
            if "/" in class_name or "\\" in class_name:
                # Extract the actual class name from the path
                path_parts = class_name.replace("\\", "/").split("/")
                actual_class_name = path_parts[-1]  # Last part is the actual class name
                subfolder_path = "/".join(
                    path_parts[:-1]
                )  # Everything before is the subfolder path

                # Build the module path including subfolder
                test_module_path = (
                    f"lib.io.{folder_name}.{subfolder_path}.{actual_class_name.lower()}"
                )
                module_path = f"avena_commons.io.{folder_name}.{subfolder_path}.{actual_class_name.lower()}"

                if self._debug:
                    debug(
                        f"Importing {actual_class_name} from path {module_path}",
                        message_logger=self._message_logger,
                    )

                # Import module and get class
                try:
                    module = importlib.import_module(test_module_path)
                    device_class = getattr(module, actual_class_name)

                except (ImportError, AttributeError) as e:
                    try:
                        # Try importing from the main module path
                        module = importlib.import_module(module_path)
                        device_class = getattr(module, actual_class_name)

                    except (ImportError, AttributeError) as e:
                        error(
                            f"Failed to import {actual_class_name} from {module_path}: {str(e)}",
                            message_logger=self._message_logger,
                        )
                        return None
            else:
                # Standard case - no subfolder
                actual_class_name = class_name
                # Test module path
                test_module_path = f"lib.io.{folder_name}.{class_name.lower()}"
                # Build the module path
                module_path = f"avena_commons.io.{folder_name}.{class_name.lower()}"

                if self._debug:
                    debug(
                        f"Importing {class_name} from {test_module_path}",
                        message_logger=self._message_logger,
                    )

                # Import module and get class
                try:
                    module = importlib.import_module(test_module_path)
                    device_class = getattr(module, class_name)

                except (ImportError, AttributeError) as e:
                    try:
                        # Try importing from the module path
                        module = importlib.import_module(module_path)
                        device_class = getattr(module, class_name)

                    except (ImportError, AttributeError) as e:
                        error(
                            f"Failed to import {class_name} from {module_path}: {str(e)}",
                            message_logger=self._message_logger,
                        )
                        return None

            # Correctly determine device type based on folder_name and configuration structure
            is_bus = folder_name == "bus"
            is_virtual = folder_name == "virtual_device"
            is_physical = folder_name == "device"

            # Extract device configuration
            device_config = config.get("configuration", {})

            # Log the configuration being used for this device
            if self._debug:
                debug(
                    f"{device_name} - Initializing {actual_class_name} with configuration: {device_config}",
                    message_logger=self._message_logger,
                )

            # Prepare constructor parameters based on device type
            init_params = {}

            if is_virtual:
                init_params["device_name"] = device_name
                # For virtual devices, pass devices dictionary, methods from config, and message_logger
                init_params["devices"] = config.get("devices", {})
                init_params["methods"] = config.get("methods", {})
                init_params["message_logger"] = self._message_logger
                # Add configuration items directly as parameters for virtual devices too
                for key, value in device_config.items():
                    init_params[key] = value

                if self._debug:
                    debug(
                        f"{device_name} - Virtual device initialization with {len(init_params['devices'])} devices and {len(init_params['methods'])} methods",
                        message_logger=self._message_logger,
                    )

            elif is_physical or is_bus:
                # Add message_logger for both physical devices and buses
                init_params["message_logger"] = self._message_logger
                init_params["device_name"] = device_name

                # If we have a parent (bus), add it as 'bus' parameter (for physical devices on buses)
                if parent is not None:
                    init_params["bus"] = parent

                # Add all configuration items directly as parameters
                for key, value in device_config.items():
                    init_params[key] = value

            # Create instance with appropriate parameters
            device_instance = device_class(**init_params)

            # Apply state values from io_state.json after device initialization
            if self._load_state:
                self._apply_io_state_values(device_instance, device_name, folder_name)
            else:
                if self._debug:
                    debug(
                        f"Skipping state loading for {device_name} ({folder_name}) - load_state is False",
                        message_logger=self._message_logger,
                    )

            # Set additional direct configuration properties for any JSON fields
            # that weren't part of the constructor parameters
            for key, value in config.items():
                if key not in [
                    "class",
                    "configuration",
                    "device",
                    "methods",
                    "devices",
                    "bus",
                ]:  # Skip special keys
                    if hasattr(device_instance, key) and not callable(
                        getattr(device_instance, key)
                    ):
                        try:
                            setattr(device_instance, key, value)
                            if self._debug:
                                debug(
                                    f"Set attribute {key}={value}",
                                    message_logger=self._message_logger,
                                )
                        except Exception as attr_error:
                            warning(
                                f"Could not set attribute {key}: {attr_error}",
                                message_logger=self._message_logger,
                            )

            if self._debug:
                debug(
                    f"Initialized {folder_name} device with class {actual_class_name}",
                    message_logger=self._message_logger,
                )

            return device_instance

        except Exception as e:
            error(
                f"Error initializing {folder_name} device with class {class_name}: {str(e)}",
                message_logger=self._message_logger,
            )
            error(traceback.format_exc(), message_logger=self._message_logger)
            return None

    def _build_state_dict(
        self, name: str, port: int, configuration_file: str, general_config_file: str
    ) -> dict:
        """
        Buduje słownik stanu zawierający informacje o serwerze IO i wszystkich urządzeniach.

        Metoda iteruje przez wszystkie typy urządzeń (virtual_devices, buses, physical_devices)
        i tworzy ich słownikowe reprezentacje wykorzystując metodę to_dict() jeśli jest dostępna.

        Args:
            name: nazwa serwera IO
            port: port serwera IO
            configuration_file: ścieżka do pliku konfiguracji
            general_config_file: ścieżka do pliku konfiguracji ogólnej

        Returns:
            dict: Słownik zawierający stan serwera IO i wszystkich urządzeń
        """
        try:
            # Podstawowe informacje o serwerze IO
            state = {
                "io_server": {
                    "name": name,
                    "port": port,
                    "configuration_file": configuration_file,
                    "general_config_file": general_config_file,
                    "check_local_data_frequency": self.check_local_data_frequency,
                    "debug": self._debug,
                    "load_state": self._load_state,
                    "error": self._error,
                    "error_message": self._error_message,
                },
                "virtual_devices": {},
                "buses": {},
            }

            # Przeiteruj przez virtual devices
            if hasattr(self, "virtual_devices") and self.virtual_devices:
                for device_name, device in self.virtual_devices.items():
                    try:
                        # Spróbuj wywołać to_dict() - jeśli zwraca None, użyj fallback
                        device_dict = device.to_dict()
                        # Upewnij się, że pole "__fsm" jest aktualne: jeśli brak lub podejrzanie puste,
                        # spróbuj odczytać je bezpośrednio z obiektu urządzenia (fallback niezależny od to_dict)
                        try:
                            if "__fsm" not in device_dict or device_dict["__fsm"] in (
                                None,
                                "",
                                "UNKNOWN",
                            ):
                                fsm_attr_name = None
                                private_fsm_attrs = [
                                    attr
                                    for attr in vars(device).keys()
                                    if attr.endswith("__fsm")
                                ]
                                if private_fsm_attrs:
                                    fsm_attr_name = private_fsm_attrs[0]
                                else:
                                    for candidate in ("_fsm", "fsm"):
                                        if hasattr(device, candidate):
                                            fsm_attr_name = candidate
                                            break
                                if fsm_attr_name is not None:
                                    fsm_obj = getattr(device, fsm_attr_name, None)
                                    if fsm_obj is not None:
                                        from enum import Enum as _EnumType

                                        if isinstance(fsm_obj, _EnumType):
                                            device_dict["__fsm"] = getattr(
                                                fsm_obj, "name", str(fsm_obj)
                                            )
                                        else:
                                            fsm_state = None
                                            if hasattr(fsm_obj, "state"):
                                                fsm_state = getattr(fsm_obj, "state")
                                            elif hasattr(fsm_obj, "current_state"):
                                                fsm_state = getattr(
                                                    fsm_obj, "current_state"
                                                )
                                            if fsm_state is not None:
                                                device_dict["__fsm"] = (
                                                    getattr(fsm_state, "name")
                                                    if hasattr(fsm_state, "name")
                                                    else (
                                                        getattr(fsm_state, "value")
                                                        if hasattr(fsm_state, "value")
                                                        else str(fsm_state)
                                                    )
                                                )
                        except Exception:
                            pass
                        if device_dict is not None:
                            state["virtual_devices"][device_name] = device_dict
                        else:
                            # Fallback - podstawowe informacje o urządzeniu
                            state["virtual_devices"][device_name] = {
                                "name": device_name,
                                "type": str(type(device).__name__),
                                "to_dict_returned_none": True,
                            }
                    except Exception as e:
                        error(
                            f"Error building state for virtual device {device_name}: {e}",
                            message_logger=self._message_logger,
                        )
                        # Fallback - podstawowe informacje o urządzeniu
                        state["virtual_devices"][device_name] = {
                            "name": device_name,
                            "type": str(type(device).__name__),
                            "error": str(e),
                        }

            # Przeiteruj przez buses
            if hasattr(self, "buses") and self.buses:
                for bus_name, bus in self.buses.items():
                    try:
                        # Spróbuj wywołać to_dict() - jeśli zwraca None, użyj fallback
                        bus_dict = bus.to_dict()
                        if bus_dict is not None:
                            state["buses"][bus_name] = bus_dict
                        else:
                            # Fallback - podstawowe informacje o busie
                            state["buses"][bus_name] = {
                                "name": bus_name,
                                "type": str(type(bus).__name__),
                                "to_dict_returned_none": True,
                            }
                    except Exception as e:
                        error(
                            f"Error building state for bus {bus_name}: {e}",
                            message_logger=self._message_logger,
                        )
                        # Fallback - podstawowe informacje o busie
                        state["buses"][bus_name] = {
                            "name": bus_name,
                            "type": str(type(bus).__name__),
                            "error": str(e),
                        }

            if self._debug:
                debug(
                    f"Built state dict: {len(state['virtual_devices'])} virtual devices, "
                    f"{len(state['buses'])} buses",
                    message_logger=self._message_logger,
                )

            return state

        except Exception as e:
            error(
                f"Error building state dict: {e}",
                message_logger=self._message_logger,
            )
            # Zwróć minimalny state w przypadku błędu
            return {
                "io_server": {"name": name, "port": port, "error": str(e)},
                "virtual_devices": {},
                "buses": {},
            }

    def update_state(self) -> dict:
        """
        Aktualizuje i zwraca aktualny stan serwera IO z wszystkimi urządzeniami.

        Metoda publiczna do aktualizacji stanu w dowolnym momencie - przydatna do
        monitorowania, zapisywania stanu czy debugowania.

        Returns:
            dict: Aktualny stan serwera IO i wszystkich urządzeń
        """
        try:
            if hasattr(self, "_state") and self._state:
                # Użyj istniejących parametrów z aktualnego stanu
                io_server_info = self._state.get("io_server", {})
                self._state = self._build_state_dict(
                    name=io_server_info.get("name", "unknown"),
                    port=io_server_info.get("port", 0),
                    configuration_file=io_server_info.get("configuration_file", ""),
                    general_config_file=io_server_info.get("general_config_file", ""),
                )
            else:
                # Jeśli nie ma stanu, stwórz podstawowy
                self._state = self._build_state_dict(
                    name="unknown",
                    port=0,
                    configuration_file="",
                    general_config_file="",
                )

            if self._debug:
                debug(
                    f"State updated manually: {len(self._state.get('virtual_devices', {}))} virtual devices, "
                    f"{len(self._state.get('buses', {}))} buses",
                    message_logger=self._message_logger,
                )

            return self._state

        except Exception as e:
            error(
                f"Error updating state: {e}",
                message_logger=self._message_logger,
            )
            return self._state if hasattr(self, "_state") else {}
