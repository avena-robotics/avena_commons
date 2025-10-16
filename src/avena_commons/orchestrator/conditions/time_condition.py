from datetime import datetime, time
from typing import Any, Dict

from ..base.base_condition import BaseCondition
from ..models.scenario_models import ScenarioContext


class TimeCondition(BaseCondition):
    """Sprawdza warunki czasowe."""

    async def evaluate(self, context: ScenarioContext) -> bool:
        """
        Ewaluacja warunków czasowych względem bieżącego czasu.

        Obsługuje klucze w konfiguracji:
        - time_range: {"start": "HH:MM", "end": "HH:MM"} (obsługa zakresu przez północ)
        - weekdays: Lista nazw dni tygodnia (lowercase, np. "monday")
        - specific_date: ISO-8601 data (YYYY-MM-DD lub pełna z czasem)

        Args:
            context (ScenarioContext): Nieużywany (zachowany dla spójności interfejsu).

        Returns:
            bool: True, jeśli spełniono przynajmniej jeden z warunków.

        Examples:
            >>> cond = TimeCondition({"time_range": {"start": "08:00", "end": "16:00"}})
            >>> await cond.evaluate({})
            True  # w godzinach pracy
        """
        current_time = datetime.now()

        # Sprawdź przedział czasowy
        time_range = self.config.get("time_range")
        if time_range:
            try:
                start_time = time.fromisoformat(time_range.get("start", "00:00"))
                end_time = time.fromisoformat(time_range.get("end", "23:59"))
                current_time_only = current_time.time()

                if start_time <= end_time:
                    return start_time <= current_time_only <= end_time
                else:  # Przechodzi przez północ
                    return (
                        current_time_only >= start_time or current_time_only <= end_time
                    )
            except ValueError as e:
                if self.message_logger:
                    self.message_logger.error(f"TimeCondition: błąd formatu czasu: {e}")
                return False

        # Sprawdź dzień tygodnia
        weekdays = self.config.get("weekdays", [])
        if weekdays:
            current_weekday = current_time.strftime("%A").lower()
            return current_weekday in weekdays

        # Sprawdź datę
        specific_date = self.config.get("specific_date")
        if specific_date:
            try:
                target_date = datetime.fromisoformat(specific_date).date()
                return current_time.date() == target_date
            except ValueError as e:
                if self.message_logger:
                    self.message_logger.error(f"TimeCondition: błąd formatu daty: {e}")
                return False

        return False
