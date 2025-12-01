"""Synchronizator pętli sterujących z precyzyjnym taktem."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict


@dataclass
class LoopState:
    """Stan pojedynczej pętli w synchronizatorze."""

    period_ns: int
    next_deadline_ns: int
    backlog: int = 0


class LoopSynchronizer:
    """Koordynuje terminy rozpoczęcia pętli sterujących.

    Wszystkie pętle odniesione są do wspólnej epoki `base_time_ns`. Dzięki temu,
    niezależnie od okresu, każda iteracja trafia w kolejne harmoniczne tej samej
    osi czasu. Przy przekroczeniu slotu można wybrać strategię:
    - „skip” (pominięcie zaległych taktów, powrót do synchronizacji),
    - „catch-up” (kolejne iteracje bez czekania, aż dogonią takt).
    """

    def __init__(self, base_time_ns: int | None = None) -> None:
        """Inicjalizuje synchronizator.

        Args:
            base_time_ns: Opcjonalna wspólna epoka (np. współdzielona między
                procesami). Gdy `None`, pobierana jest aktualna wartość
                `time.perf_counter_ns()`.
        """
        self.base_time_ns = base_time_ns or time.perf_counter_ns()
        self._state: Dict[str, LoopState] = {}
        self._guard = threading.Lock()

    def register(self, name: str, period_s: float, phase: float = 0.0) -> None:
        """Rejestruje pętlę.

        Args:
            name: Nazwa pętli (musi być unikalna).
            period_s: Okres w sekundach.
            phase: Ułamek okresu przesunięcia początkowego [0.0, 1.0).

        Raises:
            ValueError: Gdy okres jest niepoprawny lub nazwa została powtórzona.
        """
        if period_s <= 0:
            raise ValueError("period_s musi byc dodatni")
        period_ns = max(int(period_s * 1e9), 1)
        phase_ns = int(phase % 1.0 * period_ns)

        with self._guard:
            if name in self._state:
                raise ValueError(f"petla '{name}' zostala juz zarejestrowana")
            now_ns = time.perf_counter_ns()
            first_deadline = (
                self._next_deadline(period_ns, phase_ns, now_ns) + period_ns
            )
            self._state[name] = LoopState(
                period_ns=period_ns,
                next_deadline_ns=first_deadline,
                backlog=0,
            )

    def reserve_slot(self, name: str) -> int:
        """Rezerwuje najbliższy slot czasowy dla wskazanej pętli."""
        with self._guard:
            state = self._state[name]
            if state.backlog > 0:
                deadline = state.next_deadline_ns - state.period_ns * state.backlog
                state.backlog -= 1
            else:
                deadline = state.next_deadline_ns
                state.next_deadline_ns += state.period_ns
            return deadline

    def recover_after_overrun(self, name: str, now_ns: int) -> int:
        """Aktualizuje slot po przekroczeniu terminu – strategia „skip”.

        Args:
            name: Nazwa pętli.
            now_ns: Aktualny czas (np. po zakończeniu iteracji).

        Returns:
            Liczba pominiętych slotów potrzebnych, by wrócić do taktu.
        """
        with self._guard:
            state = self._state[name]
            state.backlog = 0
            skipped = 0
            while state.next_deadline_ns <= now_ns:
                state.next_deadline_ns += state.period_ns
                skipped += 1
            return skipped

    def catch_up_after_overrun(self, name: str, now_ns: int) -> int:
        """Obsługuje przekroczenie slotu strategią „catch-up”.

        Args:
            name: Nazwa pętli.
            now_ns: Aktualny czas (np. po zakończeniu iteracji).

        Returns:
            Liczba zaległych slotów, które zostaną wykonane bez czekania.
        """
        with self._guard:
            state = self._state[name]
            lateness = now_ns - state.next_deadline_ns
            if lateness < 0:
                return 0
            missed = lateness // state.period_ns + 1
            state.backlog += missed
            state.next_deadline_ns += state.period_ns * missed
            return missed

    def _next_deadline(self, period_ns: int, phase_ns: int, now_ns: int) -> int:
        """Wyznacza pierwszy slot nie wcześniejszy niż `now_ns`."""
        base = self.base_time_ns + phase_ns
        offset = now_ns - base
        if offset <= 0:
            step = 0
        else:
            quotient, remainder = divmod(offset, period_ns)
            step = quotient if remainder == 0 else quotient + 1
        return base + step * period_ns
