"""
Moduł komponentów orchestratora.

Komponenty to zewnętrzne systemy (bazy danych), które są inicjalizowane
przy starcie orchestratora i udostępniane warunkom.
"""

from .database_component import DatabaseComponent

__all__ = ["DatabaseComponent"]
