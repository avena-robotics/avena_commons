from ..base.base_condition import BaseCondition
from ..models.scenario_models import ScenarioContext


class LogicNorCondition(BaseCondition):
    """Warunek logiczny NOR - żaden warunek nie może być spełniony."""

    async def evaluate(self, context: ScenarioContext) -> bool:
        """
        Zwraca True, jeśli żaden zagnieżdżony warunek nie jest spełniony.

        Args:
            context (ScenarioContext): Kontekst ewaluacji przekazywany do pod-warunków.

        Returns:
            bool: Wynik NOR warunków.
        """
        conditions_config = self.config.get("conditions", [])
        if not conditions_config:
            if self.message_logger:
                self.message_logger.debug(
                    "LogicNorCondition: pusta lista warunków, zwracam True"
                )
            return True

        # Sprawdź czy żaden warunek nie jest spełniony
        for i, condition_config in enumerate(conditions_config):
            try:
                condition = self._create_condition(condition_config)
                result = await condition.evaluate(context)
                if result:
                    if self.message_logger:
                        self.message_logger.debug(
                            f"LogicNorCondition: warunek {i} spełniony, NOR = False"
                        )
                    return False  # Jeśli jeden warunek spełniony, NOR = False
            except Exception as e:
                if self.message_logger:
                    self.message_logger.error(
                        f"LogicNorCondition: błąd w warunku {i}: {e}"
                    )
                continue

        if self.message_logger:
            self.message_logger.debug(
                "LogicNorCondition: żaden warunek nie spełniony, NOR = True"
            )
        return True  # Żaden warunek nie spełniony
