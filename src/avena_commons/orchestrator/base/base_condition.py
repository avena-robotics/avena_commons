from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from avena_commons.util.logger import MessageLogger


class BaseCondition(ABC):
    """Bazowa klasa dla wszystkich warunków w systemie."""

    def __init__(
        self,
        config: Dict[str, Any],
        message_logger: Optional[MessageLogger] = None,
        condition_factory=None,
    ):
        self.config = config
        self.message_logger = message_logger
        self.condition_factory = condition_factory
        self.condition_type = self.__class__.__name__.replace("Condition", "").lower()

    @abstractmethod
    async def evaluate(self, context: Dict[str, Any]) -> bool:
        """
        Sprawdza czy warunek jest spełniony.

        Args:
            context: Kontekst z orkiestratorem (stan komponentów, baza danych, etc.)

        Returns:
            True jeśli warunek spełniony, False w przeciwnym razie
        """
        pass

    def get_description(self) -> str:
        """Zwraca opis warunku dla logowania."""
        return f"{self.condition_type}: {self.config}"

    def _create_condition(self, condition_config: Dict[str, Any]) -> "BaseCondition":
        """Tworzy warunek na podstawie konfiguracji."""
        if self.condition_factory is None:
            raise RuntimeError(
                "ConditionFactory nie została przekazana do konstruktora"
            )
        return self.condition_factory.create_condition(
            condition_config, self.message_logger
        )
