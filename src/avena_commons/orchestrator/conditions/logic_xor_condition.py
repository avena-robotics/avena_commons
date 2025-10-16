from typing import Any, Dict

from ..base.base_condition import BaseCondition
from ..models.scenario_models import ScenarioContext


class LogicXorCondition(BaseCondition):
    """Warunek logiczny XOR - dokładnie jeden warunek musi być spełniony."""

    async def evaluate(self, context: ScenarioContext) -> bool:
        """
        Zwraca True, jeśli dokładnie jeden zagnieżdżony warunek jest spełniony.

        Args:
            context (ScenarioContext): Kontekst ewaluacji przekazywany do pod-warunków.

        Returns:
            bool: Wynik XOR warunków.
        """
        conditions_config = self.config.get("conditions", [])
        if not conditions_config:
            if self.message_logger:
                self.message_logger.debug(
                    "LogicXorCondition: pusta lista warunków, zwracam True"
                )
            return True

        true_count = 0

        # Policz ile warunków jest spełnionych
        for i, condition_config in enumerate(conditions_config):
            try:
                condition = self._create_condition(condition_config)
                result = await condition.evaluate(context)
                if result:
                    true_count += 1
                    if self.message_logger:
                        self.message_logger.debug(
                            f"LogicXorCondition: warunek {i} spełniony (łącznie: {true_count})"
                        )
            except Exception as e:
                if self.message_logger:
                    self.message_logger.error(
                        f"LogicXorCondition: błąd w warunku {i}: {e}"
                    )
                continue

        final_result = true_count == 1
        if self.message_logger:
            self.message_logger.debug(
                f"LogicXorCondition: {true_count} warunków spełnionych, wynik: {final_result}"
            )
        return final_result  # Dokładnie jeden warunek spełniony
