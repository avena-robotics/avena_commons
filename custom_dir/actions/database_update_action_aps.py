"""
Wariant akcji database_update z automatycznym dodaniem filtrów APS do WHERE.
"""

from typing import Any, Dict

from avena_commons.orchestrator.actions import DatabaseUpdateAction
from avena_commons.util.logger import debug


class ApsDatabaseUpdateAction(DatabaseUpdateAction):
    action_type = "aps_database_update"

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        cfg = dict(action_config)
        component_name = cfg.get("component")
        if not component_name:
            raise ActionExecutionError(
                self.action_type, "Brak 'component' w konfiguracji"
            )

        orch = context.orchestrator
        db = getattr(orch, "_components", {}).get(component_name)
        if db is None:
            raise ActionExecutionError(
                self.action_type,
                f"Komponent bazodanowy '{component_name}' nie jest dostępny",
            )

        where = dict(cfg.get("where") or {})
        aps_id = db.config.get("APS_ID")
        aps_name = db.config.get("APS_NAME")
        if aps_id is not None:
            where["id"] = aps_id
            debug(
                f"aps_database_update: dodano filtr id={aps_id}",
                message_logger=context.message_logger,
            )
        if aps_name is not None:
            where["name"] = aps_name
            debug(
                f"aps_database_update: dodano filtr name={aps_name}",
                message_logger=context.message_logger,
            )
        cfg["where"] = where

        # Deleguj do implementacji bazowej (generycznej)
        return await super().execute(cfg, context)
