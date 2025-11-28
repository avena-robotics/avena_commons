from ..base.base_condition import BaseCondition
from ..models.scenario_models import ScenarioContext


class LogicAndCondition(BaseCondition):
    """Warunek logiczny AND - wszystkie warunki muszą być spełnione."""

    async def evaluate(self, context: ScenarioContext) -> bool:
        """
        Zwraca True, jeśli wszystkie zagnieżdżone warunki są spełnione.

        Args:
            context (ScenarioContext): Kontekst ewaluacji przekazywany do pod-warunków.

        Returns:
            bool: Wynik koniunkcji warunków (AND).
        """
        conditions_config = self.config.get("conditions", [])
        if not conditions_config:
            if self.message_logger:
                self.message_logger.debug(
                    "LogicAndCondition: pusta lista warunków, zwracam True"
                )
            return True

        # Rekurencyjnie sprawdź wszystkie warunki
        for i, condition_config in enumerate(conditions_config):
            try:
                condition = self._create_condition(condition_config)
                result = await condition.evaluate(context)
                if not result:
                    if self.message_logger:
                        self.message_logger.debug(
                            f"LogicAndCondition: warunek {i} nie spełniony"
                        )
                    return False  # Jeśli jeden warunek nie spełniony, całość False
            except Exception as e:
                if self.message_logger:
                    self.message_logger.error(
                        f"LogicAndCondition: błąd w warunku {i}: {e}"
                    )
                return False

        if self.message_logger:
            self.message_logger.debug("LogicAndCondition: wszystkie warunki spełnione")
        return True  # Wszystkie warunki spełnione
