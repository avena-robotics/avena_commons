"""
Bazowa klasa abstrakcyjna dla wszystkich akcji scenariuszy.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from avena_commons.util.logger import MessageLogger


@dataclass
class ActionContext:
    """
    Kontekst wykonania akcji scenariusza.
    Zawiera wszystkie dane potrzebne do wykonania akcji.
    """

    # Referencja do Orchestratora dla dostępu do jego metod
    orchestrator: Any  # Unikamy circular import

    # Logger dla akcji
    message_logger: Optional[MessageLogger] = None

    # Dane z triggera scenariusza (dla zmiennych {{ trigger.* }})
    trigger_data: Optional[Dict[str, Any]] = None

    # Nazwa aktualnie wykonywanego scenariusza
    scenario_name: Optional[str] = None

    # Dodatkowe dane kontekstowe
    additional_data: Optional[Dict[str, Any]] = None


class BaseAction(ABC):
    """
    Bazowa klasa abstrakcyjna dla wszystkich akcji scenariuszy.

    Każda akcja musi implementować metodę execute() która przyjmuje:
    - action_config: słownik z konfiguracją akcji z YAML
    - context: ActionContext z danymi potrzebnymi do wykonania
    """

    @abstractmethod
    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Any:
        """
        Wykonuje akcję na podstawie konfiguracji i kontekstu.

        Args:
            action_config: Konfiguracja akcji z pliku YAML
            context: Kontekst wykonania z danymi Orchestratora

        Returns:
            Wynik wykonania akcji (opcjonalny)

        Raises:
            ActionExecutionError: W przypadku błędu wykonania akcji
        """
        pass

    def _resolve_template_variables(self, text: str, context: ActionContext) -> str:
        """
        Rozwiązuje zmienne szablonowe w tekście typu {{ trigger.source }}.

        Args:
            text: Tekst z potencjalnymi zmiennymi szablonowymi
            context: Kontekst z danymi do podstawienia

        Returns:
            Tekst z podstawionymi zmiennymi
        """
        if not isinstance(text, str) or not context.trigger_data:
            return text

        result = text

        # Podstawowe zmienne trigger.*
        if "{{ trigger.source }}" in result and context.trigger_data.get("source"):
            result = result.replace(
                "{{ trigger.source }}", str(context.trigger_data["source"])
            )

        if "{{ trigger.payload.error_code }}" in result:
            payload = context.trigger_data.get("payload", {})
            if payload.get("error_code"):
                result = result.replace(
                    "{{ trigger.payload.error_code }}", str(payload["error_code"])
                )

        # Można dodać więcej zmiennych w przyszłości

        return result

    def _parse_timeout(self, timeout_str: str) -> float:
        """
        Parsuje string timeout (np. '30s', '2m') na sekundy.

        Args:
            timeout_str: String z timeout (np. "30s", "2m", "1.5h")

        Returns:
            Timeout w sekundach jako float
        """
        if isinstance(timeout_str, (int, float)):
            return float(timeout_str)

        timeout_str = str(timeout_str).strip().lower()

        if timeout_str.endswith("s"):
            return float(timeout_str[:-1])
        elif timeout_str.endswith("m"):
            return float(timeout_str[:-1]) * 60
        elif timeout_str.endswith("h"):
            return float(timeout_str[:-1]) * 3600
        else:
            # Assume seconds if no unit
            return float(timeout_str)


class ActionExecutionError(Exception):
    """
    Wyjątek rzucany w przypadku błędu wykonania akcji scenariusza.
    """

    def __init__(
        self,
        action_type: str,
        message: str,
        original_exception: Optional[Exception] = None,
    ):
        self.action_type = action_type
        self.original_exception = original_exception
        super().__init__(f"Action '{action_type}' failed: {message}")
