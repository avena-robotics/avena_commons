"""
#### Moduł Config - Zarządzanie Konfiguracją Systemu

Scentralizowane zarządzanie konfiguracją z automatyczną walidacją
i bezpiecznym dostępem do plików konfiguracyjnych.

#### Komponenty:
- `Config`: Klasa bazowa do zarządzania plikami konfiguracyjnymi
- `ControllerConfig`: Wyspecjalizowana konfiguracja dla kontrolerów

#### Przykład użycia:
```python
from avena_commons.config import Config, ControllerConfig

# Podstawowa konfiguracja
config = Config("app_settings.conf", read_only=True)
config.read_from_file()

# Konfiguracja kontrolera z automatyczną konwersją typów
controller_config = ControllerConfig("controller.conf")
max_velocity = controller_config.get("MAX_VELOCITY")  # float
servo_count = controller_config.get("SERVO_COUNT")    # int
```

#### Funkcjonalności:
- Tryby tylko do odczytu i odczyt-zapis
- Automatyczna konwersja typów (int, float, string)
- Interpolacja zmiennych %(zmienna)s
- Walidacja i bezpieczne zapisywanie
- Wbudowane wartości domyślne dla kontrolerów
"""

from .common import Config
from .controller import ControllerConfig

__all__ = ["Config", "ControllerConfig"]
