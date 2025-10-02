"""Moduł Pepper EventListener do obsługi pepper vision processing.

Odpowiedzialność:
- Obsługa zdarzeń pepper vision (process_fragments)
- Zarządzanie PepperConnector i komunikacją z worker
- Przetwarzanie fragmentów obrazu z pepper vision
- Integracja z systemem event-driven

Eksponuje:
- Klasa `Pepper` (główny event listener pepper vision)
"""

import os
import threading
import traceback
import copy
from typing import Dict, List, Optional, Any
import base64
import numpy as np
import json
from datetime import datetime
from dotenv import load_dotenv

from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
    Result,
)
from avena_commons.pepper.driver.pepper_connector import PepperConnector, PepperState
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import MessageLogger, debug, error, info

load_dotenv(override=True)


class Pepper(EventListener):
    """
    Główna klasa logiki pepper vision do obsługi zdarzeń przetwarzania fragmentów.

    Odpowiada za przetwarzanie zdarzeń process_fragments,
    zarządzanie PepperConnector oraz komunikację z PepperWorker.

    Atrybuty:
        pepper_connector (PepperConnector): Connector do pepper worker.
        processing_enabled (bool): Status czy przetwarzanie jest włączone.
        last_processing_result: Ostatni wynik przetwarzania.
        current_core (int): Numer core na którym działa pepper worker.
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
        Inicjalizuje pepper vision z niezbędną konfiguracją.

        Args:
            name (str): Nazwa event listenera pepper.
            address (str): Adres IP event listenera pepper.
            port (str): Port event listenera pepper.
            core (int): Numer rdzenia CPU dla pepper worker (domyślnie 2).
            message_logger (MessageLogger | None): Logger do zapisywania wiadomości; domyślnie None.
            load_state (bool): Flaga ładowania stanu (obecnie nieużywana); domyślnie False.

        Raises:
            ValueError: Gdy brak wymaganej zmiennej środowiskowej portu.
        """

        if not port:
            raise ValueError("Brak wymaganej zmiennej środowiskowej PEPPER_LISTENER_PORT")

        self.name = name
        self.check_local_data_frequency = 30  # Check every 30ms

        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
        )
        
        
        # Pepper configuration
        self.__pepper_config = self._configuration.get("pepper_configuration", {})
        debug(f"Pepper config: {self.__pepper_config}", self._message_logger)
        self.current_core = self.__pepper_config.get("core", 2)
        debug(f"Pepper init on core {self.current_core}", self._message_logger)

        self._port = port
        self._address = address

        # Processing state management
        self.processing_enabled = True
        self.last_processing_result = None
        self._is_processing = False
        self.last_fragments = None
        
        self._fragments_lock = threading.Lock()  # Thread safety
        
        self.expected_fragments = self.__pepper_config.get("expected_fragments", 4)  # Expecting 4 fragments per frame
        self.current_frame_id = None

        # Performance metrics for pepper processing functions
        self.performance_metrics = {
            'deserialization_times': [],
            'processing_times': [],
            'total_processing_times': [],
            'fragments_processed': 0,
            'processing_sessions': 0,
            'start_time': datetime.now().isoformat(),
            'processing_errors': 0
        }

        debug(
            f"EVENT_LISTENER_INIT: Pepper event listener został zainicjalizowany na core {self.current_core}",
            self._message_logger,
        )
        
        # Initialize PepperConnector
        self.pepper_connector = PepperConnector(
            core=self.current_core,
            message_logger=self._message_logger
        )
        
        # Initialize pepper worker
        self._change_fsm_state(EventListenerState.INITIALIZING)

    async def on_initializing(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZING."""
        self.pepper_connector.init(self.__pepper_config)
        debug("Pepper initializing", self._message_logger)

    async def on_starting(self):
        """Metoda wywoływana podczas przejścia w stan STARTING."""
        self.pepper_connector.start()
        debug("Pepper starting", self._message_logger)

    async def on_stopping(self):
        """Metoda wywoływana podczas przejścia w stan STOPPING."""
        self.pepper_connector.stop()
        self._is_processing = False
        debug("Pepper stopping, reset processing flag", self._message_logger)
        
        # Log performance metrics at shutdown
        self._log_performance_metrics()

    def _log_performance_metrics(self):
        """Log comprehensive performance metrics for pepper processing functions."""
        try:
            end_time = datetime.now().isoformat()
            
            # Calculate statistics
            metrics_summary = {
                'timestamp': end_time,
                'session_info': {
                    'start_time': self.performance_metrics['start_time'],
                    'end_time': end_time,
                    'name': self.name,
                    'core': self.current_core,
                    'expected_fragments': self.expected_fragments
                },
                'processing_stats': {
                    'total_fragments_processed': self.performance_metrics['fragments_processed'],
                    'total_processing_sessions': self.performance_metrics['processing_sessions'],
                    'processing_errors': self.performance_metrics['processing_errors']
                },
                'timing_statistics': {}
            }
            
            # Process timing statistics
            for metric_name, times in self.performance_metrics.items():
                if isinstance(times, list) and times and metric_name.endswith('_times'):
                    stats = {
                        'count': len(times),
                        'avg_ms': sum(times) / len(times),
                        'min_ms': min(times),
                        'max_ms': max(times),
                        'total_ms': sum(times)
                    }
                    
                    # Calculate throughput for processing operations
                    if metric_name == 'processing_times' and stats['avg_ms'] > 0:
                        stats['avg_throughput_per_sec'] = 1000.0 / stats['avg_ms']
                    
                    metrics_summary['timing_statistics'][metric_name] = stats
            
            # Create performance log file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_filename = f"temp/performance_metrics_pepper_{timestamp}.json"
            
            os.makedirs("temp", exist_ok=True)
            with open(log_filename, 'w') as f:
                json.dump(metrics_summary, f, indent=2)
            
            info(f"Performance metrics saved to {log_filename}", self._message_logger)
            
            # Log summary to main log
            if self.performance_metrics['processing_sessions'] > 0:
                avg_total = sum(self.performance_metrics['total_processing_times']) / len(self.performance_metrics['total_processing_times']) if self.performance_metrics['total_processing_times'] else 0
                info(f"PERFORMANCE SUMMARY - Sessions: {self.performance_metrics['processing_sessions']}, Fragments: {self.performance_metrics['fragments_processed']}, Avg Total Time: {avg_total:.2f}ms", self._message_logger)
            
        except Exception as e:
            error(f"Error logging performance metrics: {e}", self._message_logger)

    def _clear_before_shutdown(self):
        """Czyści zasoby przed zamknięciem pepper."""
        __logger = self._message_logger
        self._message_logger = None
        

    def _deserialize_fragments(self, fragments_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, np.ndarray]]:
        """Odtwarza fragmenty z formatu JSON na numpy arrays.
        
        Args:
            fragments_data: Dane fragmentów z JSON
            
        Returns:
            Dict[str, Dict[str, np.ndarray]]: Fragmenty z numpy arrays
            
        Raises:
            Exception: Przy błędzie konwersji danych
        """
        with Catchtime() as deser_timer:
            try:
                fragments = {}
                
                for fragment_name, fragment_data in fragments_data.items():
                    fragment = {}
                    
                    for key, value in fragment_data.items():
                        if isinstance(value, dict) and 'data' in value and 'dtype' in value and 'shape' in value:
                            # Odtwórz numpy array z base64
                            array_bytes = base64.b64decode(value['data'].encode('utf-8'))
                            dtype = np.dtype(value['dtype'])
                            shape = tuple(value['shape'])
                            
                            array = np.frombuffer(array_bytes, dtype=dtype).reshape(shape)
                            fragment[key] = array
                        else:
                            # Zachowaj inne wartości
                            fragment[key] = value
                    
                    fragments[fragment_name] = fragment
                    
                    debug(f"Deserialized fragment {fragment_name} with keys: {list(fragment.keys())}", self._message_logger)
                
                # Record deserialization timing
                self.performance_metrics['deserialization_times'].append(deser_timer.ms)
                self.performance_metrics['fragments_processed'] += len(fragments)
                
                return fragments
                
            except Exception as e:
                error(f"Error deserializing fragments from JSON: {e}", self._message_logger)
                self.performance_metrics['processing_errors'] += 1
                return {}

    async def _analyze_event(self, event):
        """Analizuje przychodzące zdarzenia pepper vision.

        Args:
            event: Zdarzenie do przetworzenia (process_fragments)

        Returns:
            bool: True jeśli zdarzenie zostało poprawnie przetworzone
        """

        match event.event_type:
            case "process_fragments":
                # Sprawdź czy mamy fragments w event data
                if not hasattr(event, 'data') or not event.data or 'fragments' not in event.data:
                    event.result = Result(
                        result="failure",
                        error_message="No fragments provided in event data.",
                    )
                    await self._reply(event)
                    return True

                fragments = event.data['fragments']
                debug(f"Received {len(fragments)} fragments for buffering", self._message_logger)

                self.last_fragments = self._deserialize_fragments(fragments)
                
                debug(f"Event added to processing queue, fragments buffered", self._message_logger)

            case _:
                if event.result is not None:
                    return True
                debug(f"Nieznany event {event.event_type}", self._message_logger)
                return False

        return True

    async def _check_local_data(self):
        """
        Periodically checks fragment buffer and processes pepper vision when ready.
        Uses proper async pattern with fragment aggregation.

        Raises:
            Exception: If an error occurs during data processing.
        """
        pepper_state = self.pepper_connector.get_state()
        
        if pepper_state == PepperState.ERROR:
            self._change_fsm_state(EventListenerState.ON_ERROR)
            self._is_processing = False
            return

        # Check if we have enough fragments to process and we're not already processing
        if self.last_fragments is not None and not self._is_processing:
            # Take fragments for processing
            with self._fragments_lock:
                processing_fragment = copy.deepcopy(self.last_fragments)

            debug(f"Starting pepper processing for fragment", self._message_logger)
            
            # Start processing with performance tracking
            self._is_processing = True
            
            # Process fragments with pepper vision
            with Catchtime() as processing_timer:
                result = self.pepper_connector.process_fragments(processing_fragment)
            
            # Record processing metrics
            self.performance_metrics['processing_times'].append(processing_timer.ms)
            self.performance_metrics['total_processing_times'].append(processing_timer.ms)
            self.performance_metrics['processing_sessions'] += 1
            
            self.last_fragments = None
            
            if result and result.get('success', False):
                debug(
                    f"Pepper processing completed in {processing_timer.ms:.2f}ms",
                    self._message_logger,
                )
                
                # Reset processing flag
                self._is_processing = False

                info(
                    f"Pepper vision completed - results logged for fragment: {result}",
                    self._message_logger,
                )
            else:
                # Reset processing flag even on failure
                self._is_processing = False
                self.performance_metrics['processing_errors'] += 1
                error(f"Pepper processing failed or returned no success", self._message_logger)
                    
    def get_processing_status(self):
        """Pobierz status przetwarzania pepper vision.
        
        Returns:
            dict: Status przetwarzania
        """
        return {
            "is_processing": self._is_processing,
            "processing_enabled": self.processing_enabled,
            "pepper_state": self.pepper_connector.get_state(),
            "core": self.current_core,
            "last_result": self.last_processing_result
        }

    def enable_processing(self):
        """Włącz przetwarzanie pepper vision."""
        self.processing_enabled = True
        debug("Pepper processing enabled", self._message_logger)

    def disable_processing(self):
        """Wyłącz przetwarzanie pepper vision."""
        self.processing_enabled = False
        debug("Pepper processing disabled", self._message_logger)
