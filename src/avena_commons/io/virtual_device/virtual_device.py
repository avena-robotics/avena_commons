from abc import ABC, abstractmethod
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, Optional

from avena_commons.event_listener import Event, Result
from avena_commons.util.logger import debug, error, warning
from avena_commons.util.measure_time import MeasureTime

from .sensor_watchdog import SensorTimerTask, SensorWatchdog

# Import PhysicalDeviceState to check physical device states
try:
    from avena_commons.io.device import PhysicalDeviceState
except ImportError:
    # Fallback if not yet available (backwards compatibility)
    PhysicalDeviceState = None


class VirtualDeviceState(Enum):
    """Enum przedstawiający stany pracy urządzenia wirtualnego.

    Atrybuty:
        UNINITIALIZED: Urządzenie nie zostało jeszcze zainicjalizowane.
        INITIALIZING: Urządzenie jest w trakcie inicjalizacji.
        WORKING: Urządzenie pracuje prawidłowo.
        ERROR: Urządzenie znajduje się w stanie błędu.
    """

    UNINITIALIZED = 0
    INITIALIZING = 1
    WORKING = 2
    ERROR = 3


class VirtualDevice(ABC):
    """Abstrakcyjna baza dla urządzeń wirtualnych sterowanych przez serwer IO.

    Klasa dostarcza wspólną infrastrukturę: obsługę zdarzeń, kolejek
    przetwarzania i zakończonych zdarzeń, mechanizm watchdogów czujników
    oraz podstawowy FSM stanu urządzenia.
    """

    def __init__(self, **kwargs):
        """Inicjalizuje urządzenie wirtualne.

        Oczekiwane pola w `kwargs`:
            - device_name (str): Nazwa urządzenia wirtualnego.
            - devices (dict[str, Any]): Mapa podłączonych urządzeń fizycznych.
            - methods (dict[str, Any]): Konfiguracja mapująca metody wirtualne na urządzenia fizyczne.
            - message_logger: Logger wiadomości używany do logowania.
        """
        self.device_name = kwargs["device_name"]
        self.devices = kwargs["devices"]
        self.methods = kwargs["methods"]
        self._processing_events = {}
        self._finished_events = []
        self._processing_events_lock = Lock()
        self._finished_events_lock = Lock()
        self._state = VirtualDeviceState.UNINITIALIZED
        self._error_message = None
        self._message_logger = kwargs["message_logger"]
        
        # Tracking physical devices that caused errors
        # Format: {"device_name": {"state": PhysicalDeviceState, "error_message": str, "timestamp": float}}
        self._failed_physical_devices: Dict[str, Dict[str, Any]] = {}

        # Built-in sensor watchdog: common for all VirtualDevice subclasses
        # Default timeout action sets device state to ERROR and logs message
        self._watchdog = SensorWatchdog(
            on_timeout_default=self._on_sensor_timeout_wrapper,
            log_error=lambda msg: error(msg, message_logger=self._message_logger),
        )

    def _on_sensor_timeout_wrapper(self, task: SensorTimerTask) -> None:
        """Wrapper dla domyślnej akcji w przypadku przekroczenia czasu zadania watchdoga.
        Wywołuje _on_sensor_timeout(nadpisywalne), ustawia stan urządzenia na ERROR i zapisuje błąd.
        """
        self._on_sensor_timeout(task)
        self.set_state(VirtualDeviceState.ERROR)
        self._error_message = (
            f"{self.device_name} - Timeout: {task.description}, {task.metadata}"
        )

    def _on_sensor_timeout(self, task: SensorTimerTask) -> None:
        """
        Domyślna akcja w przypadku przekroczenia czasu zadania watchdoga.
        Potomne urządzenia mogą nadpisać tę metodę, aby rozbudować zachowanie
        (np. zatrzymanie napędów) przed przejściem w stan ERROR.
        """
        pass

    # Public helper API for subclasses
    def add_sensor_timeout(
        self,
        condition: Callable[[], bool],
        timeout_s: float,
        description: str,
        id: Optional[str] = None,
        on_timeout: Optional[Callable[[SensorTimerTask], None]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Dodaje zadanie watchdog do monitorowania warunku w czasie.

        Args:
            condition (Callable[[], bool]): Funkcja, która powinna zwracać True przed upływem czasu.
            timeout_s (float): Limit czasu w sekundach.
            description (str): Opis zadania/warunku.
            id (str | None): Opcjonalny identyfikator zadania; gdy None, zostanie nadany automatycznie.
            on_timeout (Callable[[SensorTimerTask], None] | None): Niestandardowa akcja na timeout.
            metadata (dict[str, Any] | None): Dodatkowe metadane zadania.

        Returns:
            str: Identyfikator utworzonego zadania watchdoga.
        """
        return self._watchdog.until(
            condition=condition,
            timeout_s=timeout_s,
            description=description,
            id=id,
            on_timeout=on_timeout or self._on_sensor_timeout_wrapper,
            metadata=metadata,
        )

    def cancel_sensor_timeout(self, id: str) -> bool:
        """Anuluje zadanie watchdoga o podanym identyfikatorze.

        Args:
            id (str): Identyfikator zadania zwrócony przez `add_sensor_timeout`.

        Returns:
            bool: True, jeśli anulowano; False, jeśli zadanie nie istniało.
        """
        return self._watchdog.cancel(id)

    def _tick_watchdogs(self) -> None:
        """Wywołuje cykliczną obsługę wszystkich zadań watchdoga dla urządzenia."""
        self._watchdog.tick()

    # Ensure watchdog.tick() and health checks are invoked before subclass tick() body
    def __init_subclass__(cls, **kwargs):
        """Hook klasowy, który opakowuje metodę `tick` potomków.

        Zapewnia, że przed właściwą logiką `tick()` urządzenia zawsze:
        1. Zostanie wywołany `watchdog.tick()` (monitoring timeoutów)
        2. Zostanie wywołany `_check_physical_devices_health()` (monitoring urządzeń fizycznych)
        """
        super().__init_subclass__(**kwargs)
        if "tick" in cls.__dict__:
            original_tick = cls.__dict__["tick"]

            def wrapped_tick(self, *args, **kws):
                # Always tick watchdog first
                try:
                    self._tick_watchdogs()
                except Exception:
                    # Nie blokuj działania urządzenia w razie problemu z watchdogiem
                    pass
                
                # Check physical devices health before processing
                try:
                    self._check_physical_devices_health()
                except Exception as e:
                    error(
                        f"{self.device_name} - Error in physical device health check: {e}",
                        message_logger=self._message_logger,
                    )
                
                return original_tick(self, *args, **kws)

            setattr(cls, "tick", wrapped_tick)

    def _check_physical_devices_health(self) -> None:
        """Sprawdza stan zdrowia wszystkich podłączonych urządzeń fizycznych.

        Metoda wywoływana w tick() przed właściwą logiką urządzenia wirtualnego.
        Dla każdego urządzenia fizycznego sprawdza jego stan FSM (jeśli dostępny).
        
        Logika reakcji:
        - Jeśli urządzenie fizyczne w ERROR: wywołuje _on_physical_device_error() (potomne mogą nadpisać)
        - Jeśli urządzenie fizyczne w FAULT: wymusza przejście VirtualDevice do ERROR
        
        Rozszerzone śledzenie:
        - Zapisuje metadane urządzeń fizycznych które spowodowały błąd w self._failed_physical_devices
        - Każdy wpis zawiera: state, error_message, timestamp
        - Wykorzystywane przez IO_server do agregacji błędów i unikania duplikacji
        
        Domyślnie _on_physical_device_error() natychmiast eskaluje do VirtualDevice.ERROR,
        ale potomne klasy mogą nadpisać aby zaimplementować retry/recovery logic.
        """
        if not self.devices or PhysicalDeviceState is None:
            return
        
        import time
        
        for device_name, device in self.devices.items():
            try:
                # Check if device has get_state method (PhysicalDeviceBase protocol)
                if hasattr(device, "get_state") and callable(device.get_state):
                    device_state = device.get_state()
                    
                    # FAULT state - critical error, always escalate
                    if device_state == PhysicalDeviceState.FAULT:
                        error_msg = getattr(device, "_error_message", "Unknown fault")
                        
                        # Record failed device metadata
                        self._failed_physical_devices[device_name] = {
                            "state": "FAULT",
                            "error_message": error_msg,
                            "timestamp": time.time(),
                            "device_type": type(device).__name__,
                        }
                        
                        error(
                            f"{self.device_name} - Physical device '{device_name}' in FAULT: {error_msg}",
                            message_logger=self._message_logger,
                        )
                        self.set_state(VirtualDeviceState.ERROR)
                        self._error_message = f"Physical device '{device_name}' ({type(device).__name__}) in FAULT: {error_msg}"
                        return
                    
                    # ERROR state - let virtual device decide how to handle
                    elif device_state == PhysicalDeviceState.ERROR:
                        error_msg = getattr(device, "_error_message", "Unknown error")
                        
                        # Record failed device metadata
                        self._failed_physical_devices[device_name] = {
                            "state": "ERROR",
                            "error_message": error_msg,
                            "timestamp": time.time(),
                            "device_type": type(device).__name__,
                        }
                        
                        warning(
                            f"{self.device_name} - Physical device '{device_name}' in ERROR: {error_msg}",
                            message_logger=self._message_logger,
                        )
                        # Call overridable handler - subclasses can implement retry logic
                        self._on_physical_device_error(device_name, error_msg)
                    
                    # Device recovered - remove from failed list
                    elif device_state == PhysicalDeviceState.WORKING:
                        if device_name in self._failed_physical_devices:
                            debug(
                                f"{self.device_name} - Physical device '{device_name}' recovered from error",
                                message_logger=self._message_logger,
                            )
                            del self._failed_physical_devices[device_name]
                        
            except Exception as e:
                error(
                    f"{self.device_name} - Error checking health of physical device '{device_name}': {e}",
                    message_logger=self._message_logger,
                )

    def _on_physical_device_error(self, device_name: str, error_message: str) -> None:
        """Obsługuje błąd urządzenia fizycznego (ERROR state, nie FAULT).
        
        Domyślna implementacja: natychmiast eskaluje do VirtualDevice.ERROR (bezpieczna strategia).
        
        Potomne klasy mogą nadpisać tę metodę aby zaimplementować:
        - Retry logic (próba ponownego wykonania operacji)
        - Fallback do innego urządzenia fizycznego
        - Graceful degradation (ograniczona funkcjonalność)
        - Ignorowanie przejściowych błędów
        
        Przykład nadpisania w potomnej klasie:
        ```python
        def _on_physical_device_error(self, device_name, error_message):
            self._retry_count += 1
            if self._retry_count >= 3:
                # Po 3 nieudanych próbach - eskaluj
                self.set_state(VirtualDeviceState.ERROR)
                self._error_message = f"Device {device_name} error after retries: {error_message}"
            else:
                # Retry logic
                debug(f"Retrying operation on {device_name} (attempt {self._retry_count})")
        ```
        
        Args:
            device_name: Nazwa urządzenia fizycznego w stanie ERROR.
            error_message: Komunikat błędu z urządzenia fizycznego.
        """
        # Default: Safe strategy - immediately escalate to ERROR
        # Get device type from failed_physical_devices metadata if available
        device_type = "unknown"
        if device_name in self._failed_physical_devices:
            device_type = self._failed_physical_devices[device_name].get("device_type", "unknown")
        
        warning(
            f"{self.device_name} - Escalating physical device error to virtual device ERROR (override _on_physical_device_error to customize)",
            message_logger=self._message_logger,
        )
        self.set_state(VirtualDeviceState.ERROR)
        self._error_message = f"Physical device '{device_name}' ({device_type}) in ERROR: {error_message}"

    def set_state(self, new_state: VirtualDeviceState):
        """
        Ustawia nowy stan urządzenia wirtualnego.
        Args:
            new_state: nowy stan urządzenia
        """
        try:
            old_state = self._state
            self._state = new_state
            debug(
                f"{self.device_name} - State changed from {old_state} to {new_state}",
                message_logger=self._message_logger,
            )
        except Exception as e:
            error(
                f"{self.device_name} - Error setting state: {e}",
                message_logger=self._message_logger,
            )

    @abstractmethod
    def get_current_state(self):
        """
        Abstrakcyjna metoda do pobierania aktualnego stanu urządzenia.
        Każde urządzenie pochodne musi zaimplementować tę metodę.
        Returns:
            Aktualny stan urządzenia (może być VirtualDeviceState lub specyficzny enum urządzenia)
        """
        pass

    def _handle_check_state_event(self, event: Event) -> Event:
        """
        Obsługuje event "check_fsm_state" - zwraca aktualny stan urządzenia.
        Args:
            event: event z typem "check_fsm_state"
        Returns:
            Event z wypełnionym polem data zawierającym stan urządzenia
        """
        try:
            current_state = self.get_current_state()

            # Inicjalizacja data jeśli jest None
            if event.data is None:
                event.data = {}

            # Dodanie informacji o stanie do eventu
            event.data["device_name"] = self.device_name
            event.data["state"] = (
                current_state.value
                if hasattr(current_state, "value")
                else str(current_state)
            )
            event.data["state_name"] = (
                current_state.name
                if hasattr(current_state, "name")
                else str(current_state)
            )

            debug(
                f"{self.device_name} - State check: {current_state}",
                message_logger=self._message_logger,
            )

        except Exception as e:
            error(
                f"{self.device_name} - Error handling check_fsm_state event: {e}",
                message_logger=self._message_logger,
            )
            event.result = Result(result="error")
            event.result.error_message = f"Error getting device state: {e}"

        return event

    def _move_event_to_finished(
        self, event_type: str, result: str, result_message: str | None = None
    ) -> bool:
        """Przenosi zdarzenie z kolejki przetwarzania do listy zakończonych.

        Args:
            event_type (str): Typ zdarzenia do przeniesienia.
            result (str): Wynik przetwarzania (np. "success", "error").
            result_message (str | None): Opcjonalna wiadomość błędu/rezultatu.

        Returns:
            bool: True, jeśli operacja się powiodła; False w przypadku błędu.
        """
        try:
            debug(
                f"{self.device_name} - Current processing events: {self._processing_events}",
                message_logger=self._message_logger,
            )
            with self._processing_events_lock:
                event = self._processing_events.pop(event_type)
            event.result = Result(result=result)
            if result_message:
                event.result.error_message = result_message
            debug(
                f"{self.device_name} - Moving event to finished: {event}",
                message_logger=self._message_logger,
            )
            with self._finished_events_lock:
                self._finished_events.append(event)
            return True
        except Exception as e:
            error(
                f"{self.device_name} - Error moving event to finished: {e}",
                message_logger=self._message_logger,
            )
            return False

    @abstractmethod
    def _instant_execute_event(self, event: Event) -> Event:
        """Abstrakcyjna metoda natychmiastowego wykonania akcji dla zdarzenia.

        Potomne klasy powinny zaimplementować logikę bezpośredniej obsługi akcji,
        która nie wymaga dodawania zdarzenia do kolejki długotrwałego przetwarzania.

        Args:
            event (Event): Zdarzenie do obsłużenia.

        Returns:
            Event: Zdarzenie z uzupełnionym polem `result`.
        """
        pass

    def execute_event(self, event: Event) -> Event | None:  # wywolanie akcji
        """Wykonuje akcję związaną z przekazanym zdarzeniem.

        Zachowanie:
            - Jeśli zdarzenie jest już w przetwarzaniu, zwraca je z wynikiem błędu.
            - Jeśli `to_be_processed` jest True, zdarzenie trafia do kolejki i funkcja zwraca None.
            - W przeciwnym wypadku akcja jest wykonywana natychmiast (w tym standardowy `*_check_fsm_state`).

        Args:
            event (Event): Zdarzenie do obsłużenia.

        Returns:
            Event | None: Zdarzenie (gdy obsługa zakończona natychmiast) lub None
            (gdy dodano do kolejki przetwarzania).
        """
        with MeasureTime(
            label=f"{self.device_name} execute_event: {event.event_type}",
            max_execution_time=1.0,
            message_logger=self._message_logger,
        ):
            with self._processing_events_lock:
                if event.event_type in self._processing_events:
                    event.result = Result(result="error")
                    event.result.error_message = "Event already in progress"
                    return event
                else:
                    if event.to_be_processed:
                        self._processing_events[event.event_type] = event
                        return None
                    else:
                        result = Result(result="success")
                        event.result = result

                        # Obsługa standardowego eventu "check_fsm_state"
                        if event.event_type.endswith("_check_fsm_state"):
                            return self._handle_check_state_event(event)
                        else:
                            return self._instant_execute_event(event)

    def finished_events(self) -> list[Event]:  # odbior zakonczonych zdarzen
        """Zwraca listę zakończonych zdarzeń i czyści wewnętrzną kolejkę.

        Returns:
            list[Event]: Kopia listy zakończonych zdarzeń od ostatniego wywołania.
        """
        with self._finished_events_lock:
            temp_list = self._finished_events.copy()
            self._finished_events.clear()
            return temp_list

    @abstractmethod
    def tick(self):
        """Główna metoda pętli modułu wywoływana cyklicznie przez serwer IO.

        W tej metodzie powinny odbywać się okresowe kontrole urządzenia. Nie należy
        umieszczać tu operacji blokujących.
        """
        pass

    def __str__(self) -> str:
        """
        Zwraca czytelną reprezentację urządzenia wirtualnego w formie stringa.
        Używane przy printowaniu urządzenia.

        Returns:
            str: Czytelna reprezentacja urządzenia zawierająca nazwę, stan i liczbę połączonych urządzeń
        """
        try:
            current_state = self.get_current_state()
            state_display = (
                current_state.name
                if hasattr(current_state, "name")
                else str(current_state)
            )
            devices_count = len(self.devices) if self.devices else 0

            return f"VirtualDevice(name='{self.device_name}', state={state_display}, connected_devices={devices_count})"
        except Exception as e:
            # Fallback w przypadku błędu - pokazujemy podstawowe informacje
            return f"VirtualDevice(name='{self.device_name}', state=ERROR, error='{str(e)}')"

    def __repr__(self) -> str:
        """
        Zwraca reprezentację urządzenia wirtualnego dla developerów.
        Pokazuje więcej szczegółów technicznych.

        Returns:
            str: Szczegółowa reprezentacja urządzenia
        """
        try:
            current_state = self.get_current_state()
            state_display = (
                f"{current_state.name}({current_state.value})"
                if hasattr(current_state, "name") and hasattr(current_state, "value")
                else str(current_state)
            )

            return (
                f"VirtualDevice(device_name='{self.device_name}', "
                f"state={state_display}, "
                f"devices={self.devices}, "
                f"methods={list(self.methods.keys()) if self.methods else []})"
            )
        except Exception as e:
            return f"VirtualDevice(device_name='{self.device_name}', error='{str(e)}')"

    def to_dict(self) -> dict:
        """
        Zwraca słownikową reprezentację urządzenia wirtualnego.
        Używane do zapisywania stanu urządzenia w strukturach danych.

        Returns:
            dict: Słownik zawierający:
                - name: nazwa urządzenia
                - state: aktualny stan urządzenia (wartość)
                - state_name: nazwa stanu urządzenia
                - connected_devices: lista nazw połączonych urządzeń (serializowalne)
                - error: informacja o błędzie (jeśli wystąpił)
        """
        # Konwertuj obiekty urządzeń na ich nazwy/typy dla serializacji JSON
        connected_devices_info = {}
        if self.devices:
            for device_name, device in self.devices.items():
                try:
                    # Próbuj wywołać to_dict() na połączonym urządzeniu
                    if hasattr(device, "to_dict") and callable(device.to_dict):
                        connected_devices_info[device_name] = device.to_dict()
                    else:
                        # Fallback - podstawowe informacje o urządzeniu
                        connected_devices_info[device_name] = {
                            "name": device_name,
                            "type": str(type(device).__name__),
                            "device_obj_str": str(device)
                            if hasattr(device, "__str__")
                            else "Unknown",
                        }
                except Exception as e:
                    # W przypadku błędu, zapisz tylko podstawowe informacje
                    connected_devices_info[device_name] = {
                        "name": device_name,
                        "type": str(type(device).__name__),
                        "error": str(e),
                    }

        result = {
            "name": self.device_name,
            "connected_devices": connected_devices_info,
            "failed_physical_devices": self._failed_physical_devices.copy() if hasattr(self, "_failed_physical_devices") else {},
        }

        try:
            current_state = self.get_current_state()

            # Dodanie informacji o stanie
            result["state"] = (
                current_state.value
                if hasattr(current_state, "value")
                else str(current_state)
            )
            result["state_name"] = (
                current_state.name
                if hasattr(current_state, "name")
                else str(current_state)
            )

            # Próba odczytu wewnętrznego FSM urządzenia (np. atrybut __fsm/_fsm/fsm)
            try:
                fsm_attr_name = None
                # Szukaj atrybutów z końcówką __fsm (po name-mangling) w instancji
                private_fsm_attrs = [
                    attr for attr in vars(self).keys() if attr.endswith("__fsm")
                ]
                if private_fsm_attrs:
                    fsm_attr_name = private_fsm_attrs[0]
                else:
                    # Popularne nazwy alternatywne
                    for candidate in ("_fsm", "fsm"):
                        if hasattr(self, candidate):
                            fsm_attr_name = candidate
                            break

                if fsm_attr_name is not None:
                    fsm_obj = getattr(self, fsm_attr_name, None)
                    if fsm_obj is not None:
                        # Jeśli atrybut FSM jest Enumem bezpośrednio
                        if isinstance(fsm_obj, Enum):
                            result["__fsm"] = getattr(fsm_obj, "name", str(fsm_obj))
                        else:
                            # Wyciągnij stan FSM, preferując pola/state o standardowych nazwach
                            fsm_state_obj = None
                            if hasattr(fsm_obj, "state"):
                                fsm_state_obj = getattr(fsm_obj, "state")
                            elif hasattr(fsm_obj, "current_state"):
                                fsm_state_obj = getattr(fsm_obj, "current_state")

                            # Zapisz pod kluczem "__fsm" nazwę stanu (np. RUNNING),
                            # a jeśli brak nazwy — jego wartość/string
                            if fsm_state_obj is not None:
                                fsm_state_name = (
                                    getattr(fsm_state_obj, "name")
                                    if hasattr(fsm_state_obj, "name")
                                    else None
                                )
                                if fsm_state_name is not None:
                                    result["__fsm"] = fsm_state_name
                                else:
                                    result["__fsm"] = (
                                        getattr(fsm_state_obj, "value")
                                        if hasattr(fsm_state_obj, "value")
                                        else str(fsm_state_obj)
                                    )
            except Exception as fsm_err:
                # Nie przerywamy serializacji w razie problemów z FSM; wpiszemy tylko podstawowe pola
                error(
                    f"{self.device_name} - Error reading internal FSM for serialization: {fsm_err}",
                    message_logger=self._message_logger,
                )

        except Exception as e:
            # W przypadku błędu dodajemy informację o błędzie
            result["state"] = "ERROR"
            result["state_name"] = "ERROR"
            result["error"] = str(e)

            error(
                f"{self.device_name} - Error creating dict representation: {e}",
                message_logger=self._message_logger,
            )

        return result
