"""
Warunek bazodanowy pobierający listę rekordów dla orchestratora.

Rozszerza funkcjonalność DatabaseCondition o możliwość pobrania wielu rekordów
spełniających warunek i udostępnienia ich w kontekście scenariusza.
"""

import copy
from typing import Any, Dict, List

from avena_commons.util.logger import debug, error

from .database_condition_base import DatabaseCondition


class DatabaseListCondition(DatabaseCondition):
    """
    Warunek sprawdzający i pobierający listę rekordów z bazy danych.

    Rozszerza DatabaseCondition o funkcjonalność pobierania wielu rekordów
    spełniających warunek WHERE i udostępniania ich w akcjach scenariusza.

    Przykład konfiguracji:
    {
        "type": "database_list",
        "component": "main_database",
        "table": "zamowienia",
        "columns": ["id", "numer_zamowienia", "stan_zamowienia", "klient_id"],
        "where": {
            "stan_zamowienia": "refund"
        },
        "result_key": "zamowienia_do_zwrotu",
        "limit": 100,
        "order_by": "data_utworzenia DESC"
    }
    """

    def __init__(
        self, config: Dict[str, Any], message_logger=None, condition_factory=None
    ):
        """
        Inicjalizuje warunek bazodanowy dla listy rekordów.

        Args:
            config: Konfiguracja warunku
            message_logger: Logger wiadomości
            condition_factory: Fabryka warunków
        """
        # Wywołaj konstruktor rodzica, ale bez walidacji expected_value
        # (nie jest potrzebne dla list condition)
        super(DatabaseCondition, self).__init__(
            config, message_logger, condition_factory
        )

        # Walidacja konfiguracji specyficznej dla list condition
        self._validate_list_config()

        # Parametry zapytania
        self.component_name = self.config["component"]
        self.table = self.config["table"]
        self.columns = self.config["columns"]
        self.where_conditions = self.config["where"]
        self.result_key = self.config.get("result_key", "database_records")
        self.limit = self.config.get("limit")
        self.order_by = self.config.get("order_by")

    def _validate_list_config(self) -> None:
        """
        Waliduje konfigurację warunku bazodanowego dla listy rekordów.

        Raises:
            ValueError: Jeśli konfiguracja jest niepoprawna
        """
        # Sprawdź podstawowe pola (bez 'column' i 'expected_value')
        required_fields = ["component", "table", "columns", "where"]
        for field in required_fields:
            if field not in self.config:
                raise ValueError(
                    f"Brakuje wymaganego pola '{field}' w konfiguracji database_list condition"
                )

        # Waliduj columns
        if not isinstance(self.config["columns"], list) or not self.config["columns"]:
            raise ValueError("Pole 'columns' musi być niepustą listą")

        # Waliduj where
        if not isinstance(self.config["where"], dict) or not self.config["where"]:
            raise ValueError("Pole 'where' musi być niepustym słownikiem")

        # Waliduj limit jeśli podany
        if "limit" in self.config:
            limit_val = self.config["limit"]
            if not isinstance(limit_val, int) or limit_val <= 0:
                raise ValueError(
                    "Pole 'limit' musi być liczbą całkowitą większą od zera"
                )

        # Waliduj result_key jeśli podany
        if "result_key" in self.config:
            result_key = self.config["result_key"]
            if not isinstance(result_key, str) or not result_key.strip():
                raise ValueError("Pole 'result_key' musi być niepustym stringiem")

    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Ewaluuje warunek bazodanowy i pobiera listę rekordów.

        Pobiera rekordy spełniające warunek i zapisuje je w kontekście
        pod kluczem określonym przez result_key.

        Args:
            context: Kontekst zawierający komponenty orchestratora

        Returns:
            True jeśli znaleziono co najmniej jeden rekord, False w przeciwnym razie
        """
        try:
            # Pobierz komponent bazodanowy z kontekstu
            components = context.get("components", {})
            if self.component_name not in components:
                error(
                    f"❌ Komponent bazodanowy '{self.component_name}' nie został znaleziony w orchestratorze",
                    message_logger=self.message_logger,
                )
                return False

            db_component = components[self.component_name]

            # Sprawdź czy komponent jest połączony
            if not db_component.is_connected:
                error(
                    f"❌ Komponent bazodanowy '{self.component_name}' nie jest połączony",
                    message_logger=self.message_logger,
                )
                return False

            # Wykonaj zapytanie do bazy danych
            debug(
                f"📋 Pobieranie listy rekordów: komponent={self.component_name}, "
                f"tabela={self.table}, kolumny={self.columns}, warunki={self.where_conditions}",
                message_logger=self.message_logger,
            )

            # Pozwól klasom pochodnym rozszerzyć WHERE (dziedziczone z DatabaseCondition)
            enhanced_where_conditions = self._augment_where(
                self.where_conditions, db_component
            )

            # Pobierz rekordy z bazy danych
            records = await db_component.fetch_records(
                table=self.table,
                columns=self.columns,
                where_conditions=enhanced_where_conditions,
                limit=self.limit,
                order_by=self.order_by,
            )

            debug(
                f"📊 Pobrano {len(records)} rekordów z tabeli '{self.table}'",
                message_logger=self.message_logger,
            )

            # Zapisz wyniki w kontekście
            self._store_records_in_context(context, records)

            # Zwróć True jeśli znaleziono rekordy, False jeśli lista pusta
            result = len(records) > 0

            debug(
                f"✅ Wynik database_list condition: {result} ({len(records)} rekordów)",
                message_logger=self.message_logger,
            )

            return result

        except Exception as e:
            error(
                f"❌ Błąd ewaluacji database_list condition: {e}",
                message_logger=self.message_logger,
            )
            return False

    def _store_records_in_context(
        self, context: Dict[str, Any], records: List[Dict[str, Any]]
    ) -> None:
        """
        Zapisuje pobrane rekordy w kontekście pod określonym kluczem.

        Rekordy są dostępne dla akcji w scenariuszu przez trigger_data.

        Args:
            context: Kontekst wykonania
            records: Lista rekordów do zapisania
        """
        # Upewnij się, że istnieje struktura dla danych trigger
        if "trigger_data" not in context:
            context["trigger_data"] = {}

        # Zapisz rekordy pod określonym kluczem
        context["trigger_data"][self.result_key] = records
        
        self._context = copy.deepcopy(context)

        debug(
            f"💾 Zapisano {len(records)} rekordów w kontekście pod kluczem '{self.result_key}'",
            message_logger=self.message_logger,
        )

    def __str__(self) -> str:
        """Zwraca czytelny opis warunku."""
        return (
            f"DatabaseListCondition(component={self.component_name}, "
            f"table={self.table}, columns={self.columns}, "
            f"where={self.where_conditions}, result_key={self.result_key}, "
            f"limit={self.limit})"
        )
