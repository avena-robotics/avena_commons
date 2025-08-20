from abc import ABC, abstractmethod
from enum import Enum
from threading import Lock

from avena_commons.event_listener import Event, Result
from avena_commons.util.logger import debug, error
from avena_commons.util.measure_time import MeasureTime


class VirtualDeviceState(Enum):
    UNINITIALIZED = 0
    INITIALIZING = 1
    WORKING = 2
    ERROR = 3


class VirtualDevice(ABC):
    def __init__(self, **kwargs):
        self.device_name = kwargs["device_name"]
        self.devices = kwargs["devices"]
        self.methods = kwargs["methods"]
        self._processing_events = {}
        self._finished_events = []
        self._processing_events_lock = Lock()
        self._finished_events_lock = Lock()
        self._state = VirtualDeviceState.UNINITIALIZED
        self._message_logger = kwargs["message_logger"]

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
        pass

    def execute_event(self, event: Event) -> Event | None:  # wywolanie akcji
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
        with self._finished_events_lock:
            temp_list = self._finished_events.copy()
            self._finished_events.clear()
            return temp_list

    @abstractmethod
    def tick(self):
        """Module main loop method. Io Server calls this method periodically. Device checks should take place here. Do not use this method for blocking operations."""
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
