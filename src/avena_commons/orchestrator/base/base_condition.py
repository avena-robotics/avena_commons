from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from avena_commons.util.logger import MessageLogger


class BaseCondition(ABC):
    """
    Bazowa klasa dla wszystkich warunków w systemie.

    Klasy pochodne muszą zaimplementować metodę asynchroniczną `evaluate`.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        message_logger: Optional[MessageLogger] = None,
        condition_factory=None,
    ):
        """
        Inicjalizuje warunek bazowy.

        Args:
            config (Dict[str, Any]): Konfiguracja warunku (specyficzna dla implementacji).
            message_logger (MessageLogger | None): Logger wiadomości dla debugowania.
            condition_factory (ConditionFactory | None): Fabryka do tworzenia warunków zagnieżdżonych.
        """
        self.config = config
        self.message_logger = message_logger
        self.condition_factory = condition_factory
        self.condition_type = self.__class__.__name__.replace("Condition", "").lower()
        self.context: Dict[str, Any] = {}

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
        """
        Zwraca zwięzły opis warunku do celów logowania.

        Returns:
            str: Opis zawierający typ warunku i jego konfigurację.
        """
        return f"{self.condition_type}: {self.config}"

    def _create_condition(self, condition_config: Dict[str, Any]) -> "BaseCondition":
        """
        Tworzy instancję warunku (zagnieżdżonego) na podstawie konfiguracji.

        Args:
            condition_config (Dict[str, Any]): Konfiguracja pojedynczego warunku.

        Returns:
            BaseCondition: Utworzona instancja warunku.

        Raises:
            RuntimeError: Gdy fabryka warunków nie została przekazana do konstruktora.
        """
        if self.condition_factory is None:
            raise RuntimeError(
                "ConditionFactory nie została przekazana do konstruktora"
            )
        return self.condition_factory.create_condition(
            condition_config, self.message_logger
        )
