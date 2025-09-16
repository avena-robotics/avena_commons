import asyncio
import copy
import json
import os
import signal
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import aiohttp
import psutil
import uvicorn
import uvicorn.config
import uvicorn.server
from fastapi import FastAPI
from pydantic import BaseModel

from avena_commons.util.control_loop import ControlLoop
from avena_commons.util.logger import MessageLogger, debug, error, info, warning

from .event import Event, Result

TEMP_DIR = Path("temp")  # Relatywna ścieżka do bieżącego katalogu roboczego


class EventListenerState(Enum):
    UNKNOWN = -1  # Stan początkowy (zielony elips)
    STOPPED = 0  # Stan pasywny - zasoby zwolnione, odrzuca eventy biznesowe
    INITIALIZING = 1  # Stan przejściowy STOPPED → INITIALIZED (wczytanie state)
    STOPPING = 2  # Stan przejściowy INITIALIZED → STOPPED (zamykanie)
    INITIALIZED = 3  # Stan buforowy z zasobami - informacyjne responses, szybki restart
    STARTING = 4  # Stan przejściowy INITIALIZED → RUN (uruchomienie)
    RUN = 5  # Stan operacyjny - pełne przetwarzanie eventów
    PAUSING = 6  # Stan przejściowy RUN → PAUSE (wstrzymywanie)
    RESUMING = 7  # Stan przejściowy PAUSE → RUN (wznawianie)
    PAUSE = 8  # Stan buforujący - wstrzymane operacje z zachowaniem kontekstu
    SOFT_STOPPING = 9  # Stan przejściowy RUN → INITIALIZED (gracefully shutdown)
    HARD_STOPPING = 10  # Stan przejściowy PAUSE → STOPPED (hard stopping - zapis state)
    FAULT = 11  # Stan błędu wymagający ACK operatora
    ON_ERROR = 12  # Trigger błędu - automatyczne przejście do FAULT
    ACK = 13  # Potwierdzenie operatora ze stanu FAULT → STOPPED


