import time


class Catchtime(object):  # context manager to catch time
    def __enter__(self):
        self.t = time.perf_counter()
        return self

    def __exit__(self, type, value, traceback):
        self.t = time.perf_counter() - self.t

    def __str__(self) -> str:
        return f"Execution time: {self.t * 1_000:.6f} ms"
