"""
Enumy pomocnicze używane przez komponenty orchestratora.
"""

from enum import Enum


class CurrentState(Enum):
    """
    Bieżący stan komponentu.

    Wartości:
        INACTIVE: Komponent nieaktywny.
        ACTIVE: Komponent aktywny.
    """

    INACTIVE = "inactive"
    ACTIVE = "active"


class GoalState(Enum):
    """
    Docelowy stan komponentu.

    Wartości:
        INACTIVE: Oczekiwany stan nieaktywny.
        ACTIVE: Oczekiwany stan aktywny.
    """

    INACTIVE = "inactive"
    ACTIVE = "active"
