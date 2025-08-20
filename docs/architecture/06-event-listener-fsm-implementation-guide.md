# EventListener FSM - System Stanów i Obsługa Zdarzeń

## 1. Przegląd Systemu

EventListener implementuje Finite State Machine (FSM) zarządzający cyklem życia usługi.

### Struktura Stanów

```python
class EventListenerState(Enum):
    # Stany główne
    UNKNOWN = -1      # Stan początkowy (automatyczne przejście)
    STOPPED = 0       # Stan pasywny - zasoby zwolnione
    INITIALIZED = 2   # Stan buforowy z zasobami - gotowy do uruchomienia
    RUN = 4           # Stan operacyjny - pełna funkcjonalność
    PAUSE = 8         # Stan buforujący - wstrzymane operacje
    FAULT = 10        # Stan błędu wymagający potwierdzenia operatora
    ON_ERROR = 11     # Trigger błędu (automatyczne przejście)
    
    # Stany przejściowe
    INITIALIZING = 1  # STOPPED → INITIALIZED
    STARTING = 3      # INITIALIZED → RUN  
    PAUSING = 6       # RUN → PAUSE
    RESUMING = 7      # PAUSE → RUN
    SOFT_STOPPING = 5 # RUN → INITIALIZED
    HARD_STOPPING = 9 # PAUSE → STOPPED
```

## 2. Komendy Sterujące FSM

System zarządzany jest 5 komendami:

- **CMD_INITIALIZED** - przejście do stanu INITIALIZED
  - `STOPPED` → INITIALIZING → INITIALIZED (inicjalizacja)
  - `RUN` → SOFT_STOPPING → INITIALIZED (graceful shutdown)

- **CMD_RUN** - przejście do stanu RUN  
  - `INITIALIZED` → STARTING → RUN (uruchomienie)
  - `PAUSE` → RESUMING → RUN (wznowienie)

- **CMD_PAUSE** - przejście do stanu PAUSE
  - `RUN` → PAUSING → PAUSE (wstrzymanie)

- **CMD_STOPPED** - przejście do stanu STOPPED
  - `PAUSE` → HARD_STOPPING → STOPPED (zatrzymanie)
  - `RUN` → PAUSING → HARD_STOPPING → STOPPED (dwuetapowe)

- **CMD_ACK** - potwierdzenie operatora
  - `FAULT` → STOPPED (potwierdzenie błędu)

## 3. Metody Callback

**W klasie bazowej wszystkie callback są puste** - klasy potomne mogą je przedefiniować bez wpływu na logikę FSM.

**WAŻNE:** Logika systemu (zarządzanie thread'ami, przejścia stanów) jest w handler'ach FSM, nie w callback'ach.

```python
async def on_initialize(self):    # Alokacja zasobów
    pass
async def on_starting(self):      # Przygotowanie do uruchomienia  
    pass
async def on_run(self):           # Uruchomienie zadań biznesowych
    pass
async def on_pausing(self):       # Zatrzymanie zadań
    pass
async def on_pause(self):         # System wstrzymany
    pass
async def on_resuming(self):      # Przygotowanie do wznowienia
    pass
async def on_soft_stopping(self): # Graceful shutdown
    pass
async def on_stopping(self):      # Finalizacja
    pass
async def on_stopped(self):       # System zatrzymany
    pass
async def on_ack(self):           # Czyszczenie po błędzie
    pass
```

## 4. Automatyczne Przejścia

- **UNKNOWN → STOPPED** - w konstruktorze
- **ON_ERROR → FAULT** - przy każdym błędzie w systemie

Błędy automatycznie prowadzą do stanu FAULT, który wymaga ACK operatora.

## 5. Diagram FSM



## 6. Wzorce Przetwarzania Eventów

System implementuje różne wzorce obsługi eventów w zależności od stanu:

| Stan | Wzorzec Obsługi | Opis |
|------|----------------|------|
| **RUN** | Pełne przetwarzanie | Wywołuje `_analyze_event()` potomnych |
| **INITIALIZED** | Informacyjny | "System in initialization state" |
| **PAUSE** | Buffering | "System paused, operation buffered" - zachowuje event |
| **FAULT** | Error response | "System in fault state" - usuwa event |
| **STOPPED** | Odrzucanie | "Service stopped" - usuwa event |
| **Przejściowe** | Informacyjny | "System in transition" |

## 7. Zarządzanie Thread'ami

**Thread'y podstawowe** (cały czas aktywne):
- `analysis_thread` - obsługa kolejki eventów  
- `send_event_thread` - wysyłanie odpowiedzi
- `state_update_thread` - aktualizacja metryk

**Thread operacyjny** (tylko w RUN):
- `local_check_thread` - uruchamiany przy wejściu DO RUN, zatrzymywany przy wyjściu Z RUN

**Logika zarządzania jest w handler'ach FSM:**
```python
# _handle_cmd_run() - uruchomienie
self.__fsm_state = EventListenerState.RUN
if not self.local_check_thread.is_alive():
    self.__start_local_check()  # ✅ Przed callback
await self.on_run()

# _handle_cmd_pause() - zatrzymanie  
if self.local_check_thread.is_alive():
    self.__stop_local_check()  # ✅ Przed przejściem
self.__fsm_state = EventListenerState.PAUSING
```

## 8. Przykład Implementacji

```python
class MyEventListener(EventListener):
    async def on_initialize(self):
        self.database = await connect_to_db()
        
    async def on_run(self):
        # local_check już uruchomiony przez handler FSM
        self.task = asyncio.create_task(self.background_work())
        
    async def on_pausing(self):
        # local_check zostanie zatrzymany przez handler FSM
        self.task.cancel()
            
    async def on_stopping(self):
        await self.database.close()
    
    # Główna logika biznesowa (tylko w RUN)
    async def _check_local_data(self):
        await self.process_business_data()
        await self.update_metrics()
        
    # Przetwarzanie eventów (tylko w RUN)
    async def _analyze_event(self, event: Event) -> bool:
        if event.event_type == "my_event":
            # Logika biznesowa...
            return True
        return True
```

## 9. Podsumowanie

EventListener FSM zapewnia:

- ✅ **Kontrolowany cykl życia** usługi z bezpiecznymi przejściami
- ✅ **Automatyczną obsługę błędów** - każdy błąd prowadzi do FAULT  
- ✅ **Separację odpowiedzialności** - FSM oddzielony od logiki biznesowej
- ✅ **Czyste callback** - wszystkie `on_*()` metody są puste w klasie bazowej
- ✅ **Inteligentne zarządzanie thread'ami** - local_check działa tylko w RUN
- ✅ **Różne wzorce przetwarzania** eventów w zależności od stanu systemu

System jest gotowy do użycia produkcyjnego i zapewnia niezawodne zarządzanie stanem usług EventListener. 