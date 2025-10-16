from typing import Any, Dict

from ..base.base_condition import BaseCondition
from ..models.scenario_models import ScenarioContext


class LogicNandCondition(BaseCondition):
    """Warunek logiczny NAND - nie wszystkie warunki mogą być spełnione."""

    async def evaluate(self, context: ScenarioContext) -> bool:
        conditions_config = self.config.get("conditions", [])
        if not conditions_config:
            if self.message_logger:
                self.message_logger.debug(
                    "LogicNandCondition: pusta lista warunków, zwracam True"
                )
            return True

        # Sprawdź czy wszystkie warunki są spełnione
        all_true = True
        for i, condition_config in enumerate(conditions_config):
            try:
                condition = self._create_condition(condition_config)
                result = await condition.evaluate(context)
                if not result:
                    all_true = False
                    if self.message_logger:
                        self.message_logger.debug(
                            f"LogicNandCondition: warunek {i} nie spełniony, NAND = True"
                        )
                    break  # Jeśli jeden nie spełniony, nie musimy sprawdzać dalej
            except Exception as e:
                if self.message_logger:
                    self.message_logger.error(
                        f"LogicNandCondition: błąd w warunku {i}: {e}"
                    )
                all_true = False
                break

        final_result = not all_true  # NAND = NOT(AND)
        if self.message_logger:
            self.message_logger.debug(
                f"LogicNandCondition: wszystkie spełnione: {all_true}, wynik: {final_result}"
            )
        return final_result
