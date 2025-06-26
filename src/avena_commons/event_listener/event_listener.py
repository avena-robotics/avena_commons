import asyncio
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

# import requests
import uvicorn
import uvicorn.config
import uvicorn.server
from fastapi import FastAPI
from pydantic import BaseModel

from avena_commons.util.control_loop import ControlLoop
from avena_commons.util.logger import MessageLogger, debug, error, info

# from avena_commons.util.measure_time import MeasureTime
from .event import Event

TEMP_DIR = Path("temp")  # Relatywna ścieżka do bieżącego katalogu roboczego


class EventListenerState(Enum):
    IDLE = 0
    INITIALIZED = 1
    RUNNING = 2
    ERROR = 256


class EventListener:
    __el_state: EventListenerState = EventListenerState.IDLE
    __name: str
    __address: str = "0.0.0.0"
    __port: int
    __queue_file_path: str = None
    __config_file_path: str = None
    __retry_count: int = 100000000
    __discovery_neighbours = False

    __incoming_events: list[Event] = []
    _processing_events_dict: dict = {}  # Structure: {event_type: {id: {timestamp: event}}}
    __events_to_send: list[
        dict
    ] = []  # Lista słowników {event: Event, retry_count: int}

    __lock_for_general_purpose = threading.Lock()
    __lock_for_incoming_events = threading.Lock()
    __lock_for_processing_events = threading.Lock()
    __lock_for_events_to_send = threading.Lock()

    __send_queue_frequency: int = 50
    __analyze_queue_frequency: int = 100
    __check_local_data_frequency: int = 100
    __discovery_frequency: int = 1
    __get_state_frequency: int = 1

    _state: dict[str, Any] = {}
    _configuration: dict[str, Any] = {}
    _shutdown_requested: bool = False

    _message_logger: MessageLogger = None
    server: uvicorn.Server = None
    config: uvicorn.Config = None
    app: FastAPI = None
    _system_ready = threading.Event()
    __session = None  # Will be initialized in start()

    def __init__(
        self,
        name: str,
        address: str = "127.0.0.1",
        port: int = 8000,
        message_logger: MessageLogger | None = None,
        do_not_load_state: bool = False,
        discovery_neighbours: bool = False,
        raport_overtime: bool = True,
        use_parallel_send: bool = True,
        use_cumulative_send: bool = True,
    ):
        """
        Initializes a new EventListener object.

        Args:
            name (str): Listener name
            port (int): Server port to listen on
            message_logger (MessageLogger, optional): Logger for message recording. Defaults to None
            do_not_load_state (bool, optional): Flag determining whether to load saved state. Defaults to False
            raport_overtime (bool, optional): Flag determining whether to report overtime events. Defaults to True
        """
        info(
            f"Initializing event listener '{name}' on {address}:{port}",
            message_logger=message_logger,
        )
        # Upewnij się, że katalog temp istnieje
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        self.__queue_file_path = TEMP_DIR / f"{name}_state.json"
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
        self.__use_parallel_send = use_parallel_send
        self.__use_cumulative_send = use_cumulative_send
        self._message_logger = message_logger
        self._system_ready = threading.Event()
        self.__discovery_neighbours = discovery_neighbours

        # Wczytanie konfiguracji
        self.__load_configuration()

        # Wczytanie zapisanych kolejek
        if not do_not_load_state:
            self.__load_queues()

        # Dodanie obsługi sygnałów
        signal.signal(signal.SIGINT, self.__signal_handler)
        signal.signal(signal.SIGTERM, self.__signal_handler)

        debug(
            f"Using parallel send: {self.__use_parallel_send}",
            message_logger=self._message_logger,
        )

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

        @self.app.post("/state")
        async def state(event: Event):
            await self.__state_handler(event)
            return {"status": "ok"}

        @self.app.post("/discovery")
        async def discovery(event: Event):
            await self.__discovery_handler(event)
            return {"status": "ok"}

        # Startujemy thready - będą czekać na sygnał
        self.__start_analysis()
        self.__start_send_event()
        self.__start_local_check()

        if self.__discovery_neighbours:
            self.__start_discovering()

        self.__el_state = EventListenerState.INITIALIZED
        info(f"Event listener '{name}' initialized", message_logger=message_logger)

    @property
    def received_events(self):
        return self.__received_events

    @property
    def check_local_data_frequency(self):
        return self.__check_local_data_frequency

    @check_local_data_frequency.setter
    def check_local_data_frequency(self, value: int):
        self.__check_local_data_frequency = value

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
        self.__shutdown()  # Dodajemy bezpośrednie wywołanie shutdown
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
            Handles serialization of Pydantic objects, dictionaries, and lists, datetime objects, and Enum values
        """

        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, Enum):
            return value.value
        return value

    def __save_queues(self):
        """
        Saves queue state to file.

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
                for event_type_dict in self._processing_events_dict.values():
                    for id_dict in event_type_dict.values():
                        for event in id_dict.values():
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
                with open(self.__queue_file_path, "w", encoding="utf-8") as f:
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

    def __load_queues(self):
        """
        Loads queue state from file.

        Reads saved queue state from JSON file and reconstructs all event queues
        and listener state. File is deleted after successful loading.
        """
        if not os.path.exists(self.__queue_file_path):
            return

        try:
            with open(self.__queue_file_path, "r") as f:
                queues_data = json.load(f)

            # Konwersja danych na obiekty Event
            for event_data in queues_data.get("incoming_events", []):
                event = Event(**event_data)
                self.__incoming_events.append(event)

            # Rekonstrukcja processing_events_dict
            for event_data in queues_data.get("processing_events", []):
                event = Event(**event_data)
                event_type = event.event_type
                event_id = event.id
                event_timestamp = event.timestamp.isoformat()

                if event_type not in self._processing_events_dict:
                    self._processing_events_dict[event_type] = {}
                if event_id not in self._processing_events_dict[event_type]:
                    self._processing_events_dict[event_type][event_id] = {}

                self._processing_events_dict[event_type][event_id][event_timestamp] = (
                    event
                )

            # Rekonstrukcja events_to_send
            for event_data in queues_data.get("events_to_send", []):
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

            # Wczytywanie stanu
            state_data = queues_data.get("state", {})
            if hasattr(self, "_deserialize_state"):
                self._deserialize_state(state_data)
            else:
                self._state = state_data

            info(
                "Kolejki zostały wczytane z pliku", message_logger=self._message_logger
            )
            # Usuwanie pliku po wczytaniu
            os.remove(self.__queue_file_path)
            info(
                "Plik z kolejkami został usunięty", message_logger=self._message_logger
            )

        except Exception as e:
            error(
                f"Błąd podczas wczytywania kolejek: {e}",
                message_logger=self._message_logger,
            )

    def _event_find_and_remove_debug(self, event: Event):
        processing_time = time.time() - event.timestamp.timestamp()
        if processing_time < event.maximum_processing_time:
            info(
                f"Event find and remove from processing: source={event.source} destination={event.destination} event_type={event.event_type} data={event.data} result={event.result.result if event.result else None} timestamp={event.timestamp} processing_time={processing_time:.2f}s.",
                message_logger=self._message_logger,
            )
        else:
            error(
                f"OVERTIME: Event find and remove from processing: source={event.source} destination={event.destination} event_type={event.event_type} data={event.data} result={event.result.result if event.result else None} timestamp={event.timestamp} processing_time={processing_time:.2f}s.",
                message_logger=self._message_logger,
            )

    def _event_add_to_processing_debug(self, event: Event):
        debug(
            f"Event add to processing: id={event.id} event_type={event.event_type} data={event.data} result={event.result.result if event.result else None} timestamp={event.timestamp} MPT={event.maximum_processing_time}",
            message_logger=self._message_logger,
        )

    @contextmanager
    def _event_send_debug(self, event: Event):
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = (time.perf_counter() - start) * 1000
            if event.event_type == "cumulative":
                message = f"Event sent to {event.destination} [{event.destination_address}:{event.destination_port}] (cumulative) payload={event.payload} in {elapsed:.2f} ms:\n"
                for e in event.data["events"]:
                    message += f"- event_type='{e['event_type']}' data={e['data']} result={e['result']['result'] if e['result'] else None} timestamp={e['timestamp']} MPT={e['maximum_processing_time']}\n"
            else:
                message = f"Event sent to {event.destination} [{event.destination_address}:{event.destination_port}]: event_type='{event.event_type}' result={event.result.result if event.result else None} timestamp={event.timestamp} MPT={event.maximum_processing_time} in {elapsed:.2f} ms"
            debug(
                message,
                message_logger=self._message_logger,
            )

    def _event_receive_debug(self, event: Event):
        if event.event_type == "cumulative":
            message = f"Event received from {event.source} [{event.source_address}:{event.source_port}] (cumulative) payload={event.payload}:\n"
            for e in event.data["events"]:
                message += f"- event_type='{e['event_type']}' data={e['data']} result={e['result']['result'] if e['result'] else None} timestamp={e['timestamp']} MPT={e['maximum_processing_time']}\n"
        else:
            message = f"Event received from {event.source} [{event.source_address}:{event.source_port}]: event_type={event.event_type} result={event.result.result if event.result else None} timestamp={event.timestamp} MPT={event.maximum_processing_time}"
        debug(
            message,
            message_logger=self._message_logger,
        )

    def __save_configuration(self):
        """
        Saves configuration to file.

        Serializes and saves the current listener configuration to a JSON file.
        Operation is skipped if configuration is empty.
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
                    "Starting configuration serialization",
                    message_logger=self._message_logger,
                )
                serialized_config = self._serialize_value(self._configuration)
                debug(
                    "Configuration serialization completed",
                    message_logger=self._message_logger,
                )

                debug("Writing configuration to file")
                with open(self.__config_file_path, "w", encoding="utf-8") as f:
                    json.dump(
                        serialized_config,
                        f,
                        indent=4,
                        sort_keys=True,
                        ensure_ascii=False,
                    )
                info(
                    "Konfiguracja zostala zapisana do pliku",
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
        Loads configuration from file.

        Reads saved configuration from JSON file and assigns it to the listener.
        If the class has a _deserialize_configuration method, uses it for deserialization.
        """
        if not os.path.exists(self.__config_file_path):
            return

        try:
            with open(self.__config_file_path, "r") as f:
                config_data = json.load(f)

            if hasattr(self, "_deserialize_configuration"):
                self._deserialize_configuration(config_data)
            else:
                self._configuration = config_data

            info(
                f"Konfiguracja zostala wczytana z pliku: {self.__config_file_path}",
                message_logger=self._message_logger,
            )
        except Exception as e:
            error(
                f"Błąd podczas wczytywania konfiguracji: {e}",
                message_logger=self._message_logger,
            )

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

            # Stop all threads in proper order
            self.__stop_local_check()
            self.__stop_analysis()
            self.__stop_send_event()

            # Save state after threads are stopped to avoid race conditions
            self.__save_queues()
            self.__save_configuration()

            # Allow subclasses to perform custom cleanup
            self._execute_before_shutdown()

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
            return True

        except Exception as e:
            error(f"Błąd podczas zamykania: {e}", message_logger=self._message_logger)
            return False

    def __del__(self):
        try:
            debug(f"__del__ event listenera", message_logger=self._message_logger)
            if not self._shutdown_requested:
                self.__shutdown()
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
                debug(
                    f"Analyzing incoming event: {event}",
                    message_logger=self._message_logger,
                )
                should_remove = await self._analyze_event(event)
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
        pass

    async def __discovery_handler(self, event: Event):
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
                    # Unpack cumulative event
                    for event_data in event.data["events"]:
                        unpacked_event = Event(**event_data)
                        self.__incoming_events.append(unpacked_event)
                    debug(
                        f"Unpacked cumulative event into {len(event.data['events'])} events",
                        message_logger=self._message_logger,
                    )
                else:
                    self.__incoming_events.append(event)
                    debug(
                        f"Added event to incomming events queue: {event}",
                        message_logger=self._message_logger,
                    )
            self.__received_events += 1
        except Exception as e:
            error(f"__event_handler: {e}", message_logger=self._message_logger)

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
            loop.loop_begin()

            if self.__el_state is EventListenerState.RUNNING:
                try:
                    await self._check_local_data()
                except Exception as e:
                    error(f"Error in check_local_data: {e}")
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

                    message = f"{self.__name} - Status kolejek: przychodzace = {self.size_of_incomming_events_queue()}, procesowane = {self.size_of_processing_events_queue()}, wysylane = {self.size_of_events_to_send_queue()} [in={self.__received_events_per_second}, out={self.__sended_events_per_second}] msgs/s"
                    if (
                        self.size_of_incomming_events_queue()
                        + self.size_of_processing_events_queue()
                        + self.size_of_events_to_send_queue()
                        > 100
                    ):
                        error(message, message_logger=self._message_logger)
                    else:
                        info(message, message_logger=self._message_logger)

            loop.loop_end()

        debug("Check_local_data loop ended", message_logger=self._message_logger)

    def __start_local_check(self):
        """
        Starts the local data check loop.

        Initializes the local check flag and starts a new thread for local data monitoring.
        """
        info("Starting local data check", message_logger=self._message_logger)
        self.local_check_thread = threading.Thread(
            target=lambda: asyncio.run(self.__check_local_data_loop()), daemon=True
        )
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
                    debug(
                        f"Sending events: {len(local_queue)}",
                        message_logger=self._message_logger,
                    )

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
                                    events_by_destination[dest_key].append({
                                        "event": individual_event,
                                        "retry_count": event_data["retry_count"],
                                    })
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

                    if self.__use_parallel_send:

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
                                url = f"http://{event.destination_address}:{event.destination_port}/event"
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
                                                    time.perf_counter()
                                                    - event_start_time
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

                    else:
                        # Sequential sending
                        failed_events = []
                        for event_data in local_queue:
                            event = event_data["event"]
                            retry_count = event_data["retry_count"]

                            if retry_count >= self.__retry_count:
                                error(
                                    f"Event {event.event_type} failed after {self.__retry_count} retries - dropping",
                                    message_logger=self._message_logger,
                                )
                                continue

                            try:
                                url = f"http://{event.destination_address}:{event.destination_port}/event"
                                event_start_time = time.perf_counter()

                                try:
                                    with self._event_send_debug(event):
                                        async with session.post(
                                            url,
                                            json=event.to_dict(),
                                            timeout=aiohttp.ClientTimeout(total=0.1),
                                        ) as response:
                                            if response.status == 200:
                                                self.__sended_events += 1
                                                elapsed = (
                                                    time.perf_counter()
                                                    - event_start_time
                                                ) * 1000
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

    async def _analyze_event(self, event: Event) -> bool:
        return True  # domyślnie usuwamy event po przetworzeniu

    async def _check_local_data(self):
        pass

    async def _event(
        self,
        destination: str,
        destination_address: str = "0.0.0.0",
        destination_port: int = 8000,
        event_type: str = "default",
        id: int = None,
        data: dict = {},
        to_be_processed: bool = True,
        maximum_processing_time: float = 20,
    ) -> Event:
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
        Creates and adds event response to sending queue.

        Args:
            event (Event): Original event being responded to
            result (Result): Event processing result to be added to response

        Note:
            Creates new event with swapped source and destination addresses,
            maintaining other parameters from original event.
            Result is added to data.result field in new event.

        Raises:
            ValueError: When result is None
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

        try:
            with self.__atomic_operation_for_events_to_send():
                self.__events_to_send.append({"event": new_event, "retry_count": 0})
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
                self.__el_state = EventListenerState.RUNNING

            self.server.run()

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
                event_type = event.event_type
                event_id = event.id
                event_timestamp = event.timestamp.isoformat()

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

    def _find_and_remove_processing_event(
        self, event_type: str, id: int = None, timestamp: datetime = None
    ) -> Event | None:
        try:
            # Obsługa zarówno datetime jak i string timestamp
            timestamp_key = timestamp.isoformat()

            debug(
                f"Searching for event for remove in processing queue: id={id} event_type={event_type} timestamp={timestamp}",
                message_logger=self._message_logger,
            )

            with self.__atomic_operation_for_processing_events():
                event = self._processing_events_dict[timestamp_key]
                del self._processing_events_dict[timestamp_key]
                self._event_find_and_remove_debug(event)
                return event

            error(
                f"Event not found: id={id} event_type={event_type} timestamp={timestamp}",
                message_logger=self._message_logger,
            )
            return None
        except TimeoutError as e:
            error(
                f"_find_and_remove_processing_event: {e}",
                message_logger=self._message_logger,
            )
            return None
        except Exception as e:
            error(
                f"_find_and_remove_processing_event: {e}",
                message_logger=self._message_logger,
            )
            return None
