import multiprocessing
import threading
import time

import psutil

from .logger import debug, error, warning


def run_info(func):
    def inner1(*args, **kwargs):
        debug(f"Started {func.__qualname__}()")

        func(*args, **kwargs)

        debug(f"Finished {func.__qualname__}()")

    return inner1


class Worker:
    """
    Class Worker is used to create a worker process.
    It will run in a separate process and will be able to communicate with the main process.
    """

    def __init__(self, message_logger=None):
        self._message_logger = message_logger

    @property
    def threads(self) -> int:
        return threading.active_count()

    # @run_info
    def _run(self, pipe_in):
        try:
            while True:
                pass
        except Exception as e:
            warning(f"Exception: {e}", message_logger=self._message_logger)


class Connector:
    """
    Connector class is used to create a worker process and connect it to the main process.
    This class sends and receives data to/from the worker process in an unblockable manner.
    """

    def __init__(self, core=8, message_logger=None) -> None:
        self._core = core
        self._pipe_out = None
        self._message_logger = message_logger
        # self._connect()

    @staticmethod
    def __getattr__(name) -> None:
        """
        This method is called whenever an attribute lookup has not found the attribute or method.
        """

        def not_callable(*args, **kwargs) -> None:
            warning(f"Attempted to call non-existent method: {name}")
            return None

        warning(f"Object has no attribute or method named: {name}")
        return not_callable

    @staticmethod
    def _read_only_property(name):
        def decorator(setter_function):
            def wrapper(*args, **kwargs):
                try:
                    raise ValueError(f"{name} is read-only")
                except Exception as e:
                    error(f"{e}")
                    # raise

            return wrapper

        return decorator

    # @run_info
    def _send_thru_pipe(self, pipe, cmd):
        if pipe != None:
            try:
                pipe.send(cmd)
                value = pipe.recv()
                return value
            except (BrokenPipeError, ConnectionResetError, EOFError):
                pass
            except Exception as e:
                error(f"{e}", message_logger=self._message_logger)
                raise
        return None

    # @run_info
    def _connect(self):
        self._pipe_out, _pipe_in = multiprocessing.Pipe()
        self._process = multiprocessing.Process(
            target=self._run, args=(_pipe_in, self._message_logger)
        )
        self._process.start()
        self.core = self._core

    # @run_info
    def _run(self, pipe_in, message_logger=None):
        worker = Worker(message_logger=message_logger)
        worker._run(pipe_in)

    @property
    def threads(self) -> int:
        return threading.activeCount()

    @property
    def core(self) -> int:
        return self._core

    @core.setter
    def core(self, core):
        self._core = core
        p = psutil.Process(self._process.pid)
        p.cpu_affinity([self._core])
        debug(
            f"{self.__class__.__name__} Set CPU to {core}",
            message_logger=self._message_logger,
        )

    def __del__(self):
        try:
            if self._pipe_out is not None:
                if self._process.is_alive():
                    debug(
                        "Zamykanie procesu worker", message_logger=self._message_logger
                    )
                    self._pipe_out.send(["STOP"])
                    self._process.terminate()
                    self._process.join()
                    self._pipe_out = None
                time.sleep(0.01)
        except BrokenPipeError:
            pass
        except Exception as e:
            error(
                f"Wystąpił wyjątek przy zamykaniu: {e}",
                message_logger=self._message_logger,
            )
            # print(e)
