"""
#### Moduł Event Listener - System Sterowany Zdarzeniami

System komunikacji oparty na zdarzeniach HTTP z serwером FastAPI
i kolejkami przetwarzania zdarzeń dla architektury event-driven.

#### Komponenty:
- `EventListener`: Serwer HTTP FastAPI z kolejkami zdarzeń
- `Event`: Klasa zdarzenia z polami source, destination, event_type, data
- `Result`: Model wyniku operacji
- `EventListenerState`: Enum stanów serwera
- `types`: Submoduł z typami zdarzeń (IoAction, KdsAction, etc.)

#### Przykład użycia:
```python
from avena_commons.event_listener import EventListener, Event, Result

# Serwer zdarzeń
listener = EventListener(name="controller", port=8000)

# Zdarzenie
event = Event(
    source="sensor_01",
    destination="controller",
    event_type="measurement",
    data={"temperature": 23.5}
)

# Wynik operacji
result = Result(result="success", error_code=0)
event.result = result
```

#### Funkcjonalności:
- FastAPI serwer HTTP z endpointami /event, /state, /discovery
- Trzy kolejki zdarzeń: incoming, processing, outgoing
- Asynchroniczne przetwarzanie przez dedykowane wątki
- Automatyczne logowanie i obsługa błędów
"""

from . import types
from .event import Event, Result
from .event_listener import EventListener, EventListenerState

__all__ = ["Event", "Result", "EventListener", "EventListenerState", "types"]
