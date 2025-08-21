"""
#### Moduł Event Listener - System Sterowany Zdarzeniami z FSM

System komunikacji oparty na zdarzeniach HTTP z serwером FastAPI,
Finite State Machine (FSM) i kolejkami przetwarzania zdarzeń.

#### Komponenty:
- `EventListener`: Serwer HTTP FastAPI z FSM i kolejkami zdarzeń
- `Event`: Klasa zdarzenia z polami source, destination, event_type, data
- `Result`: Model wyniku operacji
- `EventListenerState`: Enum stanów FSM (STOPPED, INITIALIZED, RUN, PAUSE, FAULT)
- `types`: Submoduł z typami zdarzeń (IoAction, KdsAction, etc.)

#### Przykład użycia z FSM:
```python
from avena_commons.event_listener import EventListener, Event, Result

# Serwer zdarzeń z FSM
listener = EventListener(name="controller", port=8000)
listener.start()  # Uruchamia w stanie STOPPED

# Komendy sterujące FSM
await listener._event(
    destination="controller",
    event_type="CMD_INITIALIZED"  # STOPPED → INITIALIZED
)
await listener._event(
    destination="controller",
    event_type="CMD_RUN"  # INITIALIZED → RUN
)
```

#### Rozszerzanie EventListener z FSM:
```python
class MyEventListener(EventListener):
    # Callback'i FSM (wszystkie opcjonalne)
    async def on_initialize(self):
        self.database = await connect_to_db()

    async def on_run(self):
        # local_check_thread już uruchomiony automatycznie
        self.background_task = asyncio.create_task(self.work())

    async def on_pausing(self):
        # local_check_thread zatrzymany automatycznie
        self.background_task.cancel()

    # Logika biznesowa (działa tylko w RUN)
    async def _analyze_event(self, event: Event) -> bool:
        match event.event_type:
            case "my_custom_event":
                await self._handle_custom_event(event)
                return True
            case _:
                return True

    async def _check_local_data(self):
        # Wywoływane tylko w stanie RUN
        self._state["current_errors"] = self._get_current_errors()
        self._state["robot_state"] = self._get_robot_state()
```

#### Funkcjonalności FSM:
- **Stany główne**: STOPPED, INITIALIZED, RUN, PAUSE, FAULT
- **Komendy sterujące**: CMD_INITIALIZED, CMD_RUN, CMD_PAUSE, CMD_STOPPED, CMD_ACK
- **Automatyczne zarządzanie wątkami**: local_check_thread tylko w RUN
- **Wzorce przetwarzania**: pełne w RUN, buffering w PAUSE, error w FAULT/STOPPED
- **Obsługa błędów**: automatyczne przejście do FAULT, wymaga CMD_ACK
- **Callback'i**: puste w klasie bazowej, do przedefiniowania w potomnych

#### Funkcjonalności podstawowe:
- FastAPI serwer HTTP z endpointami /event, /state, /discovery
- Trzy kolejki zdarzeń: incoming, processing, outgoing
- Asynchroniczne przetwarzanie przez dedykowane wątki
- Automatyczne logowanie i obsługa błędów
- Trwałe przechowywanie kolejek i stanu w pliku JSON
"""

from . import types
from .event import Event, Result
from .event_listener import EventListener, EventListenerState

__all__ = ["Event", "Result", "EventListener", "EventListenerState", "types"]
