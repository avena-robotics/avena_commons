"""Moduł PepperCamera do obsługi kamery dedykowanej dla papryczek.

Odpowiedzialność:
- Uproszczona obsługa kamery bez QR/box detection
- Fragmentacja obrazów na 4 części
- Serializacja fragmentów do przesłania do Pepper EventListener
- Integracja z istniejącym systemem pepper vision

Eksponuje:
- Klasa `PepperCamera` (główny event listener pepper camera)
"""

from .pepper_camera import PepperCamera
from .driver.pepper_camera_connector import PepperCameraConnector, PepperCameraWorker

__all__ = [
    "PepperCamera",
    "PepperCameraConnector", 
    "PepperCameraWorker",
]
