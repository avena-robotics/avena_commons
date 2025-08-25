"""
Komponent bazodanowy dla orchestratora.

Obsługuje połączenia z bazami danych PostgreSQL i udostępnia interfejs
do wykonywania zapytań SQL dla warunków.
"""

import asyncio
import os
from typing import Any, Dict, Optional

import asyncpg

from avena_commons.util.logger import debug, error, info, warning

from .enums import CurrentState, GoalState


class DatabaseComponent:
    """
    Komponent do obsługi połączeń z bazą danych PostgreSQL.

    Inicjalizowany przez orchestrator przy starcie i udostępniany warunkom.

    Wymagane parametry w konfiguracji lub zmiennych środowiskowych:
    - DB_HOST: Adres hosta bazy danych
    - DB_PORT: Port bazy danych
    - DB_NAME: Nazwa bazy danych
    - DB_USER: Nazwa użytkownika
    - DB_PASSWORD: Hasło użytkownika
    - APS_ID: Identyfikator aplikacji
    - APS_NAME: Nazwa aplikacji
    """

    def __init__(self, name: str, config: Dict[str, Any], message_logger=None):
        """
        Inicjalizuje komponent bazodanowy.

        Args:
            name: Nazwa komponentu
            config: Konfiguracja komponentu z orchestratora
            message_logger: Logger wiadomości
        """
        self.name = name
        self.config = config
        self._message_logger = message_logger
        self._connection: Optional[asyncpg.Connection] = None
        self._connection_params: Dict[str, Any] = {}
        self._is_connected = False
        self._is_initialized = False
        self._conn_lock: asyncio.Lock = asyncio.Lock()

    def _to_db_value_for_column(self, column: str, value: Any) -> Any:
        """
        Konwertuje wartość dla wybranych kolumn do typu Enum (CurrentState).

        Dotyczy wyłącznie kolumn: 'goal_state' i 'current_state'.
        Dla innych kolumn zwraca oryginalną wartość bez zmian.
        """
        try:
            if column == "current_state":
                if value is None:
                    return None
                if isinstance(value, CurrentState):
                    return value
                if isinstance(value, str):
                    normalized = value.strip().lower()
                    return CurrentState(normalized)
                # Jeśli podano inny Enum, spróbuj z jego value
                if hasattr(value, "value"):
                    return CurrentState(str(value.value).strip().lower())
            elif column == "goal_state":
                if value is None:
                    return None
                if isinstance(value, GoalState):
                    return value
                if isinstance(value, str):
                    normalized = value.strip().lower()
                    return GoalState(normalized)
                # Jeśli podano inny Enum, spróbuj z jego value
                if hasattr(value, "value"):
                    return GoalState(str(value.value).strip().lower())
        except Exception as e:
            raise ValueError(
                f"Nie można skonwertować wartości '{value}' kolumny '{column}' do CurrentState: {e}"
            )
        return value

    def _convert_where_conditions(
        self, where_conditions: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Zwraca kopię where_conditions z konwersją wartości tylko dla kolumn
        'goal_state' i 'current_state' do CurrentState Enum.
        """
        converted: Dict[str, Any] = {}
        for col, val in where_conditions.items():
            converted[col] = self._to_db_value_for_column(col, val)
        return converted

    def validate_config(self) -> bool:
        """
        Waliduje konfigurację komponentu bazodanowego.

        Returns:
            True jeśli konfiguracja jest poprawna

        Raises:
            ValueError: Jeśli brakuje wymaganych parametrów
            ImportError: Jeśli brakuje biblioteki asyncpg
        """
        if asyncpg is None:
            raise ImportError(
                "Biblioteka 'asyncpg' jest wymagana dla komponentu bazodanowego. "
                "Zainstaluj ją: pip install asyncpg"
            )

        required_params = [
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
            "APS_ID",
            "APS_NAME",
        ]

        missing_params = []

        for param in required_params:
            # Sprawdź najpierw w konfiguracji komponentu, potem w env
            value = self.config.get(param) or os.getenv(param)
            if not value:
                missing_params.append(param)
            else:
                # Zapisz parametr do użycia przy połączeniu
                if param.startswith("DB_"):
                    # Konwertuj DB_HOST -> host, DB_PORT -> port, etc.
                    key = param[3:].lower()  # Usuń prefiks "DB_"
                    if key == "name":
                        key = "database"  # asyncpg używa "database" zamiast "name"
                    self._connection_params[key] = value

        if missing_params:
            raise ValueError(
                f"Brakuje wymaganych parametrów konfiguracji dla komponentu bazodanowego '{self.name}': "
                f"{', '.join(missing_params)}. "
                "Parametry muszą być dostępne w konfiguracji komponentu lub zmiennych środowiskowych."
            )

        # Konwertuj port na int
        try:
            self._connection_params["port"] = int(self._connection_params["port"])
        except (ValueError, TypeError):
            raise ValueError(
                f"DB_PORT musi być liczbą całkowitą, otrzymano: {self._connection_params.get('port')}"
            )

        debug(
            f"✅ Walidacja konfiguracji komponentu bazodanowego '{self.name}' pomyślna",
            message_logger=self._message_logger,
        )

        return True

    async def initialize(self) -> bool:
        """
        Inicjalizuje komponent bazodanowy.

        Returns:
            True jeśli inicjalizacja przebiegła pomyślnie
        """
        try:
            # Waliduj konfigurację
            self.validate_config()

            info(
                f"🔧 Inicjalizacja komponentu bazodanowego: {self.name}",
                message_logger=self._message_logger,
            )

            self._is_initialized = True

            debug(
                f"✅ Komponent bazodanowy '{self.name}' zainicjalizowany",
                message_logger=self._message_logger,
            )

            return True

        except Exception as e:
            error(
                f"❌ Błąd inicjalizacji komponentu bazodanowego '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            self._is_initialized = False
            return False

    async def connect(self) -> bool:
        """
        Nawiązuje połączenie z bazą danych PostgreSQL.

        Returns:
            True jeśli połączenie zostało nawiązane pomyślnie
        """
        if not self._is_initialized:
            error(
                f"❌ Komponent bazodanowy '{self.name}' nie jest zainicjalizowany",
                message_logger=self._message_logger,
            )
            return False

        try:
            info(
                f"🔌 Nawiązywanie połączenia z bazą danych: {self.name}",
                message_logger=self._message_logger,
            )

            # Ukryj hasło w logach
            safe_params = self._connection_params.copy()
            safe_params["password"] = "***"
            debug(
                f"Parametry połączenia: {safe_params}",
                message_logger=self._message_logger,
            )

            # Nawiąż połączenie
            async with self._conn_lock:
                self._connection = await asyncpg.connect(**self._connection_params)

                # Sprawdź połączenie prostym zapytaniem
                result = await self._connection.fetchval("SELECT 1")
            if result == 1:
                self._is_connected = True
                info(
                    f"✅ Połączenie z bazą danych '{self.name}' nawiązane pomyślnie",
                    message_logger=self._message_logger,
                )
                return True
            else:
                raise Exception("Test połączenia nie powiódł się")

        except Exception as e:
            error(
                f"❌ Błąd nawiązywania połączenia z bazą danych '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            self._is_connected = False
            self._connection = None
            return False

    async def disconnect(self) -> bool:
        """
        Rozłącza połączenie z bazą danych.

        Returns:
            True jeśli rozłączenie przebiegło pomyślnie
        """
        try:
            async with self._conn_lock:
                if self._connection and not self._connection.is_closed():
                    info(
                        f"🔌 Rozłączanie z bazą danych: {self.name}",
                        message_logger=self._message_logger,
                    )
                    await self._connection.close()

            self._connection = None
            self._is_connected = False

            debug(
                f"✅ Rozłączono z bazą danych '{self.name}'",
                message_logger=self._message_logger,
            )

            return True

        except Exception as e:
            error(
                f"❌ Błąd rozłączania z bazą danych '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            return False

    async def health_check(self) -> bool:
        """
        Sprawdza stan zdrowia połączenia z bazą danych.

        Returns:
            True jeśli połączenie działa poprawnie
        """
        if not self._is_connected or not self._connection:
            return False

        try:
            if self._connection.is_closed():
                self._is_connected = False
                return False

            # Sprawdź połączenie prostym zapytaniem
            async with self._conn_lock:
                result = await self._connection.fetchval("SELECT 1")
                return result == 1

        except Exception as e:
            warning(
                f"⚠️ Health check bazy danych '{self.name}' nie powiódł się: {e}",
                message_logger=self._message_logger,
            )
            self._is_connected = False
            return False

    @property
    def is_connected(self) -> bool:
        """Zwraca True jeśli komponent jest połączony."""
        return self._is_connected

    @property
    def is_initialized(self) -> bool:
        """Zwraca True jeśli komponent jest zainicjalizowany."""
        return self._is_initialized

    async def check_table_value(
        self, table: str, column: str, where_conditions: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Sprawdza wartość w tabeli na podstawie warunków WHERE.

        Args:
            table: Nazwa tabeli
            column: Nazwa kolumny do pobrania
            where_conditions: Słownik z warunkami WHERE {kolumna: wartość}

        Returns:
            Wartość z kolumny lub None jeśli nie znaleziono

        Raises:
            RuntimeError: Jeśli komponent nie jest połączony
        """
        if not self._is_connected or not self._connection:
            raise RuntimeError(f"Komponent bazodanowy '{self.name}' nie jest połączony")

        if not where_conditions:
            raise ValueError("where_conditions nie może być pusty")

        # Buduj zapytanie WHERE
        where_parts = []
        values = []
        param_index = 1

        for col, val in where_conditions.items():
            where_parts.append(f"{col} = ${param_index}")
            values.append(val)
            param_index += 1

        where_clause = " AND ".join(where_parts)
        query = f"SELECT {column} FROM {table} WHERE {where_clause}"

        try:
            debug(
                f"🔍 Wykonywanie zapytania w bazie '{self.name}': {query[:100]}{'...' if len(query) > 100 else ''}",
                message_logger=self._message_logger,
            )

            async with self._conn_lock:
                return await self._connection.fetchval(query, *values)

        except Exception as e:
            error(
                f"❌ Błąd wykonania zapytania w bazie '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            raise

    async def update_table_value(
        self,
        table: str,
        column: str,
        value: Any,
        where_conditions: Dict[str, Any],
    ) -> int:
        """
        Aktualizuje wskazaną kolumnę stałą wartością dla wierszy spełniających warunki.

        Args:
            table: Nazwa tabeli
            column: Nazwa kolumny do aktualizacji
            value: Wartość do ustawienia
            where_conditions: Warunki WHERE {kolumna: wartość}

        Returns:
            Liczba zaktualizowanych wierszy

        Raises:
            RuntimeError: Jeśli komponent nie jest połączony
            ValueError: Jeśli where_conditions jest puste
        """
        if not self._is_connected or not self._connection:
            raise RuntimeError(f"Komponent bazodanowy '{self.name}' nie jest połączony")

        if not where_conditions:
            raise ValueError("where_conditions nie może być pusty")

        # Buduj SET i WHERE
        param_index = 1
        values = []

        # Konwertuj wartość SET na string (jeśli to Enum)
        set_value = self._to_db_value_for_column(column, value)
        if hasattr(set_value, "value"):
            set_value = set_value.value  # Pobierz .value z enuma dla asyncpg

        set_clause = f"{column} = ${param_index}"
        values.append(set_value)
        param_index += 1

        where_parts = []
        converted_where = self._convert_where_conditions(where_conditions)
        for col, val in converted_where.items():
            if hasattr(val, "value"):
                val = val.value  # Pobierz .value z enuma dla asyncpg

            where_parts.append(f"{col} = ${param_index}")
            values.append(val)
            param_index += 1

        where_clause = " AND ".join(where_parts)
        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"

        try:
            debug(
                f"✏️ UPDATE w bazie '{self.name}': {query[:100]}{'...' if len(query) > 100 else ''}",
                message_logger=self._message_logger,
            )
            async with self._conn_lock:
                status = await self._connection.execute(query, *values)
            # status ma postać np. 'UPDATE 3'
            try:
                affected = int(status.split()[-1])
            except Exception:
                affected = 0
            return affected
        except Exception as e:
            error(
                f"❌ Błąd UPDATE w bazie '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            raise

    def get_status(self) -> Dict[str, Any]:
        """
        Zwraca status komponentu bazodanowego.

        Returns:
            Słownik ze statusem komponentu
        """
        return {
            "name": self.name,
            "type": "DatabaseComponent",
            "initialized": self._is_initialized,
            "connected": self._is_connected,
            "database_host": self._connection_params.get("host", "unknown"),
            "database_name": self._connection_params.get("database", "unknown"),
            "database_port": self._connection_params.get("port", "unknown"),
            "name": self._connection_params.get("name", "unknown"),
        }
