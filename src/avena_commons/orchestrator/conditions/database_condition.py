"""
Warunek bazodanowy dla orchestratora.

Sprawdza wartości w bazie danych używając komponentów bazodanowych
zarejestrowanych w orchestratorze.
"""

from typing import Any, Dict

from avena_commons.util.logger import debug, error

from ..base.base_condition import BaseCondition


class DatabaseCondition(BaseCondition):
    """
    Warunek sprawdzający wartość w bazie danych.

    Używa komponentu bazodanowego z orchestratora do wykonania zapytania
    i porównania wartości.

    Przykład konfiguracji:
    {
        "type": "database",
        "component": "main_database",  # nazwa komponentu z konfiguracji orchestratora
        "table": "users",
        "column": "status",
        "where": {
            "id": 123,
            "active": true
        },
        "expected_value": "pending_verification",
        "operator": "equals"  # equals, not_equals, in, not_in, greater, less, is_null, is_not_null
    }
    """

    SUPPORTED_OPERATORS = [
        "equals",
        "not_equals",
        "in",
        "not_in",
        "greater",
        "less",
        "greater_equal",
        "less_equal",
        "is_null",
        "is_not_null",
    ]

    def __init__(self, config: Dict[str, Any], message_logger=None):
        """
        Inicjalizuje warunek bazodanowy.

        Args:
            config: Konfiguracja warunku
            message_logger: Logger wiadomości
        """
        super().__init__(config, message_logger)

        # Walidacja konfiguracji
        self._validate_config()

        # Parametry zapytania
        self.component_name = self.config["component"]
        self.table = self.config["table"]
        self.column = self.config["column"]
        self.where_conditions = self.config["where"]
        self.expected_value = self.config.get("expected_value")
        self.operator = self.config.get("operator", "equals")

    def _validate_config(self) -> None:
        """
        Waliduje konfigurację warunku bazodanowego.

        Raises:
            ValueError: Jeśli konfiguracja jest niepoprawna
        """
        # Sprawdź podstawowe pola
        required_fields = ["component", "table", "column", "where"]
        for field in required_fields:
            if field not in self.config:
                raise ValueError(
                    f"Brakuje wymaganego pola '{field}' w konfiguracji warunku bazodanowego"
                )

        if not isinstance(self.config["where"], dict) or not self.config["where"]:
            raise ValueError("Pole 'where' musi być niepustym słownikiem")

        # Sprawdź operator
        operator = self.config.get("operator", "equals")
        if operator not in self.SUPPORTED_OPERATORS:
            raise ValueError(
                f"Nieobsługiwany operator: '{operator}'. "
                f"Obsługiwane operatory: {self.SUPPORTED_OPERATORS}"
            )

        # Sprawdź czy expected_value jest wymagane dla operatora
        null_operators = ["is_null", "is_not_null"]
        if operator not in null_operators and "expected_value" not in self.config:
            raise ValueError(f"Operator '{operator}' wymaga pola 'expected_value'")

    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Ewaluuje warunek bazodanowy.

        Args:
            context: Kontekst zawierający komponenty orchestratora

        Returns:
            True jeśli warunek jest spełniony, False w przeciwnym razie
        """
        try:
            # Pobierz komponent bazodanowy z kontekstu
            components = context.get("components", {})
            if self.component_name not in components:
                error(
                    f"❌ Komponent bazodanowy '{self.component_name}' nie został znaleziony w orchestratorze",
                    message_logger=self._message_logger,
                )
                return False

            db_component = components[self.component_name]

            # Sprawdź czy komponent jest połączony
            if not db_component.is_connected:
                error(
                    f"❌ Komponent bazodanowy '{self.component_name}' nie jest połączony",
                    message_logger=self._message_logger,
                )
                return False

            # Wykonaj zapytanie do bazy danych
            debug(
                f"🔍 Sprawdzanie warunku bazodanowego: komponent={self.component_name}, "
                f"tabela={self.table}, kolumna={self.column}, warunki={self.where_conditions}",
                message_logger=self._message_logger,
            )

            # Automatycznie dodaj filtry APS_ID i APS_NAME z konfiguracji komponentu
            enhanced_where_conditions = self.where_conditions.copy()

            # Pobierz APS_ID i APS_NAME z konfiguracji komponentu
            aps_id = db_component.config.get("APS_ID")
            aps_name = db_component.config.get("APS_NAME")

            if aps_id:
                enhanced_where_conditions["id"] = aps_id
                debug(
                    f"🔧 Automatycznie dodano filtr id={aps_id} z konfiguracji komponentu",
                    message_logger=self._message_logger,
                )

            if aps_name:
                enhanced_where_conditions["name"] = aps_name
                debug(
                    f"🔧 Automatycznie dodano filtr name={aps_name} z konfiguracji komponentu",
                    message_logger=self._message_logger,
                )

            actual_value = await db_component.check_table_value(
                table=self.table,
                column=self.column,
                where_conditions=enhanced_where_conditions,
            )

            debug(
                f"📊 Wartość z bazy danych: {actual_value}, oczekiwana: {self.expected_value}, operator: {self.operator}",
                message_logger=self._message_logger,
            )

            # Porównaj wartości według operatora
            result = self._compare_values(
                actual_value, self.expected_value, self.operator
            )

            debug(
                f"✅ Wynik warunku bazodanowego: {result}",
                message_logger=self._message_logger,
            )

            return result

        except Exception as e:
            error(
                f"❌ Błąd ewaluacji warunku bazodanowego: {e}",
                message_logger=self._message_logger,
            )
            return False

    def _compare_values(self, actual: Any, expected: Any, operator: str) -> bool:
        """
        Porównuje wartości według określonego operatora.

        Args:
            actual: Rzeczywista wartość z bazy danych
            expected: Oczekiwana wartość
            operator: Operator porównania

        Returns:
            True jeśli porównanie jest prawdziwe
        """
        match operator:
            case "equals":
                return actual == expected
            case "not_equals":
                return actual != expected
            case "in":
                return actual in expected if expected is not None else False
            case "not_in":
                return actual not in expected if expected is not None else True
            case "greater":
                return (
                    actual > expected
                    if actual is not None and expected is not None
                    else False
                )
            case "less":
                return (
                    actual < expected
                    if actual is not None and expected is not None
                    else False
                )
            case "greater_equal":
                return (
                    actual >= expected
                    if actual is not None and expected is not None
                    else False
                )
            case "less_equal":
                return (
                    actual <= expected
                    if actual is not None and expected is not None
                    else False
                )
            case "is_null":
                return actual is None
            case "is_not_null":
                return actual is not None
            case _:
                raise ValueError(f"Nieobsługiwany operator: {operator}")

    def __str__(self) -> str:
        """Zwraca czytelny opis warunku."""
        return (
            f"DatabaseCondition(component={self.component_name}, "
            f"table={self.table}, column={self.column}, "
            f"where={self.where_conditions}, "
            f"expected={self.expected_value}, operator={self.operator})"
        )
