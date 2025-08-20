import gc
import time
from typing import Callable, Optional

from .logger import Logger, warning


class ControlLoop:
    """
    ControlLoop class is used to control the loop of the program. It is used to measure the time taken to execute a block of code.

    :param name: The name of the control loop.
    :type name: str
    :param period: The period of the control loop.
    :type period: float
    :param fill_idle_time: A flag to decide if we dump data from logger in the idle time.
    :type fill_idle_time: bool
    :param warning_printer: A flag to print warnings from overtimes.
    :type warning_printer: bool
    :param message_logger: The message logger.
    :type message_logger: None
    :param overtime_info_callback: Opcjonalny callback zwracający dodatkowy tekst do logu
        przy overtime. Sygnatura: () -> str
    :type overtime_info_callback: Optional[Callable[[], str]]
    """

    def __init__(
        self,
        name: str,
        period: float = None,
        fill_idle_time: bool = False,
        warning_printer=True,
        message_logger=None,
        overtime_info_callback: Optional[Callable[[], str]] = None,
    ):
        """Constructor for ControlLoop class."""
        self.name = name
        self.period = period
        self.last_run = 0
        self.min_period = None
        self.max_period = None
        self.avg_period = None
        self.loop_counter = 0
        self.run_time = 0.0
        self.overtime_counter = 0
        self._loggers = []
        self.warning_printer = warning_printer
        self.message_logger = message_logger
        self.fill_idle_time = fill_idle_time
        self.overtime_info_callback = overtime_info_callback

    def loop_begin(self):
        """
        This function sets the start time of the loop.

        :return: None
        """
        # self.last_run = time.time()
        self.last_run = time.perf_counter()
        self.loop_counter += 1

    def loop_end(self):
        """
        This function sets the end time of the loop.
        It also calculates the time taken to execute the loop and prints a warning if the time exceeds the period.

        :return: None
        """
        period = time.perf_counter() - self.last_run  # czas wykonania kroku petli

        self.run_time += period
        self.avg_period = (
            self.run_time / self.loop_counter
        )  # sredni czas wykonania kroku petli
        self.min_period = (
            period if self.min_period == None else min(self.min_period, period)
        )  # minimalny czas wykonania kroku petli
        self.max_period = (
            period if self.max_period == None else max(self.max_period, period)
        )  # maksymalny czas wykonania kroku petli

        for logger in self._loggers:  # all loggers - new row
            logger.end_row()

        if self.warning_printer:
            if period > self.period:
                self.overtime_counter += 1

                suffix = ""
                cb = getattr(self, "overtime_info_callback", None)
                if cb is not None:
                    try:
                        extra = cb()
                        if extra is not None and str(extra):
                            suffix = f" | {str(extra)}"
                    except Exception as e:
                        suffix = f" | overtime_info_callback error: {e!r}"

                if gc.isenabled():
                    warning(
                        f"OVERTIME ERROR: {self.name.upper()} exec time: {period * 1000:.5}ms exceed: {(period - self.period) * 1000:.5}ms GC ENABLED{suffix}",
                        message_logger=self.message_logger,
                    )
                else:
                    warning(
                        f"OVERTIME ERROR: {self.name.upper()} exec time: {period * 1000:.5}ms exceed: {(period - self.period) * 1000:.5}ms GC DISABLED{suffix}",
                        message_logger=self.message_logger,
                    )
            elif self.fill_idle_time:
                end_time_before_sleep = time.perf_counter()
                left_time_ms = (
                    self.period - (end_time_before_sleep - self.last_run)
                ) * 1000
                minimal_idle_time_ms = 0.5
                # while left_time_ms > minimal_idle_time_ms:
                for logger in self._loggers:
                    for i in range(logger.get_count_rows()):
                        logger.dump_rows(rows=1)
                        left_time_ms = (
                            self.period - (time.perf_counter() - self.last_run)
                        ) * 1000
                        if left_time_ms < minimal_idle_time_ms:
                            break

        before_sleep = time.perf_counter()
        time.sleep(max(self.period - (before_sleep - self.last_run), 0))
        self.last_run = time.perf_counter()

    def logger(self, filename, clear_file=True):
        """
        This function creates a logger for the control loop.

        :param filename: The name of the file to log the data.
        :type filename: str
        :param clear_file: A flag to decide if we clear the file.
        :type clear_file: bool
        :return: The logger object.
        :rtype: Logger
        """
        logger = Logger(filename, clear_file)
        self._loggers.append(logger)
        return logger

    def __str__(self):
        return f"{self.name.upper()}, loops: {self.loop_counter}, overtime: {self.overtime_counter}, min: {self.min_period * 1000:.5}ms, max: {self.max_period * 1000:.5}ms, avg: {self.avg_period * 1000:.5}ms"
