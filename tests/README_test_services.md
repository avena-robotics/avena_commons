# Testowe Usługi dla Orchestratora

## Przegląd

Ten katalog zawiera kompletny zestaw testowych usług które symulują rzeczywiste komponenty systemu. Wszystkie usługi implementują maszynę stanów FSM zgodną z dokumentacją Orchestratora i mogą być używane do testowania scenariuszy.

## Struktura Plików

```
tests/
├── services/
│   ├── __init__.py                 # Moduł testowych usług
│   ├── base_test_service.py        # Bazowa klasa FSM
│   ├── io_service.py              # Symulator warstwy I/O (port 8001)
│   ├── supervisor_service.py      # Symulator robotów (porty 8002, 8003)
│   ├── munchies_algo_service.py   # Symulator logiki biznesowej (port 8004)
│   └── run_all_services.py        # Skrypt uruchamiający wszystkie usługi
├── test_full_scenario.py          # Test pełnego scenariusza
└── README_test_services.md        # Ta dokumentacja
```

## Testowe Usługi

### 1. **IoService** (port 8001)
- **Grupa:** `base_io`
- **Symuluje:** Warstwę I/O systemu
- **Funkcje:**
  - Podłączanie do urządzeń (sensory, aktuatory)
  - Cykliczne operacje I/O
  - Monitoring stanu sprzętu
- **Czas inicjalizacji:** 3.0s

### 2. **SupervisorService** (porty 8002, 8003)
- **Grupa:** `supervisors`
- **Symuluje:** Komponenty nadzorujące roboty
- **Funkcje:**
  - Kontrola robotów przemysłowych
  - Monitoring pozycji i statusu
  - Wykonywanie zadań ruchu
  - Bezpieczny powrót do pozycji domowej
- **Czas inicjalizacji:** 2.5s
- **Czas graceful shutdown:** 3.0s (powrót do pozycji domowej)

### 3. **MunchiesAlgoService** (port 8004)
- **Grupa:** `main_logic`
- **Symuluje:** Główną logikę biznesową
- **Funkcje:**
  - Algorytm planowania zadań
  - Zarządzanie kolejką zamówień
  - Optymalizacja ścieżek robotów
  - Monitoring wydajności systemu
- **Czas inicjalizacji:** 4.0s (najdłuższy)

## Maszyna Stanów FSM

Wszystkie usługi implementują jednolitą maszynę stanów zgodną z dokumentacją:

```
STOPPED → [CMD_INITIALIZE] → INITIALIZING → INITIALIZED → [CMD_RUN] → STARTING → STARTED
    ↑                                                                               ↓
    └─── [CMD_GRACEFUL_STOP] ← STOPPING ←─────────────────────────────────────────┘
```

### Stany FSM:
- **STOPPED:** Stan pasywny, gotowy na inicjalizację
- **INITIALIZING:** Aktywna inicjalizacja (połączenia, kalibracja)
- **INITIALIZED:** Zainicjalizowany, gotowy do uruchomienia
- **STARTING:** Przejście do stanu operacyjnego
- **STARTED:** Główny stan operacyjny (symulacja pracy)
- **STOPPING:** Graceful shutdown (dokańczanie zadań)

### Obsługiwane Komendy FSM:
- `CMD_INITIALIZE` - przejście STOPPED → INITIALIZING
- `CMD_RUN` / `CMD_START` - przejście INITIALIZED → STARTING
- `CMD_GRACEFUL_STOP` - przejście STARTED → STOPPING
- `CMD_GET_STATE` - zwraca aktualny stan FSM
- `CMD_RESET` - reset ze stanu FAULT → STOPPED

## Instrukcje Użycia

### 1. Uruchomienie Wszystkich Usług

```bash
# Przejdź do katalogu tests/services
cd tests/services

# Uruchom wszystkie usługi jednocześnie
python run_all_services.py

# Sprawdź status usług
python run_all_services.py status

# Zatrzymaj wszystkie usługi
python run_all_services.py stop
```

### 2. Uruchomienie Pojedynczych Usług

```bash
# Usługa IO
PYTHONPATH=../../src python io_service.py

# Supervisor 1
PYTHONPATH=../../src python supervisor_service.py 1

# Supervisor 2  
PYTHONPATH=../../src python supervisor_service.py 2

# MunchiesAlgo
PYTHONPATH=../../src python munchies_algo_service.py
```

### 3. Test Pełnego Scenariusza

