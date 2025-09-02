import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, Optional


@dataclass
class SensorTimerTask:
    """Reprezentuje pojedyncze zadanie watchdoga nadzorujące warunek w czasie.

    Atrybuty:
        id (str): Unikalny identyfikator zadania.
        description (str): Opis zadania/warunku.
        deadline (float): Znacznik czasu (epoch seconds), do którego warunek powinien zostać spełniony.
        resolve (Callable[[], bool]): Funkcja sprawdzająca spełnienie warunku (True oznacza sukces).
        on_timeout (Callable[[SensorTimerTask], None]): Akcja wykonywana po przekroczeniu czasu.
        metadata (dict[str, Any]): Dodatkowe metadane, np. kontekst diagnostyczny.
        created_at (float): Czas utworzenia zadania.
    """

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
        """Inicjalizuje instancję watchdoga.

        Args:
            now (Callable[[], float]): Źródło czasu (domyślnie time.time).
            on_timeout_default (Callable[[SensorTimerTask], None] | None): Domyślna akcja wykonywana przy timeout,
                gdy zadanie nie poda własnej akcji.
            log_error (Callable[[str], None] | None): Funkcja do logowania błędów/timeoutów.
        """
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
        """Rejestruje nowe zadanie watchdoga.

        Args:
            id (str): Identyfikator zadania (musi być unikalny).
            resolve (Callable[[], bool]): Funkcja sprawdzająca spełnienie warunku (True kończy zadanie).
            timeout_s (float): Limit czasu w sekundach.
            description (str): Opis zadania/warunku (opcjonalnie).
            on_timeout (Callable[[SensorTimerTask], None] | None): Niestandardowa akcja wykonywana przy timeout.
            metadata (dict[str, Any] | None): Dodatkowe metadane zadania.

        Returns:
            str: Identyfikator zarejestrowanego zadania (taki sam jak przekazany `id`).
        """
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
        """Wygodny wrapper nad `add_task` generujący identyfikator zadania.

        Args:
            condition (Callable[[], bool]): Warunek, który powinien się spełnić przed upływem czasu.
            timeout_s (float): Limit czasu w sekundach.
            description (str): Opis zadania/warunku.
            id (str | None): Opcjonalny identyfikator; gdy None, zostanie wygenerowany.
            on_timeout (Callable[[SensorTimerTask], None] | None): Niestandardowa akcja wykonywana po timeout.
            metadata (dict[str, Any] | None): Metadane użytkownika.

        Returns:
            str: Id wygenerowanego (lub przekazanego) zadania.
        """
        return self.add_task(
            id=id or f"task_{int(self._now() * 1000)}",
            resolve=condition,
            timeout_s=timeout_s,
            description=description,
            on_timeout=on_timeout,
            metadata=metadata,
        )

    def cancel(self, id: str) -> bool:
        """Anuluje zadanie o podanym identyfikatorze.

        Args:
            id (str): Identyfikator zadania do usunięcia.

        Returns:
            bool: True, jeśli zadanie usunięto; False, jeśli nie znaleziono.
        """
        for idx, t in enumerate(self._tasks):
            if t.id == id:
                del self._tasks[idx]
                return True
        return False

    def tick(self) -> None:
        """Cyklicznie przetwarza kolejkę zadań watchdoga.

        Dla każdego zadania:
            - jeśli warunek `resolve()` zwróci True, zadanie zostaje usunięte;
            - jeśli przekroczono `deadline`, wywoływany jest `on_timeout` i zadanie nie wraca do kolejki;
            - w przeciwnym wypadku zadanie trafia ponownie na koniec kolejki.
        """
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
        """Domyślna akcja wykonywana przy przekroczeniu czasu zadania.

        Jeśli przekazano `on_timeout_default` w konstruktorze — wywołuje ją.
        W przeciwnym razie próbuje zalogować błąd przez `log_error`.
        """
        if self._on_timeout_default is not None:
            self._on_timeout_default(task)
        elif self._log_error is not None:
            try:
                self._log_error(
                    f"SensorWatchdog timeout: {task.description} {task.metadata}"
                )
            except Exception:
                pass
