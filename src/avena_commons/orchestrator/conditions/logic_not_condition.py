from typing import Any, Dict

from ..base.base_condition import BaseCondition


class LogicNotCondition(BaseCondition):
    """Warunek logiczny NOT - neguje wynik warunku."""

    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Zwraca negację wyniku zagnieżdżonego warunku.

        Args:
            context (Dict[str, Any]): Kontekst ewaluacji przekazywany do pod-warunku.

        Returns:
            bool: Zanegowany wynik warunku.
        """
        condition_config = self.config.get("condition")
        if not condition_config:
            if self.message_logger:
                self.message_logger.warning(
                    "LogicNotCondition: brak konfiguracji warunku"
                )
            return True

        try:
            condition = self._create_condition(condition_config)
            result = await condition.evaluate(context)
            negated_result = not result
            if self.message_logger:
                self.message_logger.debug(
                    f"LogicNotCondition: oryginalny wynik: {result}, zanegowany: {negated_result}"
                )
            return negated_result  # Neguj wynik
        except Exception as e:
            if self.message_logger:
                self.message_logger.error(f"LogicNotCondition: błąd: {e}")
            return False