```bash
# Najpierw uruchom wszystkie usługi
cd tests/services
python run_all_services.py &

# W drugim terminalu uruchom Orchestrator
cd ../../
PYTHONPATH=src python -c "
from avena_commons.orchestrator.orchestrator import Orchestrator
from avena_commons.util.logger import MessageLogger
logger = MessageLogger('orchestrator.log', debug=True)
orchestrator = Orchestrator('orchestrator', 8000, '127.0.0.1', logger, True)
orchestrator.start()
"

# W trzecim terminalu uruchom test scenariusza
cd tests
python test_full_scenario.py
```

## Przykład Scenariusza Startowego

Testowe usługi są skonfigurowane do współpracy ze scenariuszem YAML:

```yaml
- name: "Scenariusz startowy systemu - STOPPED do RUN"
  actions:
    # Krok 1: IO (podstawa systemu)
    - type: "send_command"
      component: "io"
      command: "CMD_INITIALIZE"
    - type: "wait_for_state"
      component: "io"
      target_state: "INITIALIZED"
      timeout: "30s"

    # Krok 2: Supervisory (zależne od I/O)  
    - type: "send_command"
      group: "supervisors"
      command: "CMD_INITIALIZE"
    - type: "wait_for_state"
      group: "supervisors"
      target_state: "INITIALIZED"
      timeout: "45s"

    # Krok 3: Logika biznesowa (jako ostatnia)
    - type: "send_command"
      component: "munchies_algo"
      command: "CMD_INITIALIZE"
    - type: "wait_for_state"
      component: "munchies_algo"
      target_state: "INITIALIZED"
      timeout: "30s"

    # Krok 4: Uruchomienie wszystkich
    - type: "send_command"
      target: "@all"
      command: "CMD_RUN"
    - type: "wait_for_state"
      target: "@all"
      target_state: "STARTED"
      timeout: "15s"
```

## Monitoring i Diagnostyka

### Sprawdzenie Statusu Usługi

```bash
# Sprawdź status pojedynczej usługi
curl -X POST http://127.0.0.1:8001/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "test",
    "destination": "io",
    "event_type": "CMD_GET_STATE",
    "data": {}
  }'
```

### Logi Usług

Każda usługa generuje własny plik logów:
- `io_service.log` - logi usługi IO
- `supervisor_1_service.log` - logi Supervisor 1
- `supervisor_2_service.log` - logi Supervisor 2
- `munchies_algo_service.log` - logi MunchiesAlgo
- `scenario_test.log` - logi testu scenariusza

### Przykładowe Dane Statusu

```json
{
  "name": "supervisor_1",
  "state": "STARTED",
  "port": 8002,
  "address": "127.0.0.1",
  "group": "supervisors",
  "supervisor_id": 1,
  "robot_state": {
    "connection": "connected",
    "position": {"x": 150, "y": 75, "z": 300},
    "status": "moving_to_target",
    "is_moving": true
  },
  "tasks_completed": 42
}
```

## Rozwój i Rozszerzenia

### Dodawanie Nowej Usługi

1. **Utwórz nową klasę** dziedziczącą po `BaseTestService`
2. **Zaimplementuj metody** `on_initializing()`, `_simulate_work()`, `on_stopping()`
3. **Dodaj do** `run_all_services.py`
4. **Zaktualizuj konfigurację** Orchestratora

### Modyfikacja Czasów Symulacji

```python
# W konstruktorze usługi
super().__init__(
    name="my_service",
    port=8005,
    initialization_time=1.0,  # Szybsza inicjalizacja
    shutdown_time=0.5         # Szybsze zamykanie
)
```

### Dodawanie Niestandardowych Komend

```python
async def _handle_custom_event(self, event: Event):
    if event.event_type == "MY_CUSTOM_COMMAND":
        # Obsługa niestandardowej komendy
        result = self._process_custom_command(event.data)
        event.result = Result(result="success", data=result)
        await self._reply(event)
    else:
        await super()._handle_custom_event(event)
```

## Rozwiązywanie Problemów

### Usługa nie startuje
- Sprawdź czy port jest wolny: `netstat -an | grep 8001`
- Sprawdź PYTHONPATH: `echo $PYTHONPATH`
- Sprawdź logi błędów w terminalu

### Timeout w scenariuszu
- Zwiększ wartości timeout w scenariuszu YAML
- Sprawdź czy wszystkie usługi odpowiadają na `CMD_GET_STATE`
- Monitoruj logi usług podczas wykonania

### Usługa w stanie FAULT
- Wyślij `CMD_RESET` aby przywrócić stan STOPPED
- Sprawdź logi usługi dla szczegółów błędu
- Restart usługi jeśli problem się powtarza

---

**Uwaga:** Te usługi są przeznaczone wyłącznie do testowania i rozwoju. Nie używaj ich w środowisku produkcyjnym! 