from abc import abstractmethod
from threading import Lock

from avena_commons.event_listener import Event, Result
from avena_commons.util.logger import debug, error
from avena_commons.util.measure_time import MeasureTime


class VirtualDevice:
    def __init__(self, **kwargs):
        self.device_name = kwargs["device_name"]
        self.devices = kwargs["devices"]
        self.methods = kwargs["methods"]
        self._processing_events = {}
        self._finished_events = []
        self._processing_events_lock = Lock()
        self._finished_events_lock = Lock()
        self._message_logger = kwargs["message_logger"]

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

    def execute_event(self, event: Event) -> Event | None:  # wywolanie akcji dlugiej
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
                        return self._instant_execute_event(event)

    def finished_events(self) -> list[Event]:  # odbior zakonczonych zdarzen
        with self._finished_events_lock:
            temp_list = self._finished_events.copy()
            self._finished_events.clear()
            return temp_list

    @abstractmethod
    def tick(self):
        pass
