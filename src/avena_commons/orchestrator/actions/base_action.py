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
    
    def __str__(self):
        return f"ActionContext(scenario={self.scenario_name}, trigger_data={self.trigger_data}, additional_data={self.additional_data})"
    
    def __repr__(self):
        return self.__str__()


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
        if not isinstance(text, str):
            return text

        result = text

        # Jeśli brak trigger_data, nadal zwracamy tekst z ewentualnymi fallbackami poniżej
        trigger = context.trigger_data or {}

        # Podstawowe zmienne trigger.*
        if "{{ trigger.source }}" in result and trigger.get("source"):
            result = result.replace("{{ trigger.source }}", str(trigger["source"]))

        if (
            "{{ trigger.transaction_id }}" in result
            and trigger.get("transaction_id") is not None
        ):
            result = result.replace(
                "{{ trigger.transaction_id }}", str(trigger["transaction_id"])
            )

        if "{{ trigger.admin_email }}" in result and trigger.get("admin_email"):
            result = result.replace(
                "{{ trigger.admin_email }}", str(trigger["admin_email"])
            )

        if "{{ trigger.payload.error_code }}" in result:
            payload = trigger.get("payload", {})
            if payload.get("error_code") is not None:
                result = result.replace(
                    "{{ trigger.payload.error_code }}", str(payload["error_code"])
                )

        # Nowe: {{ trigger.error_message }} oraz {{ error_message }}
        # 1) trigger.error_message - pochodzi bezpośrednio z trigger_data
        if "{{ trigger.error_message }}" in result:
            err_msg = trigger.get("error_message")
            if err_msg is not None:
                result = result.replace("{{ trigger.error_message }}", str(err_msg))

        # Nowe: zmienne dla refund approve
        if "{{ trigger.refund_document_url }}" in result and trigger.get(
            "refund_document_url"
        ):
            result = result.replace(
                "{{ trigger.refund_document_url }}", str(trigger["refund_document_url"])
            )

        if "{{ trigger.machine_au_time }}" in result and trigger.get("machine_au_time"):
            result = result.replace(
                "{{ trigger.machine_au_time }}", str(trigger["machine_au_time"])
            )

        # 2) error_message - uniwersalny placeholder: użyj trigger.error_message,
        #    a gdy brak - spróbuj zbudować z orchestrator._state (klienci w błędzie)
        if "{{ error_message }}" in result:
            replacement = None

            if trigger.get("error_message") is not None:
                replacement = str(trigger["error_message"])  # typowo string lub lista
            else:
                try:
                    orch = context.orchestrator
                    clients_with_errors = []
                    for client_name, st in getattr(orch, "_state", {}).items():
                        try:
                            if st.get("error") and st.get("error_message") is not None:
                                msg = st.get("error_message")
                                if isinstance(msg, (list, tuple)):
                                    msg = ", ".join(str(m) for m in msg)
                                clients_with_errors.append(f"{client_name}: {msg}")
                        except Exception:
                            continue
                    if clients_with_errors:
                        replacement = "; ".join(sorted(clients_with_errors))
                except Exception:
                    pass

            if replacement is None:
                replacement = "(brak)"
            result = result.replace("{{ error_message }}", replacement)

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
