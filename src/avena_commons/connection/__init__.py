"""
#### Moduł Connection - Komunikacja Międzyprocesowa

System komunikacji międzyprocesowej wykorzystujący pamięć współdzieloną POSIX
z synchronizacją semaforami dla wysokowydajnej wymiany danych.

#### Komponenty:
- `AvenaComm`: Główna klasa komunikacyjna z pamięcią współdzieloną POSIX

#### Przykład użycia:
```python
from avena_commons.connection import AvenaComm

# Proces nadawczy
sender = AvenaComm(
    comm_name="sensor_data",
    shm_size=4096,
    data={"temperature": 23.5}
)
sender.save_and_unlock(data)

# Proces odbiorczy
receiver = AvenaComm(comm_name="sensor_data")
success, data = receiver.lock_and_read()
```

#### Funkcjonalności:
- Pamięć współdzielona POSIX z synchronizacją semaforami
- Automatyczna serializacja danych przez pickle
- Thread-safe operacje z konfigurowalnymi timeout'ami
- Monitorowanie błędów i statystyk komunikacji
"""

from .shm import AvenaComm

__all__ = ["AvenaComm"]
