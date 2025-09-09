"""
Moduł komponentów orchestratora.

Komponenty to zewnętrzne systemy (bazy danych, API), które są inicjalizowane
przy starcie orchestratora i udostępniane warunkom.
"""

from .database_component import DatabaseComponent
from .lynx_api_component import LynxAPIComponent

__all__ = ["DatabaseComponent", "LynxAPIComponent"]
