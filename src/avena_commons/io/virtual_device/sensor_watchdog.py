import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional


@dataclass
class SensorTimerTask:
    id: str
    description: str
    deadline: float
    resolve: Callable[[], bool]
    on_timeout: Callable[["SensorTimerTask"], None]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class SensorWatchdog:
    """
    Uniwersalny watchdog do nadzoru warunków (np. stanów czujników) z timeoutami.

    - add_task/until: rejestracja zadania z warunkiem i maksymalnym czasem oczekiwania
    - tick: cykliczne sprawdzanie warunków; po spełnieniu usuwa zadanie; po przekroczeniu czasu wywołuje on_timeout
    - cancel: ręczne usuwanie zadania po id
    """

    def __init__(
        self,
        now: Callable[[], float] = time.time,
        on_timeout_default: Optional[Callable[[SensorTimerTask], None]] = None,
        log_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._tasks: Deque[SensorTimerTask] = deque()
        self._now = now
        self._on_timeout_default = on_timeout_default
        self._log_error = log_error

    def add_task(
        self,
        id: str,
        resolve: Callable[[], bool],
        timeout_s: float,
        description: str = "",
        on_timeout: Optional[Callable[[SensorTimerTask], None]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        task = SensorTimerTask(
            id=id,
            description=description or id,
            deadline=self._now() + timeout_s,
            resolve=resolve,
            on_timeout=on_timeout or self._default_timeout_action,
            metadata=metadata or {},
        )
        self._tasks.append(task)
        return id

    def until(
        self,
        condition: Callable[[], bool],
        timeout_s: float,
        description: str,
        id: Optional[str] = None,
        on_timeout: Optional[Callable[[SensorTimerTask], None]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.add_task(
            id=id or f"task_{int(self._now() * 1000)}",
            resolve=condition,
            timeout_s=timeout_s,
            description=description,
            on_timeout=on_timeout,
            metadata=metadata,
        )

    def cancel(self, id: str) -> bool:
        for idx, t in enumerate(self._tasks):
            if t.id == id:
                del self._tasks[idx]
                return True
        return False

    def tick(self) -> None:
        if not self._tasks:
            return
        n = len(self._tasks)
        now = self._now()
        for _ in range(n):
            task = self._tasks.popleft()
            try:
                if task.resolve():
                    continue
                if now >= task.deadline:
                    try:
                        task.on_timeout(task)
                    finally:
                        continue
                self._tasks.append(task)
            except Exception as e:
                if self._log_error is not None:
                    try:
                        self._log_error(f"SensorWatchdog task '{task.id}' failed: {e}")
                    except Exception:
                        pass

    def _default_timeout_action(self, task: SensorTimerTask) -> None:
        if self._on_timeout_default is not None:
            self._on_timeout_default(task)
        elif self._log_error is not None:
            try:
                self._log_error(
                    f"SensorWatchdog timeout: {task.description} {task.metadata}"
                )
            except Exception:
                pass
