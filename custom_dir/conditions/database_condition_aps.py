"""
Wariant warunku bazodanowego rozszerzający WHERE o filtry APS (id, name).
"""

from typing import Any, Dict

from avena_commons.orchestrator.conditions import DatabaseCondition
from avena_commons.util.logger import debug


class ApsDatabaseCondition(DatabaseCondition):
    """
    Klasa pochodna, która automatycznie dodaje do WHERE identyfikatory APS
    (APS_ID -> id, APS_NAME -> name) na podstawie konfiguracji komponentu DB.
    """

    def _augment_where(self, where: Dict[str, Any], db_component) -> Dict[str, Any]:
        enhanced = dict(where)
        aps_id = db_component.config.get("APS_ID")
        aps_name = db_component.config.get("APS_NAME")
        if aps_id is not None:
            enhanced["id"] = aps_id
            debug(
                f"🔧 APS: dodano filtr id={aps_id}",
                message_logger=self._message_logger,
            )
        if aps_name is not None:
            enhanced["name"] = aps_name
            debug(
                f"🔧 APS: dodano filtr name={aps_name}",
                message_logger=self._message_logger,
            )
        return enhanced
