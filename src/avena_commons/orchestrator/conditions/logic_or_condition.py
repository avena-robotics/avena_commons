from typing import Any, Dict

from ..base.base_condition import BaseCondition


class LogicOrCondition(BaseCondition):
    """Warunek logiczny OR - przynajmniej jeden warunek musi być spełniony."""

    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Zwraca True, jeśli co najmniej jeden zagnieżdżony warunek jest spełniony.

        Args:
            context (Dict[str, Any]): Kontekst ewaluacji przekazywany do pod-warunków.

        Returns:
            bool: Wynik alternatywy warunków (OR).
        """
        conditions_config = self.config.get("conditions", [])
        if not conditions_config:
            if self.message_logger:
                self.message_logger.debug(
                    "LogicOrCondition: pusta lista warunków, zwracam True"
                )
            return True

        # Sprawdź czy przynajmniej jeden warunek jest spełniony
        for i, condition_config in enumerate(conditions_config):
            try:
                condition = self._create_condition(condition_config)
                result = await condition.evaluate(context)
                if result:
                    if self.message_logger:
                        self.message_logger.debug(
                            f"LogicOrCondition: warunek {i} spełniony"
                        )
                    return True  # Jeśli jeden warunek spełniony, całość True
            except Exception as e:
                if self.message_logger:
                    self.message_logger.error(
                        f"LogicOrCondition: błąd w warunku {i}: {e}"
                    )
                continue  # Przejdź do następnego warunku

        if self.message_logger:
            self.message_logger.debug("LogicOrCondition: żaden warunek nie spełniony")
        return False  # Żaden warunek nie spełniony
