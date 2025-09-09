from typing import Any, Dict, List

from ..base.base_condition import BaseCondition
from ..conditions.client_state_condition import ClientStateCondition
from ..conditions.error_message_condition import ErrorMessageCondition
from ..conditions.logic_and_condition import LogicAndCondition
from ..conditions.logic_nand_condition import LogicNandCondition
from ..conditions.logic_nor_condition import LogicNorCondition
from ..conditions.logic_not_condition import LogicNotCondition
from ..conditions.logic_or_condition import LogicOrCondition
from ..conditions.logic_xor_condition import LogicXorCondition
from ..conditions.time_condition import TimeCondition


class ConditionFactory:
    """
    Fabryka tworząca odpowiednie warunki na podstawie konfiguracji.

    Utrzymuje rejestr mapujący nazwy typów na klasy warunków i dostarcza
    metody do tworzenia oraz rejestrowania nowych typów.
    """

    _condition_types = {
        # Aliasy dla wygody (domyślne)
        "and": LogicAndCondition,
        "or": LogicOrCondition,
        "not": LogicNotCondition,
        "xor": LogicXorCondition,
        "nand": LogicNandCondition,
        "nor": LogicNorCondition,
        "client_state": ClientStateCondition,
        "time": TimeCondition,
        "error_message": ErrorMessageCondition,
    }

    @classmethod
    def create_condition(
        cls, condition_config: Dict[str, Any], message_logger=None
    ) -> BaseCondition:
        """
        Tworzy instancję warunku na podstawie konfiguracji.

        Args:
            condition_config (Dict[str, Any]): Słownik z pojedynczym kluczem będącym
                nazwą typu warunku i wartością konfiguracji, np. {"and": {...}}.
            message_logger: Opcjonalny logger przekazywany do warunku.

        Returns:
            BaseCondition: Utworzona instancja warunku.

        Raises:
            ValueError: Gdy typ warunku nie jest zarejestrowany.
        """
        # Sprawdź czy pierwszy klucz to nazwa klasy
        condition_class_name = next(iter(condition_config.keys()))

        if condition_class_name not in cls._condition_types:
            raise ValueError(f"Nieznany typ warunku: {condition_class_name}")

        condition_class = cls._condition_types[condition_class_name]
        # Przekaż fabrykę do konstruktora warunku
        return condition_class(
            condition_config[condition_class_name], message_logger, cls
        )

    @classmethod
    def register_condition_type(cls, name: str, condition_class: type):
        """
        Rejestruje nowy typ warunku w fabryce.

        Args:
            name (str): Nazwa typu (klucz konfiguracji).
            condition_class (type): Klasa implementująca `BaseCondition`.
        """
        cls._condition_types[name] = condition_class

    @classmethod
    def get_registered_conditions(cls) -> List[str]:
        """
        Zwraca listę zarejestrowanych typów warunków.

        Returns:
            List[str]: Posortowana alfabetycznie lista kluczy typów.
        """
        return list(cls._condition_types.keys())
