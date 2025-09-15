from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from avena_commons.util.logger import MessageLogger


class BaseCondition(ABC):
    """
    Bazowa klasa dla wszystkich warunków w systemie.

    Klasy pochodne muszą zaimplementować metodę asynchroniczną `evaluate`.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        message_logger: Optional[MessageLogger] = None,
        condition_factory=None,
    ):
        """
        Inicjalizuje warunek bazowy.

        Args:
            config (Dict[str, Any]): Konfiguracja warunku (specyficzna dla implementacji).
            message_logger (MessageLogger | None): Logger wiadomości dla debugowania.
            condition_factory (ConditionFactory | None): Fabryka do tworzenia warunków zagnieżdżonych.
        """
        self.config = config
        self.message_logger = message_logger
        self.condition_factory = condition_factory
        self.condition_type = self.__class__.__name__.replace("Condition", "").lower()

    def _resolve_template_variables(self, text: str, context) -> Any:
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
        if hasattr(context, "scenario_name"):
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
                        value = value[key]
                    return value
                else:
                    # Prosty klucz
                    return template_data[var_expression]
            except (KeyError, TypeError, AttributeError):
                # Zmienna nie istnieje, zwróć oryginalny tekst
                return text

        # Dla wielozmiennych templateów, użyj Jinja2
        try:
            from jinja2 import Template

            template = Template(text)
            return template.render(**template_data)
        except Exception:
            # Jeśli Jinja2 nie jest dostępne lub wystąpił błąd, zwróć oryginalny tekst
            return text

    def _resolve_template_variables_in_dict(
        self, data: Dict[str, Any], context
    ) -> Dict[str, Any]:
        """
        Rozwiązuje zmienne templatów w słowniku rekurencyjnie.

        Args:
            data: Słownik z potencjalnymi zmiennymi template
            context: Kontekst scenariusza z danymi

        Returns:
            Dict[str, Any]: Słownik z rozwiązanymi zmiennymi
        """
        resolved_data = {}

        for key, value in data.items():
            if isinstance(value, str):
                resolved_data[key] = self._resolve_template_variables(value, context)
            elif isinstance(value, dict):
                resolved_data[key] = self._resolve_template_variables_in_dict(
                    value, context
                )
            elif isinstance(value, list):
                resolved_data[key] = [
                    self._resolve_template_variables(item, context)
                    if isinstance(item, str)
                    else self._resolve_template_variables_in_dict(item, context)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                resolved_data[key] = value

        return resolved_data

    @abstractmethod
    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Sprawdza czy warunek jest spełniony.

        Args:
            context: Kontekst z orkiestratorem (stan komponentów, baza danych, etc.)

        Returns:
            True jeśli warunek spełniony, False w przeciwnym razie
        """
        pass

    def get_description(self) -> str:
        """
        Zwraca zwięzły opis warunku do celów logowania.

        Returns:
            str: Opis zawierający typ warunku i jego konfigurację.
        """
        return f"{self.condition_type}: {self.config}"

    def _create_condition(self, condition_config: Dict[str, Any]) -> "BaseCondition":
        """
        Tworzy instancję warunku (zagnieżdżonego) na podstawie konfiguracji.

        Args:
            condition_config (Dict[str, Any]): Konfiguracja pojedynczego warunku.

        Returns:
            BaseCondition: Utworzona instancja warunku.

        Raises:
            RuntimeError: Gdy fabryka warunków nie została przekazana do konstruktora.
        """
        if self.condition_factory is None:
            raise RuntimeError(
                "ConditionFactory nie została przekazana do konstruktora"
            )
        return self.condition_factory.create_condition(
            condition_config, self.message_logger
        )
