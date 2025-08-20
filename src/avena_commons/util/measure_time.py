import time
from contextlib import ContextDecorator

from avena_commons.util.logger import MessageLogger, debug, error


class MeasureTime(ContextDecorator):
    """
    Wrapper do mierzenia czasu wykonania fragmentu kodu.
    Może być używany jako dekorator lub kontekst menedżer.
    """

    elapsed: float = 0.0
    count: int = 0
    missed: int = 0

    def __init__(self, label="Czas wykonania", max_execution_time: float = 1.0, resolution: int = 3, silent_mode: bool = False, show_only_errors:bool = False, message_logger: MessageLogger | None = None):
        self.label = label
        self.__message_logger = message_logger
        self.__max_execution_time = max_execution_time
        self.__resolution = resolution
        self.__silent_mode = silent_mode
        self.__show_only_errors = show_only_errors

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.end = time.perf_counter()
        self.elapsed = (self.end - self.start) * 1000
        if self.elapsed > self.__max_execution_time:
            if not self.__silent_mode:
                error(f"MeasureTime: {self.label} = {self.elapsed:.{self.__resolution}f}ms", message_logger=self.__message_logger)
            self.missed += 1
        else:
            if not self.__silent_mode and not self.__show_only_errors:
                debug(f"MeasureTime: {self.label} = {self.elapsed:.{self.__resolution}f}ms", message_logger=self.__message_logger)
        self.count += 1

    def get_missed(self):
        return self.missed

    def get_count(self):
        return self.count
