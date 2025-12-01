"""
Moduł detekcji obiektów wizyjnych
"""

from .box_detector import box_detector
from .qr_detector import qr_detector

__all__ = ["box_detector", "qr_detector"]
