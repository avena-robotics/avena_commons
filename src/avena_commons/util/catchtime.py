import time


class Catchtime(object):  # context manager to catch time
    def __enter__(self):
        self.start_time = time.perf_counter()
        self.__t = 0  # Inicjalizuj atrybut t
        return self

    def __exit__(self, type, value, traceback):
        self.__t = time.perf_counter() - self.start_time

    def __str__(self) -> str:
        return f"Execution time: {self.ms:.6f} ms"

    @property
    def t(self) -> float:
        return self.__t

    @property
    def us(self) -> float:
        return self.t * 1_000_000

    @property
    def ms(self) -> float:
        return self.t * 1_000

    @property
    def sec(self) -> float:
        return self.t
