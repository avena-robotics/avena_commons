"""
Akcja aktualizacji rekordu w bazie danych na podstawie warunku.

Cel: Skopiować wartość z kolumny źródłowej (np. goal_state) do kolumny
docelowej (np. current_state) dla wierszy wskazanych przez warunek WHERE.

Domyślne kolumny: source=goal_state, target=current_state.

Przykład użycia w scenariuszu (na końcu, po sukcesie):
{
  "type": "database_update",
  "component": "main_database",
  "table": "aps_description",
  "from_column": "goal_state",
  "to_column": "current_state",
  "where": {
    "current_state": "inactive"
  }
}

Uwaga: Akcja automatycznie doda filtry identyfikujące APS (id, name)
na podstawie APS_ID/APS_NAME z konfiguracji komponentu (jeśli dostępne).
"""

from typing import Any, Dict

from avena_commons.util.logger import debug, error, info, warning

from .base_action import ActionContext, ActionExecutionError, BaseAction


class DatabaseUpdateAction(BaseAction):
    """
    Akcja typu database_update.

    Kopiuje wartość z from_column do to_column dla rekordów spełniających WHERE.
    """

    action_type = "database_update"

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        try:
            component_name = action_config.get("component")
            table = action_config.get("table")
            where = action_config.get("where") or {}

            # Domyślne kolumny: goal_state -> current_state
            column = action_config.get("column", "")
            value = action_config.get("value", None)

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

            # Pobierz komponent DB z orchestratora
            orchestrator = context.orchestrator
            components = getattr(orchestrator, "_components", {})
            if component_name not in components:
                raise ActionExecutionError(
                    self.action_type,
                    f"Komponent bazodanowy '{component_name}' nie jest dostępny",
                )

            db_component = components[component_name]

            # Rozszerz WHERE o identyfikatory APS, jeśli dostępne w konfiguracji komponentu
            enhanced_where = dict(where)
            aps_id = db_component.config.get("APS_ID")
            aps_name = db_component.config.get("APS_NAME")
            if aps_id is not None:
                enhanced_where["id"] = aps_id
                debug(
                    f"database_update: dodano filtr id={aps_id}",
                    message_logger=context.message_logger,
                )
            if aps_name is not None:
                enhanced_where["name"] = aps_name
                debug(
                    f"database_update: dodano filtr name={aps_name}",
                    message_logger=context.message_logger,
                )

            debug(
                f"database_update: {table}.{column} = {value} WHERE {enhanced_where}",
                message_logger=context.message_logger,
            )

            # Wykonaj aktualizację
            affected = await db_component.update_table_value(
                table=table,
                column=column,
                value=value,
                where_conditions=enhanced_where,
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
