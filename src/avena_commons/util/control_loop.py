"""Prosta pętla sterująca z integracją synchronizatora."""

from __future__ import annotations

import gc
import json
import os
import time
from pathlib import Path
from typing import Callable, Optional

from avena_commons.util.logger import Logger, warning
from avena_commons.util.loop_sync import LoopSynchronizer


class ControlLoop:
    """Realizuje pojedynczą pętlę sterującą.

    Pętla może działać w trybie autonomicznym (auto sync z epoką globalną) lub
    korzystać z `LoopSynchronizer`, aby wszystkie cykle były zgodne z jednym
    taktem niezależnie od okresu.

    CONTROL_LOOP_EPOCH_FILE - zmienna środowiskowa określająca ścieżkę pliku epoki.
    """

    OVERRUN_SKIP = "skip"
    OVERRUN_CATCH_UP = "catch_up"
    _ALLOWED_OVERRUN_STRATEGIES = {OVERRUN_SKIP, OVERRUN_CATCH_UP}

    def __init__(
        self,
        name: str,
        period: float,
        *,
        warning_printer: bool = True,
        message_logger=None,
        overtime_info_callback: Optional[Callable[[], str]] = None,
        synchronizer: Optional[LoopSynchronizer] = None,
        auto_synchronizer: bool = False,
        overrun_strategy: str = OVERRUN_SKIP,
        busy_wait_ns: int = 100_000,
    ) -> None:
        """Tworzy obiekt pętli sterującej.

        Args:
            name: Nazwa pętli (wykorzystywana w logach).
            period: Okres wyrażony w sekundach.
            warning_printer: Czy logować przekroczenia czasu.
            message_logger: Opcjonalny logger użytkownika.
            overtime_info_callback: Funkcja dostarczająca dodatkowy tekst
                do logu przy przekroczeniu.
            synchronizer: Wspólny synchronizator czasu. Gdy brak i `auto_synchronizer`
                jest prawdą, pętla korzysta z globalnej epoki.
            auto_synchronizer: Czy utworzyć domyślny synchronizator bazujący na
                epokowym pliku, gdy `synchronizer` nie został przekazany.
            overrun_strategy: Strategie obsługi przekroczeń: `"skip"` (domyślnie)
                pomija zaległe takty i czeka do kolejnego startu pętli, `"catch_up"` wykonuje zaległe iteracje
                bez czekania.
            busy_wait_ns: Długość końcowego aktywnego oczekiwania (ns).

        Raises:
            ValueError: Gdy okres jest niepoprawny lub strategia jest nieznana.
        """
        if period is None or period <= 0:
            raise ValueError("period musi byc dodatni")
        if overrun_strategy not in self._ALLOWED_OVERRUN_STRATEGIES:
            raise ValueError(
                f"overrun_strategy musi być jednym z {self._ALLOWED_OVERRUN_STRATEGIES}"
            )

        self.name = name
        self.period = period
        self.period_ns = int(period * 1e9)
        self.overrun_strategy = overrun_strategy

        if synchronizer is not None:
            self.synchronizer = synchronizer
        elif auto_synchronizer:
            self.synchronizer = self._load_default_synchronizer()
        else:
            self.synchronizer = None
        self.busy_wait_ns = max(busy_wait_ns, 0)

        self.loop_counter = 0
        self.overtime_counter = 0
        self._current_start_ns = 0
        self.last_start_ns = 0
        self._total_exec_ns = 0
        self._min_exec_ns: Optional[int] = None
        self._max_exec_ns: Optional[int] = None

        self.warning_printer = warning_printer
        self.message_logger = message_logger
        self.overtime_info_callback = overtime_info_callback
        self._loggers: list[Logger] = []

        if self.synchronizer is not None:
            self.synchronizer.register(name, period)

    def loop_begin(self) -> None:
        """Rozpoczyna nową iterację pętli.

        Gdy dostępny jest synchronizator, metoda blokuje się do czasu osiągnięcia
        kolejnego slotu (lub startuje natychmiast przy strategii „catch-up”).
        """
        self.loop_counter += 1

        if self.synchronizer is not None:
            deadline_ns = self.synchronizer.reserve_slot(self.name)
            self._wait_until(deadline_ns)
            self._current_start_ns = deadline_ns
        else:
            self._current_start_ns = time.perf_counter_ns()
        self.last_start_ns = self._current_start_ns

    def loop_end(self) -> None:
        """Kończy iterację i utrzymuje takt na kolejne cykle."""
        finish_ns = time.perf_counter_ns()
        exec_ns = finish_ns - self._current_start_ns

        self._total_exec_ns += exec_ns
        self._min_exec_ns = (
            exec_ns if self._min_exec_ns is None else min(self._min_exec_ns, exec_ns)
        )
        self._max_exec_ns = (
            exec_ns if self._max_exec_ns is None else max(self._max_exec_ns, exec_ns)
        )

        for logger in self._loggers:
            logger.end_row()

        overtime_ns = exec_ns - self.period_ns
        skipped = 0

        if self.synchronizer is not None:
            if self.overrun_strategy == self.OVERRUN_CATCH_UP:
                skipped = self.synchronizer.catch_up_after_overrun(self.name, finish_ns)
            else:
                skipped = self.synchronizer.recover_after_overrun(self.name, finish_ns)
        else:
            expected_end_ns = self._current_start_ns + self.period_ns
            self._wait_until(expected_end_ns)

        if self.warning_printer and overtime_ns > 0:
            self.overtime_counter += 1
            suffix = ""
            if skipped:
                suffix += f" | skipped={skipped}"
            cb = self.overtime_info_callback
            if cb is not None:
                try:
                    extra = cb()
                    if extra:
                        suffix += f" | {extra}"
                except Exception as err:  # pragma: no cover - diagnostyka
                    suffix += f" | overtime_info_callback error: {err!r}"
            gc_state = "GC ENABLED" if gc.isenabled() else "GC DISABLED"
            warning(
                (
                    f"OVERTIME ERROR: {self.name.upper()} "
                    f"exec={exec_ns / 1e6:.3f}ms exceed={overtime_ns / 1e6:.3f}ms "
                    f"{gc_state}{suffix}"
                ),
                message_logger=self.message_logger,
            )

    def logger(self, filename: str, clear_file: bool = True) -> Logger:
        """Tworzy loggera powiązanego z pętlą."""
        logger = Logger(filename, clear_file)
        self._loggers.append(logger)
        return logger

    def avg_exec_ns(self) -> Optional[float]:
        """Zwraca średni czas wykonania pojedynczej iteracji."""
        if self.loop_counter == 0:
            return None
        return self._total_exec_ns / self.loop_counter

    def __str__(self) -> str:
        """Czytelne streszczenie statystyk pętli."""
        average = self.avg_exec_ns()
        if average is None:
            return (
                f"{self.name.upper()}, loops: {self.loop_counter}, "
                f"overtime: {self.overtime_counter}, not yet measured"
            )
        return (
            f"{self.name.upper()}, loops: {self.loop_counter}, overtime: {self.overtime_counter}, "
            f"min exec: {self._min_exec_ns / 1e6:.3f}ms, "
            f"max exec: {self._max_exec_ns / 1e6:.3f}ms, "
            f"avg exec: {average / 1e6:.3f}ms"
        )

    def _wait_until(self, target_ns: int) -> None:
        """Czeka do wskazanego momentu."""
        while True:
            now_ns = time.perf_counter_ns()
            remaining = target_ns - now_ns
            if remaining <= self.busy_wait_ns:
                break
            sleep_ns = remaining - self.busy_wait_ns
            time.sleep(sleep_ns * 1e-9)

        while time.perf_counter_ns() < target_ns:
            pass

    # --- Obsługa wspólnej epoki -------------------------------------------------

    _EPOCH_ENV = "CONTROL_LOOP_EPOCH_FILE"
    _DEFAULT_EPOCH_PATH = "temp/control_loop_epoch.json"

    @classmethod
    def _load_default_synchronizer(cls) -> LoopSynchronizer:
        """Ładuje lub tworzy synchronizator oparty na wspólnej epoce."""
        epoch_ns = cls._load_or_create_shared_epoch()
        return LoopSynchronizer(base_time_ns=epoch_ns)

    @classmethod
    def _resolve_epoch_path(cls) -> Path:
        """Zwraca ścieżkę pliku epoki (z obsługą zmiennej środowiskowej)."""
        override = os.getenv(cls._EPOCH_ENV)
        if override:
            return Path(override)
        return Path(cls._DEFAULT_EPOCH_PATH)

    @classmethod
    def _load_or_create_shared_epoch(cls) -> int:
        """Wyszukuje lub tworzy wspólną epokę w pliku."""
        path = cls._resolve_epoch_path()
        if not os.path.exists(path):
            path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            pass
        except PermissionError as exc:
            raise RuntimeError(
                f"Brak uprawnień do utworzenia pliku epoki: {path}"
            ) from exc
        else:
            epoch_ns = time.perf_counter_ns()
            payload = json.dumps({"epoch_ns": epoch_ns})
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            return epoch_ns

        for _ in range(10):
            try:
                raw = path.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                time.sleep(0.001)
                continue
            if raw:
                epoch = cls._read_epoch(raw)
                if epoch is not None:
                    return epoch
                break
            time.sleep(0.001)

        epoch_ns = time.perf_counter_ns()
        payload = json.dumps({"epoch_ns": epoch_ns})
        try:
            path.write_text(payload, encoding="utf-8")
        except PermissionError as exc:
            raise RuntimeError(f"Brak uprawnień do zapisu pliku epoki: {path}") from exc
        return epoch_ns

    @staticmethod
    def _read_epoch(raw: str) -> Optional[int]:
        """Zwraca epoch_ns z pliku JSON."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        value = data.get("epoch_ns")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
