"""
BaseAction - klasa bazowa dla wszystkich akcji scenariuszy z ScenarioContext.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..models.scenario_models import ScenarioContext


class BaseAction(ABC):
    """
    Bazowa klasa abstrakcyjna dla wszystkich akcji scenariuszy.

    Każda akcja musi implementować metodę execute() która przyjmuje:
    - action_config: słownik z konfiguracją akcji z YAML
    - context: ScenarioContext z danymi potrzebnymi do wykonania
    """

    @abstractmethod
    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> Any:
        """
        Wykonuje akcję na podstawie konfiguracji i kontekstu.

        Args:
            action_config: Konfiguracja akcji z pliku YAML
            context: Kontekst scenariusza z danymi do wykonania

        Returns:
            Any: Wynik wykonania akcji

        Raises:
            ActionExecutionError: Gdy wystąpi błąd podczas wykonywania akcji
        """
        pass

    def _resolve_template_variables(self, text: str, context: ScenarioContext) -> str:
        """
        Rozwiązuje zmienne templatów w tekście używając kontekstu scenariusza.

        Args:
            text: Tekst z potencjalnymi zmiennymi template
            context: Kontekst scenariusza z danymi

        Returns:
            str: Tekst z rozwiązanymi zmiennymi
        """
        if not text or not isinstance(text, str):
            return str(text) if text is not None else ""

        from jinja2 import BaseLoader, Environment

        # Środowisko Jinja2 do renderowania szablonów
        env = Environment(loader=BaseLoader())

        # Przygotowanie danych kontekstowych dla templateów
        template_data = {}

        # Dodanie danych z kontekstu scenariusza
        if hasattr(context, 'context') and context.context:
            template_data.update(context.context)

        # Dodanie podstawowych danych z context
        template_data['scenario_name'] = context.scenario_name

        # Renderowanie szablonu
        try:
            template = env.from_string(text)
            result = template.render(**template_data)
            return result
        except Exception as e:
            from avena_commons.util.logger import error
            error(f"Błąd podczas renderowania template: {e}", message_logger=context.message_logger)
            return text

    def _get_config_value(
        self, 
        action_config: Dict[str, Any], 
        key: str, 
        default: Any = None, 
        required: bool = False,
        context: Optional[ScenarioContext] = None
    ) -> Any:
        """
        Pobiera wartość z konfiguracji akcji z obsługą templateów.

        Args:
            action_config: Konfiguracja akcji
            key: Klucz do pobrania
            default: Wartość domyślna
            required: Czy wartość jest wymagana
            context: Kontekst scenariusza dla templateów

        Returns:
            Any: Wartość z konfiguracji (z rozwiązanymi templateami)

        Raises:
            ActionExecutionError: Gdy wymagana wartość nie istnieje
        """
        value = action_config.get(key, default)
        
        if required and value is None:
            raise ActionExecutionError(
                action_config.get("type", "unknown"),
                f"Brak wymaganego parametru '{key}' w konfiguracji akcji"
            )
        
        # Rozwiąż templaty jeśli wartość jest stringiem i mamy kontekst
        if isinstance(value, str) and context:
            value = self._resolve_template_variables(value, context)
        
        return value

    def _validate_config(
        self, 
        action_config: Dict[str, Any], 
        required_keys: list,
        context: Optional[ScenarioContext] = None
    ) -> Dict[str, Any]:
        """
        Waliduje konfigurację akcji i zwraca przetworzone wartości.

        Args:
            action_config: Konfiguracja akcji do walidacji
            required_keys: Lista wymaganych kluczy
            context: Kontekst scenariusza dla templateów

        Returns:
            Dict[str, Any]: Przetworzona konfiguracja

        Raises:
            ActionExecutionError: Gdy brakuje wymaganych parametrów
        """
        processed_config = {}
        action_type = action_config.get("type", "unknown")
        
        for key in required_keys:
            processed_config[key] = self._get_config_value(
                action_config, key, required=True, context=context
            )
        
        return processed_config


class ActionExecutionError(Exception):
    """
    Wyjątek rzucany podczas błędów wykonywania akcji.
    """

    def __init__(
        self,
        action_type: str,
        message: str,
        original_exception: Optional[Exception] = None,
    ):
        """
        Inicjalizuje wyjątek ActionExecutionError.

        Args:
            action_type: Typ akcji która spowodowała błąd
            message: Wiadomość błędu
            original_exception: Oryginalny wyjątek (opcjonalny)
        """
        super().__init__(message)
        self.action_type = action_type
        self.message = message
        self.original_exception = original_exception

    def __str__(self):
        if self.original_exception:
            return f"[{self.action_type}] {self.message} (Causa: {self.original_exception})"
        return f"[{self.action_type}] {self.message}"

    def __repr__(self):
        return (
            f"ActionExecutionError(action_type='{self.action_type}', "
            f"message='{self.message}', "
            f"original_exception={repr(self.original_exception)})"
        )
