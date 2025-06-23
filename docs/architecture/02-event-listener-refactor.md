### **Dokumentacja Zmian: `EventListener` dla Zgodności z Orchestratorem**

#### **1. Cel**

Celem jest adaptacja bazowej klasy `EventListener` tak, aby w pełni implementowała maszynę stanów (FSM) oraz cykl życia zdefiniowany w dokumencie `ORCHESTRATOR_CONCEPT.md`. Po wprowadzeniu tych zmian, każdy komponent dziedziczący po `EventListener` będzie mógł być bezproblemowo zarządzany przez Orchestrator.

#### **2. Kluczowe Zmiany**

Zmiany koncentrują się w trzech głównych obszarach:
1.  Ujednolicenie definicji stanów (FSM).
2.  Implementacja logiki do obsługi komend sterujących cyklem życia.
3.  Wprowadzenie dedykowanych metod-haków (hooks) dla logiki specyficznej dla komponentu.

---

#### **2.1. Aktualizacja Maszyny Stanów (FSM)**

Obecna definicja stanów w `event_listener.py` nie jest w pełni zgodna z finalną koncepcją. Należy ją ujednolicić.

**Obecna definicja w `EventListenerState`:**
```python
class EventListenerState(Enum):
    STOPPED = 0
    INITIALIZING = 1
    INITIALIZED = 2
    STARTING = 3
    STARTED = 4
    STOPPING = 5
    ERROR = 256
```

**Proponowana, zgodna z koncepcją, definicja:**
```python
class EventListenerState(Enum):
    READY = 0           # Zastępuje STOPPED jako stan początkowy po rejestracji
    INITIALIZING = 1    # Bez zmian
    INIT_COMPLETE = 2   # Bardziej precyzyjna nazwa niż INITIALIZED
    STARTED = 3         # Zastępuje STARTING i STARTED
    STOPPING = 4        # Bez zmian
    STOPPED = 5         # Stan pasywny po zatrzymaniu
    FAULT = 6           # Zastępuje ERROR
```
*Nowy atrybut w klasie* `EventListener` będzie przechowywał aktualny stan, np. `self.__fsm_state: EventListenerState = EventListenerState.READY`.

---

#### **2.2. Implementacja Cyklu Życia i Obsługi Komend**

`EventListener` musi reagować na komendy od Orchestratora (`CMD_*`) i zarządzać swoim stanem. Osiągniemy to poprzez rozbudowę metody `_analyze_event` oraz wprowadzenie nowych metod.

##### **A. Metody-Haki (Lifecycle Hooks) do Nadpisania**

Należy dodać do klasy `EventListener` nowe, puste metody `async`, które będą nadpisywane przez konkretne implementacje komponentów (`Kiosk`, `IO`, `MunchiesAlgo` etc.). To w nich będzie zawarta właściwa logika biznesowa.

```python
# Do dodania w klasie EventListener

async def _on_initialize(self):
    """Metoda wywoływana podczas przejścia w stan INITIALIZING. 
    Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
    pass

async def _on_start(self):
    """Metoda wywoływana podczas przejścia w stan STARTED.
    Tu komponent rozpoczyna swoje główne zadania operacyjne."""
    pass

async def _on_stop(self):
    """Metoda wywoływana podczas przejścia w stan STOPPING.
    Tu komponent finalizuje bieżące zadania przed zatrzymaniem."""
    pass

async def _on_reset(self):
    """Metoda wywoływana po otrzymaniu komendy resetu ze stanu FAULT."""
    pass
```

##### **B. Logika Obsługi Komend**

Metoda `__analyze_incoming_events` (lub `_analyze_event`) musi zostać rozszerzona o logikę obsługi komend sterujących.

```python
# Szkic logiki w __analyze_incoming_events

async def __analyze_incoming_events(self):
    # ... istniejąca pętla po eventach ...
    match event.event_type:
        # ... istniejące case'y ...

        case "CMD_INITIALIZE":
            await self._handle_initialize_command(event)
        
        case "CMD_START":
            await self._handle_start_command(event)

        case "CMD_GRACEFUL_STOP":
            await self._handle_stop_command(event)

        case "CMD_RESET":
            await self._handle_reset_command(event)

        case _:
            should_remove = await self._analyze_event(event)

```

##### **C. Implementacja Logiki Przejść Stanów**

Należy dodać nowe, wewnętrzne metody (`_handle_*`), które będą zarządzać FSM.

1.  **Inicjalizacja (`_handle_initialize_command`)**
    *   **Warunek:** `self.__fsm_state` musi być `READY`.
    *   **Akcja:**
        1.  Zmień stan: `self.__fsm_state = EventListenerState.INITIALIZING`.
        2.  Wywołaj `await self._on_initialize()` w bloku `try...except`.
        3.  **Po sukcesie:**
            *   Zmień stan: `self.__fsm_state = EventListenerState.INIT_COMPLETE`.
            *   Wyślij do Orchestratora `EVENT_INIT_SUCCESS`.
        4.  **Po porażce (wyjątek w `_on_initialize`):**
            *   Zmień stan: `self.__fsm_state = EventListenerState.FAULT`.
            *   Wyślij do Orchestratora `EVENT_INIT_FAILURE` z informacją o błędzie.

2.  **Start (`_handle_start_command`)**
    *   **Warunek:** `self.__fsm_state` musi być `INIT_COMPLETE`.
    *   **Akcja:**
        1.  Zmień stan: `self.__fsm_state = EventListenerState.STARTED`.
        2.  Wywołaj `await self._on_start()`.
        3.  Wyślij do Orchestratora `EVENT_START_SUCCESS`.

3.  **Zatrzymanie (`_handle_stop_command`)**
    *   **Warunek:** `self.__fsm_state` musi być `STARTED`.
    *   **Akcja:**
        1.  Zmień stan: `self.__fsm_state = EventListenerState.STOPPING`.
        2.  Wywołaj `await self._on_stop()` w bloku `try...except`.
        3.  **Po sukcesie:**
            *   Zmień stan: `self.__fsm_state = EventListenerState.STOPPED`.
            *   Wyślij do Orchestratora `EVENT_STOP_SUCCESS`.
        4.  **Po porażce:**
            *   Zmień stan: `self.__fsm_state = EventListenerState.FAULT`.
            *   Wyślij `EVENT_STOP_FAILURE`.

4.  **Reset (`_handle_reset_command`)**
    *   **Warunek:** `self.__fsm_state` musi być `FAULT`.
    *   **Akcja:**
        1.  Wywołaj `await self._on_reset()`.
        2.  Zmień stan: `self.__fsm_state = EventListenerState.READY`.
        3.  Wyślij `EVENT_RESET_SUCCESS`.

---

#### **3. Podsumowanie**

Wprowadzenie powyższych zmian w klasie `EventListener` zapewni:
*   **Pełną zgodność** z cyklem życia zdefiniowanym w koncepcji Orchestratora.
*   **Hermetyzację logiki FSM** w klasie bazowej, co upraszcza implementację komponentów potomnych.
*   **Przejrzysty interfejs** w postaci metod-haków (`_on_initialize`, `_on_start` itd.) dla programistów tworzących konkretne komponenty.

Ten refaktoring jest fundamentem, który umożliwi budowę stabilnego i łatwego w zarządzaniu systemu rozproszonego. 