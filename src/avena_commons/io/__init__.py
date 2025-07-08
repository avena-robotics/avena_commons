"""
#### Moduł I/O - Komunikacja Przemysłowa

System zarządzania urządzeniami przemysłowymi z obsługą protokołów komunikacyjnych
i scentralizowanym sterowaniem przez IO_server.

#### Komponenty:
- `bus`: Protokoły EtherCAT, ModbusRTU, ModbusTCP
- `device`: Sterowniki urządzeń (I/O, silniki, sensory)
- `IO_server`: Centralny serwer sterowany zdarzeniami
- `VirtualDevice`: Klasa bazowa dla interfejsów urządzeń
- `VirtualDeviceState`: Enum stanu urządzenia wirtualnego

#### Przykład użycia:
```python
from avena_commons.io import IO_server

server = IO_server(
    name="io_server",
    port=8080,
    configuration_file="config.json"
)
await server.start()
```

#### Konfiguracja JSON:
```json
{
    "bus": {"ethercat": {"class": "EtherCAT"}},
    "device": {"servo1": {"class": "ServoDriver", "bus": "ethercat"}},
    "virtual_device": {
        "feeder": {
            "methods": {"move": {"device": "servo1", "method": "move_absolute"}}
        }
    }
}
```
"""

from . import bus, device
from .io_event_listener import IO_server
from .virtual_device import VirtualDevice, VirtualDeviceState

__all__ = ["bus", "device", "IO_server", "VirtualDevice", "VirtualDeviceState"]