class EventListener:
    __fsm_state: EventListenerState = EventListenerState.UNKNOWN
    __name: str
    __address: str = "0.0.0.0"
    __port: int
    __state_file_path: str = None
    __config_file_path: str = None
    __retry_count: int = 100000000
    __discovery_neighbours = False

    __incoming_events: list[Event] = []
    _processing_events_dict: dict = {}  # Structure: {timestamp: event}
    __events_to_send: list[
        dict
    ] = []  # Lista słowników {event: Event, retry_count: int}

    __lock_for_general_purpose = threading.Lock()
    __lock_for_incoming_events = threading.Lock()
    __lock_for_processing_events = threading.Lock()
    __lock_for_events_to_send = threading.Lock()
    __lock_for_state_data = threading.Lock()

    __send_queue_frequency: int = 50
    __analyze_queue_frequency: int = 100
    __check_local_data_frequency: int = 100
    __check_local_data_frequency_changed: bool = False
    __discovery_frequency: int = 1
    __get_state_frequency: int = 1

    _state: dict[str, Any] = {}
    _configuration: dict[str, Any] = {}
    _default_configuration: dict[str, Any] = {}
    _shutdown_requested: bool = False

    _message_logger: MessageLogger = None
    server: uvicorn.Server = None
    config: uvicorn.Config = None
    app: FastAPI = None
    _system_ready = threading.Event()
    __session = None  # Will be initialized in start()

    # For background state calculation
    _latest_state_data: dict = {}
    __state_update_frequency: int = 1  # Hz
    __state_update_thread: threading.Thread = None

    _error: bool = False
    _error_code: int = 0
    _error_message: str | None = None

    def __init__(
        self,
        name: str,
        address: str = "127.0.0.1",
        port: int = 8000,
        message_logger: MessageLogger | None = None,
        load_state: bool = False,
        discovery_neighbours: bool = False,
        raport_overtime: bool = True,
        # use_parallel_send: bool = True,
        use_cumulative_send: bool = True,
    ):
        """
        Initializes a new EventListener object.

        Args:
            name (str): Listener name
            port (int): Server port to listen on
            message_logger (MessageLogger, optional): Logger for message recording. Defaults to None
            load_state (bool, optional): Flag determining whether to load saved state. Defaults to False
            raport_overtime (bool, optional): Flag determining whether to report overtime events. Defaults to True
        """
        info(
            f"Initializing event listener '{name}' on {address}:{port}",
            message_logger=message_logger,
        )

        # Zgodnie z FSM - stan początkowy to UNKNOWN, automatycznie przechodzi do STOPPED
        self.fsm_state = EventListenerState.UNKNOWN
        info(
            f"Event listener '{name}' initialized in UNKNOWN state",
            message_logger=message_logger,
        )

        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        # For non-blocking CPU calculation
        self.__last_proc_cpu_times: dict = {}
        self.__last_cpu_calc_time: float = 0.0

        self.__state_file_path = TEMP_DIR / f"{name}_state.json"
        self.__config_file_path = f"{name}_config.json"
        self.__name = name.lower()
        self.__port = int(port)
        self.__address = address
        self.__raport_overtime = raport_overtime
        self.servers = {}
        self.__incoming_events = []
        self.__received_events = 0
        self.__sended_events = 0
        self.__prev_received_events = 0
        self.__prev_sended_events = 0
        self.__received_events_per_second = 0
        self.__sended_events_per_second = 0
        self._shutdown_requested = False
        # self.__use_parallel_send = use_parallel_send
        self.__use_cumulative_send = use_cumulative_send
        self._message_logger = message_logger
        self._system_ready = threading.Event()
        self.__discovery_neighbours = discovery_neighbours

        # Inicjalizacja psutil
        self.__main_process = psutil.Process(os.getpid())
        self.__main_process.cpu_percent()  # Inicjalizacja
        self.__health_status = {}

        # Wczytanie konfiguracji
        self.__load_configuration()

        # Dodanie obsługi sygnałów
        signal.signal(signal.SIGINT, self.__signal_handler)
        signal.signal(signal.SIGTERM, self.__signal_handler)

        # debug(
        #     f"Using parallel send: {self.__use_parallel_send}",
        #     message_logger=self._message_logger,
        # )

        self.app = FastAPI(
            docs_url="/",
            redoc_url="/redoc",
        )
        self.config = uvicorn.Config(
            self.app,
            loop="asyncio",
            host="0.0.0.0",
            port=port,
            log_level="error",  # Changed from warning to error to reduce noise
            access_log=False,  # Disable access logs to reduce output
        )

        @self.app.post("/event")
        async def handle_event(event: Event):
            await self.__event_handler(event)
            return {"status": "ok"}

        # Startujemy thready podstawowe - będą czekać na sygnał
        self.__start_local_check()
        self.__start_analysis()
        self.__start_send_event()
        self.__start_state_update_thread()

        # Local check uruchamiany dopiero w RUN
        # self.local_check_thread = None

        if self.__discovery_neighbours:
            self.__start_discovering()

        # Automatyczne przejście UNKNOWN → STOPPED
        self._change_fsm_state(EventListenerState.STOPPED)

    @property
    def fsm_state(self):
        return self.__fsm_state

    @fsm_state.setter
    def fsm_state(self, value: EventListenerState):
        debug(
            f"FSM state changed to {value}",
            message_logger=self._message_logger,
        )
        self.__fsm_state = value

    @property
    def received_events(self):
        return self.__received_events

    @property
    def check_local_data_frequency(self):
        return self.__check_local_data_frequency

    @check_local_data_frequency.setter
    def check_local_data_frequency(self, value: int):
        self.__check_local_data_frequency = value
        self.__check_local_data_frequency_changed = True

    @property
    def analyze_queue_frequency(self):
        return self.__analyze_queue_frequency

    @analyze_queue_frequency.setter
    def analyze_queue_frequency(self, value: int):
        self.__analyze_queue_frequency = value

    @property
    def sended_events(self):
        return self.__sended_events

    def size_of_incomming_events_queue(self):
        return len(self.__incoming_events)

    def size_of_processing_events_queue(self):
        return len(self._processing_events_dict)

    def size_of_events_to_send_queue(self):
        return len(self.__events_to_send)

    def __signal_handler(self, signum, frame):
        info(
            f"Otrzymano sygnał {signum}. Rozpoczynam bezpieczne zamykanie...",
            message_logger=None,
        )
        # Wyłącz wątki przed próbą zamknięcia
        self.__del__()  # Wywołujemy destruktor, który wywoła __shutdown
        sys.exit(0)

    @contextmanager
    def __atomic(self):
        """Context manager for thread-safe queue operations"""
        with self.__lock_for_general_purpose:
            yield

    @contextmanager
    def __atomic_operation_for_events_to_send(self):
        """Context manager dla bezpiecznych operacji na kolejce zdarzeń do wysłania"""

        try:
            with (
                self.__lock_for_events_to_send
            ):  # Używamy tylko with, bez osobnego acquire()
                yield
        finally:
            pass

    @contextmanager
    def __atomic_operation_for_incoming_events(self):
        """Context manager dla bezpiecznych operacji na kolejce zdarzeń do wysłania"""

        try:
            with (
                self.__lock_for_incoming_events
            ):  # Używamy tylko with, bez osobnego acquire()
                yield
        finally:
            pass

    @contextmanager
    def __atomic_operation_for_processing_events(self):
        """Context manager dla bezpiecznych operacji na kolejce zdarzeń do wysłania"""

        try:
            with (
                self.__lock_for_processing_events
            ):  # Używamy tylko with, bez osobnego acquire()
                yield
        finally:
            pass

    def _serialize_value(self, value: Any) -> Any:
        """
        Recursively serializes a value to JSON format.

        Args:
            value (Any): Value to serialize

        Returns:
            Any: Serialized value ready for JSON format

        Note:
            Handles serialization of Pydantic objects, dictionaries, lists, datetime objects,
            Enum values, and objects with to_dict() method (like orchestrator components)
        """

        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        elif hasattr(value, "to_dict") and callable(getattr(value, "to_dict")):
            # Obsługa komponentów orchestratora (DatabaseComponent, EmailComponent, etc.)
            return self._serialize_value(value.to_dict())
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, Enum):
            return value.value
        return value

    def __save_state(self):
        """
        Saves state to file.

        Saves current state of all event queues and listener state to JSON file.
        Operation is skipped if queues and state are empty.
        """
        try:
            if not (
                self.__incoming_events
                or self.__events_to_send
                or self._state
                or self._processing_events_dict
            ):
                debug(
                    "Kolejki są puste, pomijam zapis do pliku",
                    message_logger=self._message_logger,
                )
                return

            with self.__lock_for_general_purpose:
                debug(
                    "Starting state serialization", message_logger=self._message_logger
                )
                serialized_state = self._serialize_value(self._state)
                debug(
                    "State serialization completed", message_logger=self._message_logger
                )

                # Flatten processing_events_dict to a list of events
                processing_events_list = []
                for event in self._processing_events_dict.values():
                    processing_events_list.append(event.to_dict())

                queues_data = {
                    "incoming_events": [
                        event.to_dict() for event in self.__incoming_events
                    ],
                    "processing_events": processing_events_list,
                    "events_to_send": [
                        event_data["event"].to_dict()
                        for event_data in self.__events_to_send
                    ],
                    "state": serialized_state,
                }

                debug("Writing to file", message_logger=self._message_logger)
                with open(self.__state_file_path, "w", encoding="utf-8") as f:
                    json.dump(
                        queues_data, f, indent=4, sort_keys=True, ensure_ascii=False
                    )
                info(
                    "Kolejki zostały zapisane do pliku",
                    message_logger=self._message_logger,
                )

        except Exception as e:
            error(
                f"Błąd podczas zapisywania kolejek: {e} {self.__incoming_events} {self._processing_events_dict} {self.__events_to_send}",
                message_logger=self._message_logger,
            )
            error(
                f"State type: {type(self._state)}", message_logger=self._message_logger
            )
            error(f"State content: {self._state}", message_logger=self._message_logger)

    def __load_state(self):
        """
        Loads state from file.

        Reads saved state from JSON file and reconstructs all event queues
        and listener state. File is deleted after successful loading.
        """
        if not os.path.exists(self.__state_file_path):
            return

        try:
            with open(self.__state_file_path, "r") as f:
                json_data = json.load(f)

            # Konwersja danych na obiekty Event
            for event_data in json_data.get("incoming_events", []):
                event = Event(**event_data)
                self.__incoming_events.append(event)

            # Rekonstrukcja processing_events_dict
            for event_data in json_data.get("processing_events", []):
                event = Event(**event_data)
                event_timestamp = event.timestamp.isoformat()
                self._processing_events_dict[event_timestamp] = event

            # Rekonstrukcja events_to_send
            for event_data in json_data.get("events_to_send", []):
                if isinstance(event_data, dict) and "event" in event_data:
                    # Nowy format z retry_count
                    event = Event(**event_data["event"])
                    retry_count = event_data.get("retry_count", 0)
                    self.__events_to_send.append({
                        "event": event,
                        "retry_count": retry_count,
                    })
                else:
                    # Stary format - tylko event
                    event = Event(**event_data)
                    self.__events_to_send.append({"event": event, "retry_count": 0})

            # Wczytywanie całego stanu - wszystko co jest w sekcji "state"
            state_data = json_data.get("state", {})
            if hasattr(self, "_deserialize_state"):
                self._deserialize_state(state_data)
            else:
                # Aktualizacja _state ze wszystkimi danymi z sekcji "state"
                if isinstance(state_data, dict) and state_data:
                    if not isinstance(self._state, dict):
                        self._state = {}
                    self._state.update(state_data)

            info(
                "Kolejki zostały wczytane z pliku", message_logger=self._message_logger
            )

            # Usuwanie pliku po wczytaniu
            os.remove(self.__state_file_path)
            info(
                "Plik z kolejkami został usunięty", message_logger=self._message_logger
            )

        except Exception as e:
            error(
                f"Błąd podczas wczytywania kolejek: {e}",
                message_logger=self._message_logger,
            )

    def _event_find_and_remove_debug(self, event: Event):
        if event.is_system_event:
            return
        processing_time = time.time() - event.timestamp.timestamp()
        if processing_time < event.maximum_processing_time:
            debug(
                f"Event find and remove from processing: source={event.source} destination={event.destination} event_type={event.event_type} data={event.data} result={event.result.result if event.result else None} timestamp={event.timestamp} processing_time={processing_time:.2f}s.",
                message_logger=self._message_logger,
            )
        else:
            error(
                f"OVERTIME: Event find and remove from processing: source={event.source} destination={event.destination} event_type={event.event_type} data={event.data} result={event.result.result if event.result else None} timestamp={event.timestamp} processing_time={processing_time:.2f}s.",
                message_logger=self._message_logger,
            )

    def _event_add_to_processing_debug(self, event: Event):
        if not event.is_system_event:
            debug(
                f"Event add to processing: id={event.id} event_type={event.event_type} data={event.data} result={event.result.result if event.result else None} timestamp={event.timestamp} MPT={event.maximum_processing_time}",
                message_logger=self._message_logger,
            )

    @contextmanager
    def _event_send_debug(self, event: Event):
        if event.is_system_event:  # nie debugujemy systemowych
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            if event.event_type == "cumulative":
                message = f"Event sent to {event.destination} [{event.destination_address}:{event.destination_port}{event.destination_endpoint}] (cumulative) payload={event.payload} in {elapsed:.2f} ms:\n"
                for e in event.data["events"]:
                    message += f"- event_type='{e['event_type']}' data={e['data']} result={e['result']['result'] if e['result'] else None} timestamp={e['timestamp']} MPT={e['maximum_processing_time']}\n"
            else:
                message = f"Event sent to {event.destination} [{event.destination_address}:{event.destination_port}{event.destination_endpoint}]: event_type='{event.event_type}' result={event.result.result if event.result else None} timestamp={event.timestamp} MPT={event.maximum_processing_time} in {elapsed:.2f} ms"
            info(
                message,
                message_logger=self._message_logger,
            )

    def _event_receive_debug(self, event: Event):
        if event.is_system_event:  # nie debugujemy systemowych
            return
        if event.event_type == "cumulative":
            message = f"Event received from {event.source} [{event.source_address}:{event.source_port}{event.destination_endpoint}] (cumulative) payload={event.payload}:\n"
            for e in event.data["events"]:
                message += f"- event_type='{e['event_type']}' data={e['data']} result={e['result']['result'] if e['result'] else None} timestamp={e['timestamp']} MPT={e['maximum_processing_time']}\n"
        else:
            message = f"Event received from {event.source} [{event.source_address}:{event.source_port}{event.destination_endpoint}]: event_type={event.event_type} result={event.result.result if event.result else None} timestamp={event.timestamp} MPT={event.maximum_processing_time}"
        info(
            message,
            message_logger=self._message_logger,
        )

    def __save_configuration(self):
        """
        Saves configuration to file by storing only differences from baseline configuration.

        Compares current _configuration with _default_configuration and saves
        only the changed values to the config file. This preserves the original defaults
        while persisting only the actual changes made during runtime.
        Operation is skipped if configuration is empty or no changes exist.
        """
        try:
            if not self._configuration:
                debug(
                    "Konfiguracja jest pusta, pomijam zapis do pliku",
                    message_logger=self._message_logger,
                )
                return

            with self.__lock_for_general_purpose:
                debug(
                    "Starting configuration save with baseline comparison",
                    message_logger=self._message_logger,
                )

                # Extract only the differences from baseline
                config_changes = self._extract_config_differences(
                    self._default_configuration, self._configuration
                )

                # Only save if there are actual changes
                if config_changes:
                    debug(
                        "Configuration changes detected, serializing",
                        message_logger=self._message_logger,
                    )
                    serialized_config = self._serialize_value(config_changes)
                    debug(
                        "Configuration serialization completed",
                        message_logger=self._message_logger,
                    )

                    debug(
                        "Writing configuration changes to file",
                        message_logger=self._message_logger,
                    )
                    with open(self.__config_file_path, "w", encoding="utf-8") as f:
                        json.dump(
                            serialized_config,
                            f,
                            indent=4,
                            sort_keys=True,
                            ensure_ascii=False,
                        )
                    info(
                        "Konfiguracja zostala zapisana do pliku (changes only)",
                        message_logger=self._message_logger,
                    )
                else:
                    debug(
                        "No configuration changes detected, skipping save",
                        message_logger=self._message_logger,
                    )
                    # Remove config file if no changes exist
                    if os.path.exists(self.__config_file_path):
                        os.remove(self.__config_file_path)
                        debug(
                            "Removed empty configuration file",
                            message_logger=self._message_logger,
                        )

        except Exception as e:
            error(
                f"Błąd podczas zapisywania konfiguracji: {e}",
                message_logger=self._message_logger,
            )
            error(
                f"Configuration type: {type(self._configuration)}",
                message_logger=self._message_logger,
            )
            error(
                f"Configuration content: {self._configuration}",
                message_logger=self._message_logger,
            )

    def __load_configuration(self):
        """
        Loads configuration from file and merges it with default configuration.

        First establishes the baseline configuration, then loads saved changes from file
        and merges them with the baseline to create the working _configuration.
        The baseline remains unchanged and serves as reference for detecting changes.
        If the class has a _deserialize_configuration method, uses it for deserialization.
        """
        # Store the current configuration as baseline before any modifications
        self._configuration = (
            copy.deepcopy(self._default_configuration)
            if self._default_configuration
            else {}
        )

        if not os.path.exists(self.__config_file_path):
            debug(
                f"Plik konfiguracji {self.__config_file_path} nie istnieje, pomijam wczytywanie.",
                message_logger=self._message_logger,
            )
            return

        try:
            with open(self.__config_file_path, "r") as f:
                config_data = json.load(f)

            if hasattr(self, "_deserialize_configuration"):
                self._deserialize_configuration(config_data)
            else:
                # Merge config_data with _configuration
                self._merge_configuration(config_data)

            info(
                f"Konfiguracja zostala wczytana z pliku: {self.__config_file_path}",
                message_logger=self._message_logger,
            )
        except Exception as e:
            error(
                f"Błąd podczas wczytywania konfiguracji: {e}",
                message_logger=self._message_logger,
            )

    def _merge_configuration(self, config_data: dict):
        """
        Merges loaded configuration data with default configuration.

        Updates existing keys in _configuration from config_data.
        Adds new keys from config_data that don't exist in _configuration.
        Preserves keys in _configuration that don't exist in config_data.

        Args:
            config_data (dict): Configuration data loaded from file
        """
        for key, value in config_data.items():
            if key in self._configuration:
                # Update existing key
                if isinstance(self._configuration[key], dict) and isinstance(
                    value, dict
                ):
                    # Recursively merge nested dictionaries
                    self._configuration[key] = self._merge_dict_recursive(
                        self._configuration[key], value
                    )
                else:
                    # Direct assignment for non-dict values
                    self._configuration[key] = value
            else:
                # Add new key that doesn't exist in default configuration
                self._configuration[key] = value

    def _merge_dict_recursive(self, default_dict: dict, config_dict: dict) -> dict:
        """
        Recursively merges two dictionaries.

        Args:
            default_dict (dict): The default dictionary (base)
            config_dict (dict): The configuration dictionary (overlay)

        Returns:
            dict: Merged dictionary
        """
        result = copy.deepcopy(default_dict)

        for key, value in config_dict.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # Recursively merge nested dictionaries
                result[key] = self._merge_dict_recursive(result[key], value)
            else:
                # Direct assignment for non-dict values or new keys
                result[key] = value

        return result

    def _extract_config_differences(self, default: dict, current: dict) -> dict:
        """
        Extracts only the differences between default and current configuration.

        Recursively compares default and current configurations and returns
        a dictionary containing only the changed values.

        Args:
            default (dict): The default configuration (original defaults)
            current (dict): The current configuration (potentially modified)

        Returns:
            dict: Dictionary containing only the changed values
        """
        differences = {}

        # Check for new or modified keys in current config
        for key, current_value in current.items():
            if key not in default:
                # New key that doesn't exist in default
                differences[key] = current_value
            elif isinstance(current_value, dict) and isinstance(default[key], dict):
                # Recursively check nested dictionaries
                nested_diff = self._extract_config_differences(
                    default[key], current_value
                )
                if nested_diff:  # Only add if there are actual differences
                    differences[key] = nested_diff
            elif current_value != default[key]:
                # Value has changed
                differences[key] = current_value

        return differences

    def _execute_before_shutdown(self):
        pass

    def shutdown(self):
        """
        Public method for graceful shutdown of the EventListener.

        This method should be called to properly close the listener and all its resources.
        It's thread-safe and can be called multiple times without issues.

        Args:
            suppress_uvicorn_errors (bool): If True, suppresses CancelledError messages from Uvicorn

        Returns:
            bool: True if shutdown was successful, False if already shutting down
        """
        return self.__shutdown()

    def __stop_local_check(self):
        """
        Stops the local data check loop.
        Attempts to safely terminate the thread within 2 seconds.
        """
        try:
            info("Stopping local data check", message_logger=self._message_logger)
            if (
                hasattr(self, "local_check_thread")
                and self.local_check_thread
                and self.local_check_thread.is_alive()
            ):
                self.local_check_thread.join(timeout=2.0)
                if self.local_check_thread.is_alive():
                    error(
                        "Local check thread did not terminate within timeout",
                        message_logger=self._message_logger,
                    )
        except Exception as e:
            error(
                f"Error stopping local check thread: {e}",
                message_logger=self._message_logger,
            )

    def __stop_analysis(self):
        try:
            info("Stopping analysis", message_logger=self._message_logger)
            if (
                hasattr(self, "analysis_thread")
                and self.analysis_thread
                and self.analysis_thread.is_alive()
            ):
                self.analysis_thread.join(timeout=2.0)  # Czekamy maksymalnie 2 sekundy
                if self.analysis_thread.is_alive():
                    error(
                        "Analysis thread did not terminate within timeout",
                        message_logger=self._message_logger,
                    )
        except Exception as e:
            error(
                f"Error stopping analysis thread: {e}",
                message_logger=self._message_logger,
            )

    def __stop_send_event(self):
        try:
            info("Stopping send_event", message_logger=self._message_logger)
            if (
                hasattr(self, "send_event_thread")
                and self.send_event_thread
                and self.send_event_thread.is_alive()
            ):
                self.send_event_thread.join(
                    timeout=2.0
                )  # Czekamy maksymalnie 2 sekundy
                if self.send_event_thread.is_alive():
                    error(
                        "Send event thread did not terminate within timeout",
                        message_logger=self._message_logger,
                    )
        except Exception as e:
            error(
                f"Error stopping send event thread: {e}",
                message_logger=self._message_logger,
            )

    def __stop_state_update_thread(self):
        try:
            info("Stopping state update thread", message_logger=self._message_logger)
            if (
                hasattr(self, "__state_update_thread")
                and self.__state_update_thread
                and self.__state_update_thread.is_alive()
            ):
                self.__state_update_thread.join(timeout=1.0)
                if self.__state_update_thread.is_alive():
                    error(
                        "State update thread did not terminate within timeout",
                        message_logger=self._message_logger,
                    )
        except Exception as e:
            error(
                f"Error stopping state update thread: {e}",
                message_logger=self._message_logger,
            )

    def __shutdown(self):
        """
        Safely shuts down all components.

        Saves queue state and configuration, stops all threads and loops,
        and releases FastAPI server resources.

        Returns:
            bool: True if shutdown completed successfully
        """
        try:
            info(
                f"Zamykanie {self.__class__.__name__}...",
                message_logger=None,
            )

            # Set shutdown flag first to stop all loops
            self._shutdown_requested = True

            # Give threads time to see the shutdown flag and complete current iterations
            self._message_logger = None  # Wylaczamy message logger

            time.sleep(
                0.5
            )  # Reduced from 0.5s - just enough for threads to see the flag

            # Allow subclasses to perform custom cleanup
            self._execute_before_shutdown()

            # Stop all threads in proper order
            self.__stop_state_update_thread()
            self.__stop_local_check()
            self.__stop_analysis()
            self.__stop_send_event()

            # Save state after threads are stopped to avoid race conditions
            # self.__save_state()
            self.__save_configuration()

            # Close aiohttp session
            if self.__session:
                info("Closing aiohttp session...", message_logger=self._message_logger)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        loop.create_task(self.__session.close())
                    else:
                        loop.run_until_complete(self.__session.close())
                except Exception as e:
                    error(
                        f"Error closing aiohttp session: {e}",
                        message_logger=self._message_logger,
                    )

            # Shutdown FastAPI server
            if hasattr(self, "server") and self.server:
                info(
                    "Zamykanie serwera FastAPI...", message_logger=self._message_logger
                )
                try:
                    self.server.should_exit = True
                    if hasattr(self.server, "force_exit"):
                        self.server.force_exit = True
                    self.server.server_info = None
                    self.server.config = None
                    self.server.app = None
                    time.sleep(0.1)
                except Exception as e:
                    error(
                        f"Error during server shutdown: {e}",
                        message_logger=self._message_logger,
                    )

            self.config = None
            self.app = None

            info(
                f"{self.__class__.__name__} został bezpiecznie zamknięty.",
                message_logger=None,
            )

            # OSTATECZNOŚĆ - wymuszenie zakończenia procesu po krótkim czasie
            def force_exit():
                time.sleep(2.0)  # Dajemy 2 sekundy na naturalne zakończenie
                warning("Forcing process exit after timeout...", message_logger=None)
                os._exit(0)  # Wymuś zakończenie procesu

            force_thread = threading.Thread(target=force_exit, daemon=True)
            force_thread.start()

            return True

        except Exception as e:
            error(f"Błąd podczas zamykania: {e}", message_logger=self._message_logger)
            return False

    def __del__(self):
        try:
            debug(f"__del__ event listenera", message_logger=self._message_logger)
            if not self._shutdown_requested:
                self.shutdown()
        except Exception:
            # Ignorujemy błędy podczas destruktora
            pass

    async def __analyze_queues(self):
        """
        Main loop analyzing all event queues.
        """
        debug("Starting analyze_queues loop", message_logger=self._message_logger)
        loop = ControlLoop(
            name="analyze_queues_loop",
            period=1 / self.__analyze_queue_frequency,
            warning_printer=self.__raport_overtime,
            message_logger=self._message_logger,
        )

        # Czekamy na gotowość systemu
        self._system_ready.wait()
        debug(
            f"Analyze_queues loop activated...",
            message_logger=self._message_logger,
        )

        while not self._shutdown_requested:
            loop.loop_begin()
            try:
                with self.__atomic_operation_for_incoming_events():
                    if len(self.__incoming_events) > 0:
                        debug(
                            f"Analyzing incoming events queue. size={len(self.__incoming_events)}",
                            message_logger=self._message_logger,
                        )
                        await self.__analyze_incoming_events()
            except TimeoutError as e:
                error(
                    f"Timeout in analyze_queues: {e}",
                    message_logger=self._message_logger,
                )
            except Exception as e:
                error(
                    f"Error in analyze_queues: {e}", message_logger=self._message_logger
                )
            loop.loop_end()
        debug("Analyze_queues loop ended", message_logger=self._message_logger)

    # MARK: Incoming events
    async def __analyze_incoming_events(self):
        """
        Analyzes a single event queue.

        Args:
            queue (list[Event]): List of events to analyze
        """
        events_to_process = self.__incoming_events.copy()
        self.__incoming_events.clear()

        new_queue = []  # Tworzymy nową kolejkę dla eventów do zachowania
        for event in events_to_process:
            try:
                if not event.is_system_event:
                    debug(
                        f"Analyzing incoming event: {event}",
                        message_logger=self._message_logger,
                    )
                should_remove = True
                match event.event_type:
                    case "CMD_INITIALIZED":
                        if event.result is None:
                            await self._handle_cmd_initialized(event)
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "CMD_RUN":
                        if event.result is None:
                            await self._handle_cmd_run(event)
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "CMD_RESTART":
                        if event.result is None:
                            await self._handle_cmd_restart(event)
                            # CMD_RESTART obsługuje odpowiedź samodzielnie, nie przekazujemy dalej
                            should_remove = True
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "CMD_PAUSE":
                        if event.result is None:
                            await self._handle_cmd_pause(event)
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "CMD_HARD_STOP":
                        if event.result is None:
                            await self._handle_cmd_hard_stop(event)
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "CMD_SOFT_STOP":
                        if event.result is None:
                            await self._handle_cmd_soft_stop(event)
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "CMD_STOPPED":
                        if event.result is None:
                            await self._handle_cmd_stopped(event)
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "CMD_ACK":
                        if event.result is None:
                            await self._handle_cmd_ack(event)
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "CMD_GET_STATE":
                        if event.result is None:
                            await self._handle_get_state_command(event)
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "CMD_HEALTH_CHECK":
                        if event.result is None:
                            try:
                                await self.__state_handler(event)

                            except Exception as e:
                                error(
                                    f"Error in __state_handler: {e}",
                                    message_logger=self._message_logger,
                                )
                                event.result = Result(
                                    result="failure",
                                    error_message=f"Failed to get state: {e}",
                                )
                                await self._reply(event)
                        else:
                            should_remove = await self.__analyze_event_with_fsm(event)

                    case "discovery":
                        pass

                    case _:
                        should_remove = await self.__analyze_event_with_fsm(event)
                if not should_remove:
                    new_queue.append(event)
            except Exception as e:
                error(
                    f"Error processing event: {e}", message_logger=self._message_logger
                )
                error(
                    f"Event data: {event.__dict__}", message_logger=self._message_logger
                )
                error(
                    f"Traceback:\n{traceback.format_exc()}",
                    message_logger=self._message_logger,
                )
                self._shutdown_requested = True
                new_queue.append(event)

        # Na końcu zastępujemy oryginalną kolejkę nową
        self.__incoming_events.extend(new_queue)

    def __start_analysis(self):
        """Starts the event queue analysis thread."""
        info("Starting analysis", message_logger=self._message_logger)
        self.analysis_thread = threading.Thread(
            target=lambda: asyncio.run(self.__analyze_queues()), daemon=True
        )
        self.analysis_thread.start()

    async def __discovery(self):
        debug("Starting analyze_queues loop", message_logger=self._message_logger)
        loop = ControlLoop(
            name="analyze_queues_loop",
            period=1 / self.__discovery_frequency,
            warning_printer=False,
            message_logger=self._message_logger,
        )

        # Czekamy na gotowość systemu
        self._system_ready.wait()

        debug("Discovery loop activated...", message_logger=self._message_logger)

        while not self._shutdown_requested:
            loop.loop_begin()
            loop.loop_end()
        debug("Discovery loop ended", message_logger=self._message_logger)

    def __start_discovering(self):
        """Starts the event queue analysis thread."""
        info("Starting analysis", message_logger=self._message_logger)
        self.discovering_thread = threading.Thread(
            target=lambda: asyncio.run(self.__discovery()), daemon=True
        )
        self.discovering_thread.start()

    async def __state_handler(self, event: Event):
        try:
            # Instantly get the latest pre-calculated state
            with self.__lock_for_state_data:
                state_data = self._latest_state_data

            event.result = Result(result="success", data=state_data)
            await self._reply(event)

        except Exception as e:
            error(
                f"Error in state handler: {e}, {traceback.format_exc()}",
                message_logger=self._message_logger,
            )
            event.result = Result(result="error", error_message=str(e))
            await self._reply(event)

    async def __discovery_handler(self, event: Event):
        # TODO: dodać logikę wykrywania sąsiadów
        pass

    async def __event_handler(self, event: Event):
        """
        Handles incoming events by assigning them to appropriate queues.

        Args:
            event (Event): Event to handle

        Note:
            Events are assigned to queues based on their priority.
            Operation is protected by mutex.
        """
        try:
            self._event_receive_debug(event)

            with self.__atomic_operation_for_incoming_events():
                if event.event_type == "cumulative":
                    for event_data in event.data["events"]:
                        unpacked_event = Event(**event_data)
                        self.__incoming_events.append(unpacked_event)
                    debug(
                        f"Unpacked cumulative event into {len(event.data['events'])} events",
                        message_logger=self._message_logger,
                    )
                else:
                    self.__incoming_events.append(event)
                    if not event.is_system_event:
                        debug(
                            f"Added event to incomming events queue: {event}",
                            message_logger=self._message_logger,
                        )
            self.__received_events += 1
        except Exception as e:
            error(f"__event_handler: {e}", message_logger=self._message_logger)

    # MARK: Local data
    async def __check_local_data_loop(self):
        """
        Main loop for checking local data.
        """
        debug("Starting check_local_data loop", message_logger=self._message_logger)
        loop = ControlLoop(
            name="check_local_data_loop",
            period=1 / self.__check_local_data_frequency,
            warning_printer=self.__raport_overtime,
            message_logger=self._message_logger,
        )

        # Czekamy na gotowość systemu
        self._system_ready.wait()

        debug("Check_local_data loop activated...", message_logger=self._message_logger)

        while not self._shutdown_requested:
            if self.__check_local_data_frequency_changed:
                loop.period = 1 / self.__check_local_data_frequency
                self.__check_local_data_frequency_changed = False

            loop.loop_begin()
            try:
                # Event processing per state zgodnie z FSM analizą
                match self.__fsm_state:
                    case EventListenerState.UNKNOWN:
                        pass
                    case EventListenerState.STOPPED:
                        await self.on_stopped()
                    case EventListenerState.INITIALIZING:
                        # Wczytanie zapisanych kolejek
                        if self.__load_state:
                            self.__load_state()
                        await self.on_initializing()
                        self._change_fsm_state(EventListenerState.INITIALIZED)
                    case EventListenerState.INITIALIZED:
                        await self.on_initialized()
                    case EventListenerState.STARTING:
                        await self.on_starting()
                        self._change_fsm_state(EventListenerState.RUN)
                    case EventListenerState.RUN:
                        await self.on_run()
                        await self._check_local_data()

                        if (
                            loop.loop_counter % self.__check_local_data_frequency == 0
                        ):  # co 1 sekunde
                            self.__received_events_per_second = (
                                self.__received_events - self.__prev_received_events
                            )
                            self.__sended_events_per_second = (
                                self.__sended_events - self.__prev_sended_events
                            )

                            # Aktualizacja poprzednich wartości i czasu
                            self.__prev_received_events = self.__received_events
                            self.__prev_sended_events = self.__sended_events

                    case EventListenerState.PAUSING:
                        await self.on_pausing()
                        self._change_fsm_state(EventListenerState.PAUSE)
                    case EventListenerState.RESUMING:
                        await self.on_resuming()
                        self._change_fsm_state(EventListenerState.RUN)
                    case EventListenerState.PAUSE:
                        await self.on_pause()
                    case EventListenerState.SOFT_STOPPING:
                        await self.on_soft_stopping()
                        self._change_fsm_state(EventListenerState.INITIALIZED)
                    case EventListenerState.HARD_STOPPING:
                        await self.on_hard_stopping()
                        self._change_fsm_state(EventListenerState.STOPPED)
                    case EventListenerState.STOPPING:
                        self.__save_state()
                        await self.on_stopping()
                        self._change_fsm_state(EventListenerState.STOPPED)
                    case EventListenerState.FAULT:
                        await self.on_fault()
                    case EventListenerState.ON_ERROR:
                        await self.on_error()
                        self._change_fsm_state(EventListenerState.FAULT)
                    case EventListenerState.ACK:
                        await self.on_ack()

                        self._error = False
                        self._error_code = 0
                        self._error_message = None

                        self.__save_state()
                        self._change_fsm_state(EventListenerState.STOPPED)
                    case _:
                        error(
                            f"Unknown state: {self.__fsm_state}",
                            message_logger=self._message_logger,
                        )
            except Exception as e:
                error(f"Error in check_local_data: {e}")
                self._change_fsm_state(EventListenerState.ON_ERROR)

            loop.loop_end()

        debug("Check_local_data loop ended", message_logger=self._message_logger)

    def __start_local_check(self):
        self.local_check_thread = threading.Thread(
            target=lambda: asyncio.run(self.__check_local_data_loop()),
            name="local_check_thread",
        )
        self.local_check_thread.daemon = True
        self.local_check_thread.start()

    def __start_send_event(self):
        """
        Starts the event sending thread.
        """
        info("Starting send_event", message_logger=self._message_logger)
        self.send_event_thread = threading.Thread(
            target=self._run_send_event_loop, daemon=True
        )
        self.send_event_thread.start()

    def __start_state_update_thread(self):
        self.__state_update_thread = threading.Thread(
            target=self.__update_system_state_loop, name="state_update_thread"
        )
        self.__state_update_thread.daemon = True
        self.__state_update_thread.start()

    def _run_send_event_loop(self):
        """Run the send event loop in a separate thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.__send_event_loop())
        finally:
            loop.close()

    async def __send_event_loop(self):
        """
        Main loop for sending events from the dispatch queue.
        """
        debug("Starting send_event loop", message_logger=self._message_logger)
        control_loop = ControlLoop(
            name="send_event_loop",
            period=1 / self.__send_queue_frequency,
            warning_printer=self.__raport_overtime,
            message_logger=self._message_logger,
        )

        # Czekamy na gotowość systemu
        self._system_ready.wait()

        debug("Send_event loop activated...", message_logger=self._message_logger)

        # Initialize aiohttp session
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=100,  # Maksymalnie 100 połączeń łącznie
                limit_per_host=30,  # Maksymalnie 30 do jednego hosta
                keepalive_timeout=5,  # Utrzymuj połączenia przez 5s
                force_close=False,  # Reuse connections
                enable_cleanup_closed=True,  # Automatyczne czyszczenie
            )
        ) as session:
            while not self._shutdown_requested:
                control_loop.loop_begin()

                with self.__atomic_operation_for_events_to_send():
                    local_queue = self.__events_to_send.copy()
                    self.__events_to_send.clear()

                if local_queue:
                    # debug(
                    #     f"Sending events: {len(local_queue)}",
                    #     message_logger=self._message_logger,
                    # )

                    if self.__use_cumulative_send:
                        # Group events by destination
                        events_by_destination = {}
                        send_queue = []  # Initialize send_queue here

                        for event_data in local_queue:
                            # Skip events that are already cumulative - they should be unpacked
                            if (
                                event_data["event"].event_type == "cumulative"
                                and "events" in event_data["event"].data
                            ):
                                # Unpack cumulative event and add its events directly to the send_queue
                                for event_dict in event_data["event"].data["events"]:
                                    individual_event = Event(**event_dict)
                                    dest_key = (
                                        individual_event.destination_address,
                                        individual_event.destination_port,
                                    )
                                    if dest_key not in events_by_destination:
                                        events_by_destination[dest_key] = []
                                    events_by_destination[dest_key].append(event_data)
                                continue

                            dest_key = (
                                event_data["event"].destination_address,
                                event_data["event"].destination_port,
                            )
                            if dest_key not in events_by_destination:
                                events_by_destination[dest_key] = []
                            events_by_destination[dest_key].append(event_data)

                        # Create temporary queue with cumulative events for sending
                        for event_group in events_by_destination.values():
                            if len(event_group) == 1:
                                # Single event - keep as is
                                send_queue.append(event_group[0])
                            else:
                                # Multiple events - create cumulative event only for sending
                                first_event = event_group[0]["event"]
                                cumulative_event = Event(
                                    source=first_event.source,
                                    source_address=first_event.source_address,
                                    source_port=first_event.source_port,
                                    destination=first_event.destination,
                                    destination_address=first_event.destination_address,
                                    destination_port=first_event.destination_port,
                                    event_type="cumulative",
                                    payload=sum(
                                        e["event"].payload for e in event_group
                                    ),
                                    data={
                                        "events": [
                                            e["event"].to_dict() for e in event_group
                                        ]
                                    },
                                )
                                send_queue.append({
                                    "event": cumulative_event,
                                    "retry_count": 0,
                                    "original_events": event_group,  # Store original events for retry
                                })

                        local_queue = send_queue

                    start_time = time.perf_counter()

                    # if self.__use_parallel_send:

                    async def send_single_event(event_data):
                        event = event_data["event"]
                        retry_count = event_data["retry_count"]

                        if retry_count >= self.__retry_count:
                            error(
                                f"Event {event.event_type} failed after {self.__retry_count} retries - dropping",
                                message_logger=self._message_logger,
                            )
                            return None

                        try:
                            url = f"http://{event.destination_address}:{event.destination_port}{event.destination_endpoint}"
                            event_start_time = time.perf_counter()

                            try:
                                with self._event_send_debug(event):
                                    async with session.post(
                                        url,
                                        json=event.to_dict(),
                                        timeout=aiohttp.ClientTimeout(total=0.025),
                                    ) as response:
                                        if response.status == 200:
                                            self.__sended_events += 1
                                            elapsed = (
                                                time.perf_counter() - event_start_time
                                            ) * 1000
                                            return None
                            except asyncio.TimeoutError:
                                error(
                                    f"Timeout sending event to {url}",
                                    message_logger=self._message_logger,
                                )
                                # If this was a cumulative event, return original events
                                if event.event_type == "cumulative":
                                    return [
                                        {
                                            "event": Event(**e),
                                            "retry_count": retry_count + 1,
                                        }
                                        for e in event.data["events"]
                                    ]
                                return {
                                    "event": event,
                                    "retry_count": retry_count + 1,
                                }

                        except Exception as e:
                            error(
                                f"Error sending event: {e}",
                                message_logger=self._message_logger,
                            )
                            # If this was a cumulative event, return original events
                            if event.event_type == "cumulative":
                                return [
                                    {
                                        "event": Event(**e),
                                        "retry_count": retry_count + 1,
                                    }
                                    for e in event.data["events"]
                                ]
                            return {
                                "event": event,
                                "retry_count": retry_count + 1,
                            }

                    # Create and run all tasks in parallel
                    tasks = [send_single_event(data) for data in local_queue]
                    results = await asyncio.gather(*tasks, return_exceptions=True)

                    # Collect failed events
                    failed_events = []
                    for r in results:
                        if isinstance(r, (dict, list)):  # means failed event(s)
                            if isinstance(
                                r, list
                            ):  # original events from failed cumulative
                                failed_events.extend(r)
                            else:  # single failed event
                                failed_events.append(r)

                    # If there are failed events, add them back
                    if failed_events:
                        with self.__atomic_operation_for_events_to_send():
                            self.__events_to_send.extend(failed_events)

                    total_elapsed = (time.perf_counter() - start_time) * 1000
                    debug(
                        f"Send time: {total_elapsed:.4f} ms for {len(local_queue)} events",
                        message_logger=self._message_logger,
                    )

                control_loop.loop_end()
            debug("Send_data loop ended", message_logger=self._message_logger)

    # MARK: Analyze event
    async def __analyze_event_with_fsm(self, event: Event) -> bool:
        """Analizuje event w zależności od aktualnego stanu FSM, a następnie wywołuje logikę potomnych.

        Response Patterns per State zgodnie z analizą:
        - RUN: Pełne responses z przetwarzaniem + wywołanie _analyze_event z potomnych
        - INITIALIZED: "System in initialization state"
        - PAUSE: "System paused, operation buffered"
        - FAULT: "System in fault state, operation buffered"
        - STOPPED: "Service stopped" - odrzuca eventy biznesowe
        - ON_ERROR: Brak przetwarzania, automatyczne przekierowanie
        """
        match self.__fsm_state:
            case EventListenerState.RUN:
                # RUN: Pełne przetwarzanie wszystkich eventów - wywołanie logiki potomnych
                try:
                    return await self._analyze_event(event)
                except Exception as e:
                    error(
                        f"Error in _analyze_event: {e} timestamp={event.timestamp}",
                        message_logger=self._message_logger,
                    )
                    # Przy błędzie w logice biznesowej przechodzi do ON_ERROR
                    self._change_fsm_state(EventListenerState.ON_ERROR)
                    return False  # Zachowujemy event
            case EventListenerState.INITIALIZED:
                # INITIALIZED: Informacyjne odpowiedzi
                try:
                    if event.result is None:
                        event.result = Result(
                            result="info",
                            data={
                                "message": "System in initialization state",
                                "fsm_state": "INITIALIZED",
                            },
                        )
                        await self._reply(event)
                    return True
                except Exception as e:
                    error(
                        f"Error in INITIALIZED state: {e}",
                        message_logger=self._message_logger,
                    )
                    self._change_fsm_state(EventListenerState.ON_ERROR)
                    return False
            case EventListenerState.PAUSE:
                # PAUSE: Buffering bez przetwarzania
                try:
                    if event.result is None:
                        event.result = Result(
                            result="info",
                            data={
                                "message": "System paused, operation buffered",
                                "fsm_state": "PAUSE",
                            },
                        )
                        await self._reply(event)
                    return False  # Zachowujemy event w buforze
                except Exception as e:
                    error(
                        f"Error in PAUSE state: {e}",
                        message_logger=self._message_logger,
                    )
                    self._change_fsm_state(EventListenerState.ON_ERROR)
                    return False
            case EventListenerState.FAULT:
                # FAULT: Error response - odrzuca eventy
                try:
                    if event.result is None:
                        event.result = Result(
                            result="error",
                            data={
                                "message": "System in fault state",
                                "fsm_state": "FAULT",
                            },
                        )
                        await self._reply(event)
                    return True  # Usuwamy event (odrzucamy)
                except Exception as e:
                    # W FAULT już jesteśmy - logujemy ale zostajemy w FAULT
                    error(
                        f"Error in FAULT state: {e}",
                        message_logger=self._message_logger,
                    )
                    return True  # Usuwamy event nawet przy błędzie w odpowiedzi
            case EventListenerState.STOPPED:
                # STOPPED: Odrzuca eventy biznesowe
                try:
                    if event.result is None:
                        event.result = Result(
                            result="error",
                            data={"message": "Service stopped", "fsm_state": "STOPPED"},
                        )
                        await self._reply(event)
                    return True  # Usuwamy event (odrzucamy)
                except Exception as e:
                    error(
                        f"Error in STOPPED state: {e}",
                        message_logger=self._message_logger,
                    )
                    self._change_fsm_state(EventListenerState.ON_ERROR)
                    return False
            case EventListenerState.ON_ERROR:
                # ON_ERROR: Automatyczne przekierowanie do FAULT
                return False  # Zachowujemy event, system przejdzie do FAULT
            case [
                EventListenerState.INITIALIZING,
                EventListenerState.STARTING,
                EventListenerState.PAUSING,
                EventListenerState.RESUMING,
                EventListenerState.SOFT_STOPPING,
                EventListenerState.HARD_STOPPING,
            ]:
                # Stany przejściowe - informacyjne responses o trwającym przejściu
                if event.result is None:
                    event.result = Result(
                        result="info",
                        data={
                            "message": f"System in transition - {self.__fsm_state.name.lower()}",
                            "fsm_state": self.__fsm_state.name,
                        },
                    )
                    await self._reply(event)
                return True  # Usuwamy event po odpowiedzi
            case _:
                warning(
                    f"Analyze Event -> Unknown state: {self.__fsm_state}",
                    message_logger=self._message_logger,
                )
                return True

    async def _analyze_event(self, event: Event) -> bool:
        """Metoda do przedefiniowania w klasach potomnych dla logiki biznesowej.

        Wywoływana tylko w stanie RUN dla pełnego przetwarzania eventów.

        Args:
            event (Event): Event do analizy

        Returns:
            bool: True jeśli event powinien być usunięty, False jeśli zachowany
        """
        return True  # Domyślnie usuwamy event po przetworzeniu

    async def _check_local_data(self):
        pass

    async def _event(
        self,
        *,
        destination: str = None,
        destination_address: str = "0.0.0.0",
        destination_port: int = 8000,
        event_type: str = "default",
        id: int = None,
        data: dict = {},
        to_be_processed: bool = True,
        maximum_processing_time: float = 20,
        is_system_event: bool = False,
    ) -> Event:
        """
        Creates a new event and adds it to the sending queue.

        Args:
            destination (str): The name of the destination listener.
            destination_address (str, optional): The IP address of the destination. Defaults to "0.0.0.0".
            destination_port (int, optional): The port of the destination. Defaults to 8000.
            event_type (str, optional): The type of the event. Defaults to "default".
            id (int, optional): An optional ID for the event. Defaults to None.
            data (dict, optional): A dictionary of data to send with the event. Defaults to {}.
            to_be_processed (bool, optional): Flag indicating if the event requires processing. Defaults to True.
            maximum_processing_time (float, optional): Maximum time in seconds for processing. Defaults to 20.

        Returns:
            Event: The created event object, or None if an error occurred.
        """
        event = Event(
            source=self.__name,
            source_address=self.__address,
            source_port=self.__port,
            destination=destination,
            destination_address=destination_address,
            destination_port=destination_port,
            event_type=event_type,
            data=data,
            id=id,
            to_be_processed=to_be_processed,
            is_processing=False,
            is_system_event=is_system_event,
            maximum_processing_time=maximum_processing_time,
        )

        try:
            with self.__atomic_operation_for_events_to_send():
                self.__events_to_send.append({"event": event, "retry_count": 0})
        except TimeoutError as e:
            error(f"__event: {e}", message_logger=self._message_logger)
            return None
        except Exception as e:
            error(f"__event: {e}", message_logger=self._message_logger)
            return None
        return event

    async def _cumulative_reply(self, events: list[Event]):
        for event in events:
            await self._reply(event)

    async def _reply(self, event: Event):
        """
        Creates and adds an event response to the sending queue.

        This method ensures symmetrical communication by sending the reply
        to the same endpoint from which the original event was received.

        Args:
            event (Event): The original event being responded to.

        Note:
            The processing result must be set in `event.result` before calling this method.

        Raises:
            ValueError: If `event.result` is None.
        """
        if event.result is None:
            raise ValueError("Result cannot be None")
        new_event = event.model_copy()
        new_event.source = event.destination
        new_event.source_address = event.destination_address
        new_event.source_port = event.destination_port
        new_event.destination = event.source
        new_event.destination_address = event.source_address
        new_event.destination_port = event.source_port
        new_event.id = event.id
        new_event.result = event.result
        new_event.is_system_event = event.is_system_event

        try:
            with self.__atomic_operation_for_events_to_send():
                self.__events_to_send.append({"event": new_event, "retry_count": 0})
                if not new_event.is_system_event:
                    debug(
                        f"Added event to send queue: {new_event}",
                        message_logger=self._message_logger,
                    )
        except TimeoutError as e:
            error(f"_reply: {e}", message_logger=self._message_logger)
            raise

    def start(self):
        """
        Starts the EventListener server.
        """
        info("Starting server", message_logger=self._message_logger)
        try:
            self.server = uvicorn.Server(self.config)

            # Note: startup event is already defined in __init__
            @self.app.on_event("startup")
            async def startup_event():
                info(
                    "FastAPI server started, waiting for stabilization...",
                    message_logger=self._message_logger,
                )
                # Initialize aiohttp session
                self.__session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(
                        limit=0,  # No connection limit
                        ttl_dns_cache=300,
                        use_dns_cache=True,
                        force_close=False,
                    )
                )
                await asyncio.sleep(1)  # Czekamy na stabilizację
                info(
                    "System stabilized, starting processing threads...",
                    message_logger=self._message_logger,
                )
                self._system_ready.set()  # Wysyłamy sygnał do threadów
                # FSM sterowany komendami - nie ma automatycznych przejść poza UNKNOWN→STOPPED
                info(
                    "System ready, waiting for FSM commands",
                    message_logger=self._message_logger,
                )

            # Uruchamiamy serwer w osobnym thread żeby nie blokować głównego procesu

            server_thread = threading.Thread(target=self.server.run, daemon=False)
            server_thread.start()

            # Czekamy na zakończenie serwera lub shutdown request
            try:
                while server_thread.is_alive() and not self._shutdown_requested:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                info(
                    "Otrzymano KeyboardInterrupt, rozpoczynam shutdown...",
                    message_logger=self._message_logger,
                )
                self.shutdown()

            # Czekamy na zakończenie server thread
            if server_thread.is_alive():
                info(
                    "Czekam na zakończenie serwera...",
                    message_logger=self._message_logger,
                )
                server_thread.join(timeout=5.0)
                if server_thread.is_alive():
                    warning(
                        "Serwer nie zakończył się w czasie, wymuszam zakończenie",
                        message_logger=self._message_logger,
                    )

        except Exception as e:
            error(
                f"Błąd podczas uruchamiania serwera: {e}",
                message_logger=self._message_logger,
            )

    def _add_to_processing(self, event: Event) -> bool:
        """
        Moves event to processing queue using dictionary structure for faster lookup.

        Args:
            event (Event): Event to move

        Returns:
            bool: True if operation succeeded, False otherwise
        """
        try:
            event.is_processing = True
            with self.__atomic_operation_for_processing_events():
                event_timestamp = event.timestamp.isoformat(sep=" ")

                self._processing_events_dict[event_timestamp] = event

                self._event_add_to_processing_debug(event)
            return True
        except TimeoutError as e:
            error(f"_add_to_processing: {e}", message_logger=self._message_logger)
            return False
        except Exception as e:
            error(
                f"_add_to_processing: Error adding event to processing queue: {e}",
                message_logger=self._message_logger,
            )
            return False

    def _find_and_remove_processing_event(self, event: Event) -> Event | None:
        try:
            # Obsługa zarówno datetime jak i string timestamp
            timestamp_key = event.timestamp.isoformat(sep=" ")

            debug(
                f"Searching for event for remove in processing queue: id={event.id} event_type={event.event_type} timestamp={timestamp_key}",
                message_logger=self._message_logger,
            )

            with self.__atomic_operation_for_processing_events():
                event = self._processing_events_dict[timestamp_key]
                del self._processing_events_dict[timestamp_key]
                self._event_find_and_remove_debug(event)
                return event

        except TimeoutError as e:
            error(
                f"Exception TimeoutError: _find_and_remove_processing_event: {e}",
                message_logger=self._message_logger,
            )
            return None
        except Exception as e:
            error(
                f"Exception: _find_and_remove_processing_event: {e}",
                message_logger=self._message_logger,
            )
            return None

    def __update_system_state_loop(self):
        debug("Starting system state update loop", message_logger=self._message_logger)

        last_proc_cpu_times = {}
        last_cpu_calc_time = 0.0

        while not self._shutdown_requested:
            try:
                main_process = psutil.Process(os.getpid())
                children = main_process.children(recursive=True)
                all_processes = [main_process] + children

                # --- Non-blocking CPU and resource calculation ---
                wall_time_now = time.monotonic()

                proc_cpu_times_now = {}
                total_memory_rss = 0
                total_memory_vms = 0
                process_count = 0

                for p in all_processes:
                    try:
                        proc_cpu_times_now[p.pid] = p.cpu_times()
                        mem_info = p.memory_info()
                        total_memory_rss += mem_info.rss
                        total_memory_vms += mem_info.vms
                        process_count += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                total_cpu_percent = 0.0
                if last_cpu_calc_time > 0:
                    wall_time_delta = wall_time_now - last_cpu_calc_time
                    if wall_time_delta > 0:
                        proc_cpu_time_delta = 0
                        for (
                            pid,
                            cpu_times_now,
                        ) in proc_cpu_times_now.items():
                            if pid in last_proc_cpu_times:
                                cpu_times_before = last_proc_cpu_times[pid]
                                proc_cpu_time_delta += (
                                    cpu_times_now.user - cpu_times_before.user
                                ) + (cpu_times_now.system - cpu_times_before.system)

                        if proc_cpu_time_delta > 0:
                            total_cpu_percent = (
                                proc_cpu_time_delta / wall_time_delta
                            ) * 100
                            # Normalize by number of cores
                            total_cpu_percent /= psutil.cpu_count()

                # Update state for the next call
                last_proc_cpu_times = proc_cpu_times_now
                last_cpu_calc_time = wall_time_now
                # --- End of calculation ---

                state_data = {
                    "process_count": process_count,
                    "cpu_percent": round(total_cpu_percent, 2),
                    "memory_rss_mb": round(total_memory_rss / (1024 * 1024), 2),
                    "memory_vms_mb": round(total_memory_vms / (1024 * 1024), 2),
                }

                with self.__lock_for_state_data:
                    self._latest_state_data = state_data

            except Exception as e:
                error(
                    f"Error in state update thread: {e}",
                    message_logger=self._message_logger,
                )

            # Sleep for the desired interval
            time.sleep(1.0 / self.__state_update_frequency)

        debug("System state update loop ended", message_logger=self._message_logger)

    # MARK: OVERLOADERS
    async def on_initializing(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZING.
        Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
        pass

    async def on_initialized(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZED.
        Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
        pass

    async def on_starting(self):
        """Metoda wywoływana podczas przejścia w stan STARTING.
        Tu komponent przygotowuje się do uruchomienia głównych operacji."""
        pass

    async def on_run(self):
        """Metoda wywoływana podczas przejścia w stan RUN.
        Tu komponent rozpoczyna swoje główne zadania operacyjne."""
        pass

    async def on_pausing(self):
        """Metoda wywoływana podczas przejścia w stan PAUSING.
        Tu komponent przygotowuje się do wstrzymania operacji."""
        pass

    async def on_pause(self):
        """Metoda wywoływana podczas przejścia w stan PAUSE.
        Tu komponent jest wstrzymany ale gotowy do wznowienia."""
        pass

    async def on_resuming(self):
        """Metoda wywoływana podczas przejścia RESUMING (PAUSE → RUN).
        Tu komponent przygotowuje się do wznowienia operacji."""
        pass

    async def on_stopping(self):
        """Metoda wywoływana podczas przejścia w stan STOPPING.
        Tu komponent finalizuje wszystkie zadania przed całkowitym zatrzymaniem."""
        pass

    async def on_stopped(self):
        """Metoda wywoływana po przejściu w stan STOPPED.
        Tu komponent jest całkowicie zatrzymany i wyczyszczony."""
        pass

    async def on_soft_stopping(self):
        """Metoda wywoływana podczas przejścia SOFT_STOPPING (RUN → INITIALIZED).
        Tu komponent kończy bieżące operacje ale zachowuje stan."""
        pass

    async def on_hard_stopping(self):
        """Metoda wywoływana podczas przejścia HARD_STOPPING (PAUSE → STOPPED).
        Tu komponent kończy bieżące operacje i zapisuje stan."""
        pass

    async def on_ack(self):
        """Metoda wywoływana po otrzymaniu ACK operatora ze stanu FAULT.
        Tu komponent wykonuje operacje czyszczenia i przygotowania do stanu STOPPED.
        """
        pass

    async def on_error(self):
        """Metoda wywoływana podczas przejścia w stan ON_ERROR.
        Tu komponent przechodzi w stan błędu i oczekuje na ACK operatora."""
        pass

    async def on_fault(self):
        """Metoda wywoływana podczas przejścia w stan FAULT.
        Tu komponent przechodzi w stan błędu i oczekuje na ACK operatora."""
        pass

    def _change_fsm_state(self, new_state: EventListenerState):
        """Zmienia stan FSM i wywołuje odpowiednie metody"""
        info(
            f"EventListener FSM transition from '{self.__fsm_state.name}' to '{new_state.name}' state",
            message_logger=self._message_logger,
        )
        self.__fsm_state = new_state

    async def _handle_cmd_initialized(self, event: Event):
        """Obsługa CMD_INITIALIZED - przejście DO stanu INITIALIZED z różnych stanów źródłowych"""
        match self.__fsm_state:
            case EventListenerState.STOPPED:
                # STOPPED → INITIALIZING → INITIALIZED
                self._change_fsm_state(EventListenerState.INITIALIZING)

            case EventListenerState.RUN:
                # RUN → SOFT_STOPPING → INITIALIZED (graceful shutdown)
                self._change_fsm_state(EventListenerState.SOFT_STOPPING)

            case _:
                warning(
                    f"Received CMD_INITIALIZED in unexpected state: {self.__fsm_state.name}",
                    message_logger=self._message_logger,
                )

    async def _handle_cmd_run(self, event: Event):
        """Obsługa CMD_RUN - przejście DO stanu RUN z różnych stanów źródłowych"""
        match self.__fsm_state:
            case EventListenerState.INITIALIZED:
                # INITIALIZED → STARTING → RUN
                self._change_fsm_state(EventListenerState.STARTING)

            case EventListenerState.PAUSE:
                # PAUSE → RESUMING → RUN
                self._change_fsm_state(EventListenerState.RESUMING)

            case _:
                warning(
                    f"Received CMD_RUN in unexpected state: {self.__fsm_state.name}",
                    message_logger=self._message_logger,
                )

    async def _handle_cmd_restart(self, event: Event):
        """Obsługa CMD_RESTART - zatrzymanie programu przez shutdown, automatyczny restart z systemctl"""
        match self.__fsm_state:
            case EventListenerState.STOPPED:
                # Najpierw wysyłamy odpowiedź że restart jest akceptowany
                event.result = Result(
                    result="success",
                    data={"message": "Restart accepted, shutting down system"},
                )
                await self._reply(event)

                # Dajemy czas na wysłanie odpowiedzi
                await asyncio.sleep(0.1)

                # Dopiero teraz wykonujemy shutdown
                info(
                    "CMD_RESTART: Initiating system shutdown after successful response",
                    message_logger=self._message_logger,
                )
                self.shutdown()

            case _:
                # Wysyłamy odpowiedź o błędzie - restart niemożliwy
                event.result = Result(
                    result="error",
                    error_message=f"Cannot restart from state {self.__fsm_state.name}. System must be in STOPPED state first.",
                )
                await self._reply(event)

                warning(
                    f"Received CMD_RESTART in unexpected state: {self.__fsm_state.name}, first STOP the program.",
                    message_logger=self._message_logger,
                )

    async def _handle_cmd_pause(self, event: Event):
        """Obsługa CMD_PAUSE - przejście DO stanu PAUSE z różnych stanów źródłowych"""
        match self.__fsm_state:
            case EventListenerState.RUN:
                # RUN → PAUSING → PAUSE
                # Zatrzymujemy local_check thread przy wyjściu z RUN
                self._change_fsm_state(EventListenerState.PAUSING)

            case _:
                warning(
                    f"Received CMD_PAUSE in unexpected state: {self.__fsm_state.name}",
                    message_logger=self._message_logger,
                )

    async def _handle_cmd_hard_stop(self, event: Event):
        """Obsługa CMD_HARD_STOP - przejście DO stanu STOPPED z różnych stanów źródłowych"""
        match self.__fsm_state:
            case EventListenerState.PAUSE:
                # PAUSE → HARD_STOPPING → STOPPED
                self._change_fsm_state(EventListenerState.HARD_STOPPING)

            case EventListenerState.RUN:
                # RUN → PAUSE → HARD_STOPPING → STOPPED (dwustopniowe)
                # Zatrzymujemy local_check thread przy wyjściu z RUN
                await self.on_pausing()
                await self.on_pause()
                self._change_fsm_state(EventListenerState.HARD_STOPPING)

            case _:
                warning(
                    f"Received CMD_HARD_STOP in unexpected state: {self.__fsm_state.name}",
                    message_logger=self._message_logger,
                )

    async def _handle_cmd_stopped(self, event: Event):
        """Obsługa CMD_STOPPED - przejście do stanu STOPPED z dowolnego stanu"""
        match self.__fsm_state:
            case EventListenerState.RUN:
                # RUN → SOFT_STOPPING → STOPPED
                await self.on_soft_stopping()
                self._change_fsm_state(EventListenerState.STOPPING)

            case _:
                # Przejście do stanu STOPPED z dowolnego stanu
                self._change_fsm_state(EventListenerState.STOPPING)

    async def _handle_cmd_ack(self, event: Event):
        """Obsługa CMD_ACK - potwierdzenie operatora ze stanu FAULT → STOPPED"""
        match self.__fsm_state:
            case EventListenerState.FAULT:
                # FAULT → STOPPED (potwierdzenie błędu przez operatora)
                info(
                    "Received operator ACK for FAULT state",
                    message_logger=self._message_logger,
                )
                # await self.on_ack()
                self._change_fsm_state(EventListenerState.ACK)
                info(
                    "Transitioned to STOPPED state after ACK",
                    message_logger=self._message_logger,
                )

            case _:
                warning(
                    f"Received CMD_ACK in unexpected state: {self.__fsm_state.name}",
                    message_logger=self._message_logger,
                )

    async def _handle_get_state_command(self, event: Event):
        # debug(
        #     f"Processing CMD_GET_STATE event ({event}), sending state: {self._state}",
        #     message_logger=self._message_logger,
        # )

        event.data = {}
        event.data["fsm_state"] = self.__fsm_state.name
        # Pola błędu (jeśli klasa potomna je definiuje)
        event.data["error"] = getattr(self, "_error", False)
        event.data["error_code"] = getattr(self, "_error_code", False)
        event.data["error_message"] = getattr(self, "_error_message", None)
        event.result = Result(result="success")
        await self._reply(event)

    def _has_config_changes(self, old_config: dict, new_config: dict) -> bool:
        """
        Checks if there are any changes between two configuration dictionaries.

        Args:
            old_config (dict): Original configuration
            new_config (dict): New configuration to compare

        Returns:
            bool: True if configurations differ, False if identical
        """
        try:
            # Serialize both configs for comparison to handle complex nested objects
            old_serialized = self._serialize_value(old_config)
            new_serialized = self._serialize_value(new_config)

            return old_serialized != new_serialized
        except Exception as e:
            warning(
                f"Error comparing configurations, assuming changes exist: {e}",
                message_logger=self._message_logger,
            )
            return True  # If comparison fails, assume there are changes to be safe
