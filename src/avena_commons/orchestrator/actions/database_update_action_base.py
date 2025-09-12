"""
Generyczna akcja aktualizacji w bazie danych.

Obsługuje dwa warianty:
1) SET stałej wartości w kolumnie: podaj {"column", "value"}
2) Kopia kolumna→kolumna (z rzutowaniem enum gdy trzeba): podaj {"to_column", "from_column"}

WHERE przekazywany wprost z konfiguracji (bez automatycznych filtrów).
"""

from typing import Any, Dict

from avena_commons.util.logger import debug, error, info, warning

from ..models.scenario_models import ScenarioContext
from .base_action import ActionExecutionError, BaseAction


class DatabaseUpdateAction(BaseAction):
    """
    Akcja typu database_update.

    Kopiuje wartość z from_column do to_column dla rekordów spełniających WHERE.
    """

    action_type = "database_update"

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> Dict[str, Any]:
        """
        Aktualizuje dane w bazie: SET stałej wartości lub kopia kolumna→kolumna.

        Args:
            action_config (Dict[str, Any]): Konfiguracja akcji z polami:
                - component (str): Nazwa komponentu DB w orchestratorze.
                - table (str): Tabela do aktualizacji.
                - where (Dict[str, Any]): Warunek WHERE.
                - column (str): Kolumna do ustawienia wartości (wariant 1).
                - value (Any): Wartość do ustawienia (wariant 1).
                - to_column (str): Kolumna docelowa (wariant 2).
                - from_column (str): Kolumna źródłowa (wariant 2).
            context (ScenarioContext): Kontekst wykonania z dostępem do komponentów DB.

        Returns:
            Dict[str, Any]: Podsumowanie liczby zaktualizowanych rekordów i parametrów.

        Raises:
            ActionExecutionError: W przypadku braków konfiguracji lub błędów bazy.
        """
        try:
            component_name = action_config.get("component")
            table = action_config.get("table")
            where = action_config.get("where") or {}

            # Tryb 1: SET stałej wartości (column + value)
            column = action_config.get("column")
            value = action_config.get("value")
            # Tryb 2: Kopia z kolumny (to_column + from_column)
            to_column = action_config.get("to_column")
            from_column = action_config.get("from_column")

            if not component_name:
                raise ActionExecutionError(
                    self.action_type, "Brak 'component' w konfiguracji"
                )
            if not table:
                raise ActionExecutionError(
                    self.action_type, "Brak 'table' w konfiguracji"
                )
            if not isinstance(where, dict):
                raise ActionExecutionError(
                    self.action_type, "Pole 'where' musi być niepustym słownikiem"
                )

            if component_name not in context.components:
                raise ActionExecutionError(
                    self.action_type,
                    f"Komponent bazodanowy '{component_name}' nie jest dostępny",
                )

            db_component = context.components[component_name]

            enhanced_where = dict(where)

            # Wykonaj odpowiedni wariant
            if column is not None and value is not None:
                debug(
                    f"database_update: SET {table}.{column} = {value} WHERE {enhanced_where}",
                    message_logger=context.message_logger,
                )
                affected = await db_component.update_table_value(
                    table=table,
                    column=column,
                    value=value,
                    where_conditions=enhanced_where,
                )
            elif to_column and from_column:
                debug(
                    f"database_update: COPY {table}.{to_column} <- {from_column} WHERE {enhanced_where}",
                    message_logger=context.message_logger,
                )
                affected = await db_component.update_column_from_column(
                    table=table,
                    target_column=to_column,
                    source_column=from_column,
                    where_conditions=enhanced_where,
                )
            else:
                raise ActionExecutionError(
                    self.action_type,
                    "Niepoprawna konfiguracja: podaj (column,value) lub (to_column,from_column)",
                )

            if affected == 0:
                warning(
                    "database_update: Brak zaktualizowanych rekordów (WHERE nie zwrócił wyników)",
                    message_logger=context.message_logger,
                )
            else:
                info(
                    f"database_update: Zaktualizowano {affected} rekordów",
                    message_logger=context.message_logger,
                )

            return {
                "updated_rows": affected,
                "table": table,
                "column": column,
                "value": value,
            }

        except ActionExecutionError:
            raise
        except Exception as e:
            error(
                f"database_update: Błąd wykonania akcji: {e}",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(
                self.action_type, f"Błąd wykonania akcji: {str(e)}", e
            )
