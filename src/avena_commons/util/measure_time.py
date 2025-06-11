import time
from contextlib import ContextDecorator

from avena_commons.util.logger import MessageLogger, debug, error


class MeasureTime(ContextDecorator):
    """
    Wrapper do mierzenia czasu wykonania fragmentu kodu.
    Może być używany jako dekorator lub kontekst menedżer.
    """

    elapsed: float = 0.0

    def __init__(
        self,
        label="Czas wykonania",
        max_execution_time: float = 1.0,
        resolution: int = 3,
        print_info: bool = True,
        message_logger: MessageLogger | None = None,
    ):
        self.label = label
        self.__message_logger = message_logger
        self.__max_execution_time = max_execution_time
        self.__resolution = resolution
        self.__print_info = print_info

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.end = time.perf_counter()
        self.elapsed = (self.end - self.start) * 1000
        if self.__print_info:
            if self.elapsed > self.__max_execution_time:
                error(
                    f"MeasureTime: {self.label} = {self.elapsed:.{self.__resolution}f}ms",
                    message_logger=self.__message_logger,
                )
            else:
                debug(
                    f"MeasureTime: {self.label} = {self.elapsed:.{self.__resolution}f}ms",
                    message_logger=self.__message_logger,
                )
