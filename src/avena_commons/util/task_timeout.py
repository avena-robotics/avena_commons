from abc import ABC
from threading import Event, Thread
from typing import Any, Callable, Dict, Optional

from avena_commons.io.virtual_device.sensor_watchdog import (
    SensorTimerTask,
    SensorWatchdog,
)
from avena_commons.util.control_loop import ControlLoop
from avena_commons.util.logger import error


class TaskTimeout(ABC):
    def __init__(self, message_logger=None, **kwargs):
        """Inicjalizuje TaskTimeout i uruchamia wątek pętli sterującej do tickowania watchdogów."""

        self.message_logger = message_logger
        self.__watchdog = SensorWatchdog(on_timeout_default=self.__on_sensor_timeout_wrapper, log_error=lambda msg: error(msg, message_logger=self.message_logger))

        self._stop_event = Event()
        self._thread = None
        self.cl = ControlLoop(
            name="TaskTimeoutLoop",
            period=0.1,  # 100ms tick
            message_logger=self.message_logger,
            auto_synchronizer=True,
            warning_printer=False,
        )
        
        def _tick_loop():
            while not self._stop_event.is_set():
                self.cl.loop_begin()
                self.__tick_watchdogs()
                self.cl.loop_end()
                
        self._thread = Thread(target=_tick_loop, daemon=True)
        self._thread.start()

    def __del__(self):
        """Zatrzymuje wątek tickowania watchdogów przy usuwaniu obiektu."""
        if hasattr(self, '_stop_event') and self._stop_event:
            self._stop_event.set()
        if hasattr(self, '_thread') and self._thread:
            self._thread.join(timeout=1)

    def on_sensor_timeout(self, task: SensorTimerTask) -> None:
        """
        Domyślna akcja w przypadku przekroczenia czasu zadania watchdoga.
        Potomne urządzenia mogą nadpisać tę metodę, aby rozbudować zachowanie
        (np. zatrzymanie napędów) przed przejściem w stan ERROR.
        """
        pass

    def __on_sensor_timeout_wrapper(self, task: SensorTimerTask) -> None:
        """Wrapper dla domyślnej akcji w przypadku przekroczenia czasu zadania watchdoga.
        Wywołuje on_sensor_timeout(nadpisywalne), zapisuje błąd.
        """
        self.on_sensor_timeout(task)
        error(f"{self.device_name} - Timeout: {task.description}, {task.metadata}", message_logger=self.message_logger)

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
        return self.__watchdog.until(
            condition=condition,
            timeout_s=timeout_s,
            description=description,
            id=id,
            on_timeout=on_timeout or self.__on_sensor_timeout_wrapper,
            metadata=metadata,
        )

    def cancel_sensor_timeout(self, id: str) -> bool:
        """Anuluje zadanie watchdoga o podanym identyfikatorze.

        Args:
            id (str): Identyfikator zadania zwrócony przez `add_sensor_timeout`.

        Returns:
            bool: True, jeśli anulowano; False, jeśli zadanie nie istniało.
        """
        return self.__watchdog.cancel(id)

    def __tick_watchdogs(self) -> None:
        """Wywołuje cykliczną obsługę wszystkich zadań watchdoga dla urządzenia."""
        self.__watchdog.tick()