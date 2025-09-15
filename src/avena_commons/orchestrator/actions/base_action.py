# AI: BaseAction implementuje template rendering z zachowaniem typów dla pojedynczych zmiennych Jinja2 oraz standardowe renderowanie dla mieszanego tekstu. Obsługuje zagnieżdżone struktury i notację kropkową. Zawiera globalne śledzenie błędów akcji poprzez zmienne klasowe.
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

    Zawiera metody pomocnicze do zarządzania błędami akcji i ich licznikami.
    Liczniki błędów są przechowywane jako zmienne klasowe, więc są wspólne
    dla wszystkich instancji akcji.
    """

    # Globalne liczniki kolejnych błędów akcji (wg typu akcji)
    # Klucze: np. "send_sms", "send_email"
    _action_error_counts: Dict[str, int] = {}

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

    # ==== Metody pomocnicze do zarządzania błędami akcji ====

    @classmethod
    def get_action_error_count(cls, action_type: str) -> int:
        """
        Zwraca liczbę kolejnych błędów dla danego typu akcji.

        Args:
            action_type: Typ akcji (np. "send_sms", "send_email")

        Returns:
            int: Liczba kolejnych błędów
        """
        return int(cls._action_error_counts.get(action_type, 0))

    @classmethod
    def increment_action_error_count(cls, action_type: str) -> int:
        """
        Zwiększa licznik kolejnych błędów dla danego typu akcji i zwraca aktualną wartość.

        Args:
            action_type: Typ akcji (np. "send_sms", "send_email")

        Returns:
            int: Aktualna liczba kolejnych błędów
        """
        current = int(cls._action_error_counts.get(action_type, 0)) + 1
        cls._action_error_counts[action_type] = current
        return current

    @classmethod
    def reset_action_error_count(cls, action_type: str) -> None:
        """
        Zeruje licznik kolejnych błędów dla danego typu akcji.

        Args:
            action_type: Typ akcji (np. "send_sms", "send_email")
        """
        if action_type in cls._action_error_counts:
            del cls._action_error_counts[action_type]

    @classmethod
    def should_skip_action_due_to_errors(
        cls, action_type: str, max_attempts: int
    ) -> bool:
        """
        Sprawdza czy należy pominąć wykonanie akcji z powodu przekroczenia
        dozwolonej liczby kolejnych błędów.

        Args:
            action_type: Typ akcji (np. "send_sms", "send_email")
            max_attempts: Maksymalna liczba prób (None lub <= 0 = bez limitu)

        Returns:
            bool: True jeśli akcja powinna być pominięta, False w przeciwnym razie
        """
        if max_attempts is None:
            return False
        try:
            max_attempts_int = int(max_attempts)
        except Exception:
            max_attempts_int = 0
        if max_attempts_int <= 0:
            return False
        return cls.get_action_error_count(action_type) >= max_attempts_int

    @classmethod
    def get_all_error_counts(cls) -> Dict[str, int]:
        """
        Zwraca kopię wszystkich liczników błędów akcji.

        Returns:
            Dict[str, int]: Słownik z licznikami błędów dla każdego typu akcji
        """
        return cls._action_error_counts.copy()

    def _resolve_template_variables(self, text: str, context: ScenarioContext) -> Any:
        """
        Rozwiązuje zmienne templatów w tekście używając kontekstu scenariusza.

        Jeśli cały tekst to jedna zmienna Jinja ({{ var }}), zwraca oryginalną wartość
        zachowując typ. W przeciwnym razie renderuje jako string.

        Args:
            text: Tekst z potencjalnymi zmiennymi template
            context: Kontekst scenariusza z danymi

        Returns:
            Any: Wartość zmiennej z zachowanym typem lub wyrenderowany string
        """
        if not text or not isinstance(text, str):
            return str(text) if text is not None else ""

        import re

        # Przygotowanie danych kontekstowych dla templateów
        template_data = {}

        # Dodanie danych z kontekstu scenariusza
        if hasattr(context, "context") and context.context:
            template_data.update(context.context)

        # Dodanie podstawowych danych z context
        template_data["scenario_name"] = context.scenario_name

        # Sprawdź czy cały tekst to jedna zmienna (np. "{{ variable }}" lub "{{ var.attr }}")
        single_var_pattern = r"^\s*\{\{\s*([^}]+)\s*\}\}\s*$"
        match = re.match(single_var_pattern, text)

        if match:
            # Wyciągnij nazwę zmiennej
            var_expression = match.group(1).strip()

            try:
                # Obsługa zagnieżdżonych kluczy jak "data.key" lub "var.attribute"
                if "." in var_expression:
                    keys = var_expression.split(".")
                    value = template_data
                    for key in keys:
                        if isinstance(value, dict):
                            value = value[key]
                        else:
                            # Dla obiektów użyj getattr
                            value = getattr(value, key)
                    return value
                else:
                    # Prosty klucz
                    return template_data[var_expression]

            except (KeyError, AttributeError, TypeError) as e:
                from avena_commons.util.logger import error

                error(
                    f"Nie można pobrać zmiennej '{var_expression}': {e}",
                    message_logger=context.message_logger,
                )
                return None

        # Jeśli to nie jest pojedyncza zmienna, użyj standardowego renderowania Jinja2
        from jinja2 import BaseLoader, Environment

        env = Environment(loader=BaseLoader())

        try:
            template = env.from_string(text)
            result = template.render(**template_data)
            return result
        except Exception as e:
            from avena_commons.util.logger import error

            error(
                f"Błąd podczas renderowania template: {e}",
                message_logger=context.message_logger,
            )
            return text

    def _get_config_value(
        self,
        action_config: Dict[str, Any],
        key: str,
        default: Any = None,
        required: bool = False,
        context: Optional[ScenarioContext] = None,
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
            Any: Wartość z konfiguracji z zachowanymi typami danych

        Raises:
            ActionExecutionError: Gdy wymagana wartość nie istnieje
        """
        value = action_config.get(key, default)

        if required and value is None:
            raise ActionExecutionError(
                action_config.get("type", "unknown"),
                f"Brak wymaganego parametru '{key}' w konfiguracji akcji",
            )

        # Rozwiąż templaty zachowując oryginalne typy
        if context:
            return self._resolve_nested_templates(value, context)

        return value

    def _resolve_nested_templates(self, data: Any, context: ScenarioContext) -> Any:
        """
        Rekurencyjnie rozwiązuje templaty w zagnieżdżonych strukturach danych.

        Args:
            data: Dane do przetworzenia (może być string, lista, słownik, etc.)
            context: Kontekst scenariusza

        Returns:
            Any: Przetworzone dane z rozwiązanymi templateami i zachowanymi typami
        """
        if isinstance(data, str):
            return self._resolve_template_variables(data, context)
        elif isinstance(data, dict):
            return {
                key: self._resolve_nested_templates(value, context)
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return [self._resolve_nested_templates(item, context) for item in data]
        else:
            # Dla innych typów (int, float, bool, None, etc.) zwróć bez zmian
            return data

    def _validate_config(
        self,
        action_config: Dict[str, Any],
        required_keys: list,
        context: Optional[ScenarioContext] = None,
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
