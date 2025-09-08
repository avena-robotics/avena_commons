"""
ScenarioExecutionManager - zarządzanie stanem wykonywania scenariuszy z kontrolą przepływu.

Odpowiedzialność:
- Zarządzanie stanem wykonywania scenariuszy (pause/resume/nesting)
- Tracking zagnieżdżonych scenariuszy i stosu wykonań
- Checkpoint system dla wznowienia scenariuszy
- Kompatybilność wsteczna z istniejącym systemem

Eksponuje:
- Klasa `ScenarioExecutionManager`
- Enum `ExecutionState`
- Dataclass `ExecutionContext`
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from avena_commons.util.logger import MessageLogger, debug, error, info, warning

from .actions.base_action import ActionContext


class ExecutionState(Enum):
    """
    Stany wykonywania scenariusza.
    
    Attributes:
        RUNNING: Scenariusz jest aktywnie wykonywany
        PAUSED: Scenariusz został zatrzymany i oczekuje na wznowienie
        WAITING_FOR_NESTED: Scenariusz oczekuje na zakończenie zagnieżdżonego
        COMPLETED: Scenariusz zakończony pomyślnie
        FAILED: Scenariusz zakończony błędem
        CANCELLED: Scenariusz został anulowany
    """
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    WAITING_FOR_NESTED = "WAITING_FOR_NESTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class ExecutionContext:
    """
    Kontekst wykonania scenariusza z kontrolą przepływu.
    
    Rozszerza ActionContext o funkcjonalności pause/resume/nesting.
    
    Attributes:
        execution_id (str): Unikalny identyfikator wykonania
        scenario_name (str): Nazwa wykonywanego scenariusza
        base_context (ActionContext): Podstawowy kontekst akcji
        state (ExecutionState): Aktualny stan wykonania
        current_action_index (int): Indeks aktualnie wykonywanej akcji
        parent_execution_id (str | None): ID rodzica dla zagnieżdżonych scenariuszy
        nested_executions (List[str]): Lista ID zagnieżdżonych scenariuszy
        pause_event (asyncio.Event): Event do kontroli pause/resume
        checkpoint_data (Dict[str, Any]): Dane checkpointu dla wznowienia
        started_at (datetime): Czas rozpoczęcia wykonania
        paused_at (datetime | None): Czas zatrzymania (jeśli zatrzymany)
        completed_at (datetime | None): Czas zakończenia
        error_message (str | None): Komunikat błędu (jeśli failed)
    """
    execution_id: str
    scenario_name: str
    base_context: ActionContext
    state: ExecutionState = ExecutionState.RUNNING
    current_action_index: int = 0
    parent_execution_id: Optional[str] = None
    nested_executions: List[str] = field(default_factory=list)
    pause_event: asyncio.Event = field(default_factory=asyncio.Event)
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    paused_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        """Inicjalizuje pause_event w stanie 'set' (nie zatrzymany)."""
        self.pause_event.set()


class ScenarioExecutionManager:
    """
    Zarządca wykonywania scenariuszy z kontrolą przepływu.
    
    Rozszerza istniejący system orchestratora o możliwości:
    - Zatrzymywania i wznawiania scenariuszy
    - Uruchamiania scenariuszy zagnieżdżonych
    - Checkpoint system
    - Tracking stosu wykonań
    
    Zachowuje pełną kompatybilność wsteczną z istniejącym systemem.
    """

    def __init__(self, orchestrator, message_logger: Optional[MessageLogger] = None):
        """
        Inicjalizuje ScenarioExecutionManager.

        Args:
            orchestrator: Referencja do instancji Orchestrator
            message_logger (MessageLogger | None): Logger komunikatów
        """
        self.orchestrator = orchestrator
        self.message_logger = message_logger

        # Referencje do istniejących struktur orchestratora (kompatybilność)
        self._running_scenarios = orchestrator._running_scenarios
        self._scenario_execution_count = orchestrator._scenario_execution_count

        # Nowe struktury dla zaawansowanej kontroli przepływu
        self._execution_contexts: Dict[str, ExecutionContext] = {}
        self._execution_stack: List[str] = []  # stos zagnieżdżonych scenariuszy
        self._completed_executions: Dict[str, ExecutionContext] = {}  # historia

    def generate_execution_id(self) -> str:
        """
        Generuje unikalny identyfikator wykonania.

        Returns:
            str: Unikalny ID wykonania w formacie timestamp_uuid
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"{timestamp}_{unique_id}"

    async def create_execution_context(
        self,
        scenario_name: str,
        base_context: ActionContext,
        parent_execution_id: Optional[str] = None
    ) -> ExecutionContext:
        """
        Tworzy nowy kontekst wykonania scenariusza.

        Args:
            scenario_name: Nazwa scenariusza
            base_context: Podstawowy kontekst akcji
            parent_execution_id: ID rodzica dla zagnieżdżonych scenariuszy

        Returns:
            ExecutionContext: Nowy kontekst wykonania
        """
        execution_id = self.generate_execution_id()
        
        context = ExecutionContext(
            execution_id=execution_id,
            scenario_name=scenario_name,
            base_context=base_context,
            parent_execution_id=parent_execution_id
        )

        # Rejestruj kontekst
        self._execution_contexts[execution_id] = context

        # Dodaj do stosu jeśli to zagnieżdżony scenariusz
        if parent_execution_id:
            self._execution_stack.append(execution_id)
            # Dodaj do listy zagnieżdżonych w rodzicu
            if parent_execution_id in self._execution_contexts:
                self._execution_contexts[parent_execution_id].nested_executions.append(execution_id)

        info(
            f"Utworzono kontekst wykonania: {execution_id} dla scenariusza '{scenario_name}'",
            message_logger=self.message_logger
        )

        if parent_execution_id:
            info(
                f"   └─ Zagnieżdżony w: {parent_execution_id}",
                message_logger=self.message_logger
            )

        return context

    async def pause_execution(self, execution_id: str) -> bool:
        """
        Zatrzymuje wykonanie scenariusza.

        Args:
            execution_id: ID wykonania do zatrzymania

        Returns:
            bool: True jeśli zatrzymano pomyślnie, False w przeciwnym razie
        """
        if execution_id not in self._execution_contexts:
            warning(
                f"Nie znaleziono wykonania o ID: {execution_id}",
                message_logger=self.message_logger
            )
            return False

        context = self._execution_contexts[execution_id]

        if context.state != ExecutionState.RUNNING:
            warning(
                f"Wykonanie {execution_id} nie jest w stanie RUNNING (aktualny: {context.state})",
                message_logger=self.message_logger
            )
            return False

        # Zatrzymaj wykonanie
        context.pause_event.clear()
        context.state = ExecutionState.PAUSED
        context.paused_at = datetime.now()

        info(
            f"⏸Zatrzymano wykonanie scenariusza: {execution_id} ({context.scenario_name})",
            message_logger=self.message_logger
        )

        return True

    async def resume_execution(self, execution_id: str) -> bool:
        """
        Wznawia wykonanie scenariusza.

        Args:
            execution_id: ID wykonania do wznowienia

        Returns:
            bool: True jeśli wznowiono pomyślnie, False w przeciwnym razie
        """
        if execution_id not in self._execution_contexts:
            warning(
                f"Nie znaleziono wykonania o ID: {execution_id}",
                message_logger=self.message_logger
            )
            return False

        context = self._execution_contexts[execution_id]

        if context.state != ExecutionState.PAUSED:
            warning(
                f"Wykonanie {execution_id} nie jest zatrzymane (aktualny: {context.state})",
                message_logger=self.message_logger
            )
            return False

        # Wznów wykonanie
        context.pause_event.set()
        context.state = ExecutionState.RUNNING
        context.paused_at = None

        info(
            f"Wznowiono wykonanie scenariusza: {execution_id} ({context.scenario_name})",
            message_logger=self.message_logger
        )

        return True

    async def wait_for_resume(self, execution_id: str) -> None:
        """
        Oczekuje na wznowienie wykonania (używane wewnętrznie przez akcje).

        Args:
            execution_id: ID wykonania
        """
        if execution_id in self._execution_contexts:
            context = self._execution_contexts[execution_id]
            await context.pause_event.wait()

    async def complete_execution(
        self, 
        execution_id: str, 
        success: bool = True, 
        error_message: Optional[str] = None
    ) -> None:
        """
        Oznacza wykonanie jako zakończone.

        Args:
            execution_id: ID wykonania
            success: Czy zakończone pomyślnie
            error_message: Komunikat błędu (jeśli success=False)
        """
        if execution_id not in self._execution_contexts:
            return

        context = self._execution_contexts[execution_id]
        context.completed_at = datetime.now()
        context.state = ExecutionState.COMPLETED if success else ExecutionState.FAILED
        
        if error_message:
            context.error_message = error_message

        # Usuń ze stosu jeśli to zagnieżdżony scenariusz
        if execution_id in self._execution_stack:
            self._execution_stack.remove(execution_id)

        # Przenieś do historii
        self._completed_executions[execution_id] = context
        del self._execution_contexts[execution_id]

        status = "✅ SUKCES" if success else "❌ BŁĄD"
        duration = (context.completed_at - context.started_at).total_seconds()
        
        info(
            f"🏁 Zakończono wykonanie: {execution_id} ({context.scenario_name}) - {status} ({duration:.2f}s)",
            message_logger=self.message_logger
        )

        if error_message:
            error(
                f"   └─ Błąd: {error_message}",
                message_logger=self.message_logger
            )

    def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """
        Zwraca status wykonania scenariusza.

        Args:
            execution_id: ID wykonania

        Returns:
            Dict[str, Any] | None: Status wykonania lub None jeśli nie znaleziono
        """
        # Sprawdź aktywne wykonania
        if execution_id in self._execution_contexts:
            context = self._execution_contexts[execution_id]
            return self._context_to_status_dict(context)

        # Sprawdź zakończone wykonania
        if execution_id in self._completed_executions:
            context = self._completed_executions[execution_id]
            return self._context_to_status_dict(context)

        return None

    def list_active_executions(self) -> List[Dict[str, Any]]:
        """
        Zwraca listę wszystkich aktywnych wykonań.

        Returns:
            List[Dict[str, Any]]: Lista statusów aktywnych wykonań
        """
        return [
            self._context_to_status_dict(context)
            for context in self._execution_contexts.values()
        ]

    def get_execution_stack(self) -> List[str]:
        """
        Zwraca aktualny stos zagnieżdżonych scenariuszy.

        Returns:
            List[str]: Lista ID wykonań w kolejności zagnieżdżenia
        """
        return self._execution_stack.copy()

    def _context_to_status_dict(self, context: ExecutionContext) -> Dict[str, Any]:
        """
        Konwertuje ExecutionContext na słownik statusu.

        Args:
            context: Kontekst wykonania

        Returns:
            Dict[str, Any]: Słownik ze statusem wykonania
        """
        duration = None
        if context.completed_at:
            duration = (context.completed_at - context.started_at).total_seconds()
        elif context.paused_at:
            duration = (context.paused_at - context.started_at).total_seconds()
        else:
            duration = (datetime.now() - context.started_at).total_seconds()

        return {
            "execution_id": context.execution_id,
            "scenario_name": context.scenario_name,
            "state": context.state.value,
            "current_action_index": context.current_action_index,
            "parent_execution_id": context.parent_execution_id,
            "nested_executions": context.nested_executions.copy(),
            "started_at": context.started_at.isoformat(),
            "paused_at": context.paused_at.isoformat() if context.paused_at else None,
            "completed_at": context.completed_at.isoformat() if context.completed_at else None,
            "duration_seconds": duration,
            "error_message": context.error_message,
            "is_nested": context.parent_execution_id is not None,
            "has_nested": len(context.nested_executions) > 0
        }

    async def cleanup_completed_executions(self, max_history: int = 100) -> None:
        """
        Czyści historię zakończonych wykonań.

        Args:
            max_history: Maksymalna liczba wykonań w historii
        """
        if len(self._completed_executions) <= max_history:
            return

        # Sortuj według czasu zakończenia i zachowaj najnowsze
        sorted_executions = sorted(
            self._completed_executions.items(),
            key=lambda x: x[1].completed_at or datetime.min,
            reverse=True
        )

        # Zachowaj tylko najnowsze
        to_keep = dict(sorted_executions[:max_history])
        removed_count = len(self._completed_executions) - len(to_keep)
        
        self._completed_executions = to_keep

        if removed_count > 0:
            debug(
                f"🧹 Wyczyszczono {removed_count} starych wykonań z historii",
                message_logger=self.message_logger
            )
