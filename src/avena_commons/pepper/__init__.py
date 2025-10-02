"""Moduł Pepper Vision Processing System.

Odpowiedzialność:
- PepperWorker: Proces roboczy wykonujący pepper vision na dedykowanym core
- PepperConnector: Zarządza worker process, komunikacja przez pipe
- Pepper: EventListener interfejs główny dla pepper vision

Eksponuje:
- Klasa `Pepper` (główny event listener pepper vision)
- Klasa `PepperConnector` (connector do pepper worker)
"""

from .pepper import Pepper
from .driver.pepper_connector import PepperConnector

__all__ = ["Pepper", "PepperConnector"]
