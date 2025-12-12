# Architektura Modułowych Chwytaków (Modular Gripper Architecture)

## Przegląd Architektury

System chwytaków w `avena_commons` został zaprojektowany jako w pełni autonomiczna, zdarzeniowa architektura modułowa. Kluczową zasadą jest **separacja odpowiedzialności**: każdy chwytak jest niezależnym komponentem, który sam monitoruje swój stan, przetwarza zdarzenia i reaguje na warunki błędów.

### Kluczowe Założenia Projektowe

1. **Autonomia Chwytaka**: Gripper otrzymuje bezpośredni dostęp do `robot_state_pkg` i samodzielnie monitoruje swoją kondycję bez ingerencji kontrolera robota.

2. **Zdarzeniowy Przepływ Danych**: Supervisor odbiera zdarzenia domenowe i deleguje je do grippera przed jakąkolwiek akcją na robocie. Gripper waliduje, przetwarza i zwraca rezultat.

3. **Watchdog Niezależny**: Każdy gripper implementuje własną logikę watchdog, która jest wywoływana w pętli ruchu. RobotController tylko reaguje na zgłoszone błędy, nie zna wewnętrznej logiki.

4. **Wymienność**: Możliwość łatwej wymiany typu chwytaka (podciśnieniowy, elektryczny, pneumatyczny) bez modyfikacji RobotController czy Supervisor.

## Przepływ Zdarzeń i Danych

### 1. Event Processing Flow (Przepływ Przetwarzania Zdarzeń)

```
┌─────────────────────────────────────────────────────────────┐
│  ZEWNĘTRZNY SYSTEM (orchestrator, UI, API)                  │
└────────────────────┬────────────────────────────────────────┘
                     │ Event (pump_on, light_off, etc.)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  SUPERVISOR (Warstwa Zdarzeniowa)                           │
│  - Odbiera event z zewnątrz                                 │
│  - Sprawdza czy gripper jest skonfigurowany                 │
│  - Waliduje czy event jest obsługiwany przez gripper        │
└────────────────────┬────────────────────────────────────────┘
                     │ gripper.process_event(event)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  GRIPPER (Moduł Chwytaka)                                   │
│  - Waliduje parametry eventu                                │
│  - Wykonuje akcje IO (włącza pompę, światło, etc.)          │
│  - Aktualizuje swój wewnętrzny stan                         │
│  - Zwraca EventResult {success, data, error}                │
└────────────────────┬────────────────────────────────────────┘
                     │ EventResult
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  SUPERVISOR                                                 │
│  - Jeśli success: loguje sukces                             │ 
│  - Jeśli error: zwraca Result.fail() do zewnętrznego systemu│
└─────────────────────────────────────────────────────────────┘
```

**Kluczowe punkty:**
- RobotController **NIE** jest zaangażowany w przetwarzanie eventów grippera
- Gripper ma pełną kontrolę nad swoim IO i stanem
- Supervisor jedynie deleguje i reaguje na rezultat

### 2. Watchdog Monitoring Flow (Przepływ Monitorowania Watchdog)

```
┌─────────────────────────────────────────────────────────────┐
│  ROBOT CONTROLLER (Pętla Ruchu)                             │
│  - Wykonuje ruch robota wzdłuż trajektorii                  │
│  - W kluczowych punktach (przed, w trakcie, po ruchu)       │
└────────────────────┬────────────────────────────────────────┘
                     │ gripper.check_errors()  [BEZ PARAMETRÓW]
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  GRIPPER (Autonomiczny Watchdog)                            │
│  - Używa WŁASNEGO kontekstu (self._testing_move, etc.)      │
│  - Kontekst ustawiony przez on_path_start() i callbacks     │
│  - Czyta robot_state_pkg (IO, pozycja, prędkość)            │
│  - Oblicza wartości fizyczne (np. ciśnienie z napięcia)     │
│  - Sprawdza warunki błędów (utrata próżni, brak połączenia) │
│  - Zwraca None (OK) lub GripperError                        │
└────────────────────┬────────────────────────────────────────┘
                     │ None lub GripperError
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  ROBOT CONTROLLER                                           │
│  - Jeśli None: kontynuuje ruch                              │
│  - Jeśli GripperError:                                      │
│    * Sprawdza GripperError.recoverable                      │
│    * Jeśli not recoverable: STOP + raise exception          │
│    * Jeśli recoverable: loguje warning i kontynuuje         │
└─────────────────────────────────────────────────────────────┘
```

**Kluczowe punkty:**
- Watchdog jest wywoływany **synchronicznie** w pętli ruchu (3 miejsca: przed, w trakcie, po)
- **check_errors() NIE przyjmuje parametrów** - gripper używa własnego kontekstu
- Kontekst jest zarządzany przez lifecycle callbacks (on_path_start, on_waypoint_reached, on_path_end)
- Gripper samodzielnie decyduje co jest błędem
- RobotController tylko reaguje na zgłoszony błąd zgodnie z GripperError.recoverable

### 3. State Management Flow (Przepływ Zarządzania Stanem)

```
┌─────────────────────────────────────────────────────────────┐
│  ROBOT (Hardware)                                           │
│  - robot_state_pkg zawiera bieżący stan IO, pozycji, etc.   │
└────────────────────┬────────────────────────────────────────┘
                     │ Direct access
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  GRIPPER (Autonomiczny Stan)                                │
│  - Czyta robot_state_pkg bezpośrednio                       │
│  - Przetwarza surowe wartości (voltage → kPa, bool → state) │
│  - Utrzymuje wewnętrzny stan (pump_active, holding, etc.)   │
│  - Używa buforów i filtrów (median filter dla ciśnienia)    │
└────────────────────┬────────────────────────────────────────┘
                     │ gripper.get_state()
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  ROBOT CONTROLLER                                           │
│  - Wywołuje gripper.get_state() dla status update           │
│  - Dodaje do get_status_update() jako gripper_state         │
│  - Nie interpretuje ani nie modyfikuje tych danych          │
└────────────────────┬────────────────────────────────────────┘
                     │ Status update z gripper_state
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  ZEWNĘTRZNY SYSTEM (monitoring, dashboard, logs)            │
└─────────────────────────────────────────────────────────────┘
```

**Kluczowe punkty:**
- Tylko gripper wie jak interpretować surowe dane hardware
- RobotController jest "blind pass-through" dla stanu grippera
- Zewnętrzne systemy otrzymują przetworzone dane (np. ciśnienie w kPa zamiast woltów)

## Komponenty Systemu

### BaseGripper (Klasa Abstrakcyjna)

**Odpowiedzialność**: Definiuje kontrakt dla wszystkich chwytaków.

**Kluczowe metody**:
- `get_robot_config()` - Zwraca konfigurację narzędzia dla robota (współrzędne TCP, masa, etc.)
- `get_io_mapping()` - Zwraca mapowanie logicznych nazw IO na fizyczne piny
- `process_event(event)` - Przetwarza zdarzenie i zwraca rezultat
- `get_state()` - Zwraca bieżący stan grippera jako słownik
- `check_errors()` - Sprawdza warunki błędów, zwraca None lub GripperError (używa wewnętrznego kontekstu)
- `get_supported_events()` - Zwraca zbiór obsługiwanych eventów

**Lifecycle callbacks** (zarządzanie kontekstem):
- `on_enable()` - Wywoływane gdy gripper jest inicjalizowany
- `on_disable()` - Wywoływane gdy gripper jest wyłączany
- `on_path_start(path)` - Wywoływane przed rozpoczęciem ruchu (gripper może odczytać path.testing_move, etc.)
- `on_waypoint_reached(waypoint)` - Wywoływane po osiągnięciu waypointa (gripper może odczytać waypoint.watchdog_override)
- `on_path_end(path)` - Wywoływane po zakończeniu ruchu (gripper resetuje kontekst)
- `validate_path_completion(path)` - Waliduje czy path został pomyślnie ukończony (zwraca EventResult)

**Modele danych Pydantic**:
- `RobotToolConfig` - Konfiguracja narzędzia (ID, współrzędne, typ, waga)
- `IOMapping` - Mapowanie nazw IO na piny (digital_outputs, digital_inputs, analog_inputs, analog_outputs)
- `EventResult` - Rezultat przetwarzania eventu (success, data, error)
- `GripperError` - Wyjątek błędu grippera (error_type, message, recoverable)

### IOManager (Helper Grippera)

**Odpowiedzialność**: Hermetyzuje niskopoziomowe operacje IO z translatem logicznych nazw na piny hardware.

**Kluczowe cechy**:
- **Generyczność**: Nie ma hardkodowanych nazw pinów - wszystko przez IOMapping
- **Bezpieczeństwo**: Wszystkie operacje IO są owijane w try-except i zwracają GripperIOError przy błędach
- **Abstrakcja**: Gripper operuje nazwami ("pump", "pressure_sensor"), IOManager tłumaczy na piny (DO[1], AI[0])
- **Validacja**: Może wykonać test połączenia hardware przez loopback sequence
- **Delegacja**: Używa `ToolIO` do wykonywania operacji IO (eliminuje duplikację kodu)

**Przykładowe użycie** (konceptualne):
```
io_manager.set_do("pump", True)   → tool_io.set_do(pin=1, True) → robot.SetToolDO(pin=1, status=1)
voltage = io_manager.get_ai("pressure_sensor")  → tool_io.get_ai(pin=0) → robot.GetToolAI(pin=0)
```

### ToolIO (Universal IO Utility)

**Odpowiedzialność**: Uniwersalny moduł do operacji IO narzędzia robota.

**Kluczowe cechy**:
- **Pojedyncze źródło prawdy**: Wszystkie operacje IO (DO/DI/AO/AI) w jednym miejscu
- **Unified error handling**: Wszystkie błędy jako `ToolIOError`
- **Stateless**: Nie przechowuje stanu, tylko wykonuje operacje
- **Reusable**: Może być użyty przez IOManager, Supervisor, lub inne komponenty

**Metody**:
- `get_do(pin_id)` - Odczytuje stan pojedynczego digital output
- `set_do(pin_id, value, smooth, block)` - Ustawia digital output
- `get_di(pin_id, block)` - Odczytuje digital input
- `get_ai(pin_id, block)` - Odczytuje analog input
- `set_ao(pin_id, value, block)` - Ustawia analog output
- `get_do_status()` - Odczytuje stan wszystkich DO jako integer
- `decode_do_status(status)` - Dekoduje status DO na listę wartości bool
- `is_bit_set(value, bit)` - Sprawdza czy bit jest ustawiony

### VacuumGripper (Implementacja Referencyjna)

**Odpowiedzialność**: Konkretna implementacja chwytaka próżniowego z autonomicznym watchdog.

**Kluczowe cechy**:
- **PressureCalculator**: Konwertuje napięcie (0-10V) na ciśnienie (kPa) z median filterem na 100 próbkach
- **Autonomiczny watchdog**: 4 przypadki monitorowania:
  1. Pompa wyłączona → OK (nie sprawdza ciśnienia)
  2. Override aktywny → OK (tryb testowy)
  3. Nie trzyma przez debounce_time → OK (grace period)
  4. Powinien trzymać ale ciśnienie za niskie → ERROR (utrata próżni)
- **Event handling**: Obsługuje pump_on, pump_off, light_on, light_off
- **State tracking**: pump_active, pressure_kpa, holding (debounced), light_active

**Konfiguracja**: VacuumGripperConfig rozszerza RobotToolConfig o:
- `io_mapping` - Mapowanie pinów
- `pressure_threshold_kpa` - Próg ciśnienia dla holding
- `hold_debounce_ms` - Czas debounce dla stabilizacji
- `adc_resolution`, `adc_supply_voltage` - Parametry ADC
- `pressure_buffer_size` - Rozmiar bufora dla median filter
- `light_voltage_range` - Zakres napięcia dla regulacji światła

## Jak Stworzyć Nowy Gripper

### Krok 1: Analiza Wymagań

Przed implementacją zdefiniuj:

1. **Sygnały IO**:
   - Jakie Digital Outputs kontrolujesz? (np. solenoid valve, motor enable)
   - Jakie Digital Inputs monitorujesz? (np. position sensors, limit switches)
   - Jakie Analog Inputs czytasz? (np. force sensor, current sensor)
   - Jakie Analog Outputs sterujesz? (np. proportional valve, motor speed)
2. **Parametry fizyczne**: Waga, wymiary, TCP offset
3. **Eventy**: Jakie akcje użytkownik może wywołać? (open, close, set_force, calibrate)
4. **Warunki błędów**: Co oznacza awarię? (timeout, overcurrent, position mismatch)
5. **Stan wewnętrzny**: Co trzeba trackować? (position, force, temperature, cycle_count)

### Krok 2: Stwórz Konfigurację (Pydantic Model)

Rozszerz `RobotToolConfig` o parametry specyficzne dla twojego grippera:

```python
class MyGripperConfig(RobotToolConfig):
    """Konfiguracja MyGripper."""
    io_mapping: IOMapping
    max_force_n: float  # Maksymalna siła w Newtonach
    timeout_ms: int     # Timeout operacji
    calibration_offset: float  # Offset kalibracyjny
    safety_margin: float  # Margines bezpieczeństwa
```

**Dobre praktyki**:
- Używaj jednostek SI w nazwach (force_n, time_ms, voltage_v)
- Dodaj walidatory Pydantic jeśli parametry mają ograniczenia (np. `@validator('max_force_n')`)
- Dokumentuj każde pole w docstring

### Krok 3: Implementuj Klasę Grippera

Dziedzicz po `BaseGripper` i zaimplementuj wszystkie abstrakcyjne metody:

#### 3.1. Constructor i Setup

```python
class MyGripper(BaseGripper):
    def __init__(self, robot, config: MyGripperConfig, message_logger=None):
        self._robot = robot
        self._config = config
        self._logger = message_logger
        
        # Stwórz IOManager dla operacji IO
        self._io = IOManager(robot, config.io_mapping, message_logger)
        
        # Inicjalizuj wewnętrzny stan
        self._is_open = False
        self._current_force = 0.0
        self._last_error = None
        
        # Utwórz pomocnicze obiekty (jeśli potrzebne)
        # np. ForceCalculator, PositionTracker, etc.
```

**Kluczowe punkty**:
- Przechowuj referencję do `robot` dla dostępu do `robot_state_pkg`
- Utwórz `IOManager` z `config.io_mapping`
- Inicjalizuj wszystkie zmienne stanu w konstruktorze

#### 3.2. get_robot_config()

Zwróć konfigurację narzędzia z `_config`:

```python
def get_robot_config(self) -> RobotToolConfig:
    """Zwraca konfigurację narzędzia dla robota."""
    return self._config
```

Prosty pass-through, bo wszystko jest w config.

#### 3.3. get_io_mapping()

Zwróć mapowanie IO z `_config`:

```python
def get_io_mapping(self) -> IOMapping:
    """Zwraca mapowanie IO grippera."""
    return self._config.io_mapping
```

#### 3.4. get_supported_events()

Zdefiniuj zbiór obsługiwanych eventów:

```python
def get_supported_events(self) -> set[str]:
    """Zwraca zbiór obsługiwanych eventów."""
    return {"gripper_open", "gripper_close", "set_force", "calibrate"}
```

Supervisor użyje tego do walidacji eventów przed przekazaniem do `process_event()`.

#### 3.5. process_event() - Serce Logiki Eventów

To najważniejsza metoda - tu przetwarzasz wszystkie eventy:

```python
def process_event(self, event: Event) -> EventResult:
    """Przetwarza event grippera."""
    try:
        action = event.data.get("action")
        
        if action == "gripper_open":
            return self._handle_open(event)
        elif action == "gripper_close":
            return self._handle_close(event)
        elif action == "set_force":
            return self._handle_set_force(event)
        elif action == "calibrate":
            return self._handle_calibrate(event)
        else:
            return EventResult(
                success=False,
                data={},
                error=f"Unknown action: {action}"
            )
    except Exception as e:
        return EventResult(
            success=False,
            data={},
            error=f"Event processing failed: {str(e)}"
        )
```

**Dobre praktyki**:
- Każdą akcję wydziel do osobnej metody `_handle_*()` dla czytelności
- Zawsze zwracaj `EventResult` - nawet przy wyjątkach
- Waliduj parametry eventu na początku
- Używaj `self._io.set_do()` zamiast bezpośrednich wywołań robot API
- Loguj istotne akcje przez `message_logger`
- Aktualizuj stan wewnętrzny po udanej akcji

#### 3.6. get_state() - Eksport Stanu

Zwróć bieżący stan jako słownik:

```python
def get_state(self) -> Dict[str, Any]:
    """Zwraca bieżący stan grippera."""
    return {
        "is_open": self._is_open,
        "current_force_n": self._current_force,
        "target_force_n": self._config.max_force_n,
        "last_error": self._last_error,
        "gripper_type": "MyGripper"
    }
```

**Dobre praktyki**:
- Zwracaj przetworzone wartości (np. force w Newtonach, nie surowe woltaże)
- Dodaj `gripper_type` dla identyfikacji w logach
- Możesz dodać `timestamp` jeśli stan się zmienia w czasie
- To jest publiczne API - zewnętrzne systemy będą to czytać

#### 3.7. check_errors() - Watchdog Logic

Implementuj autonomiczny watchdog wykorzystując wewnętrzny kontekst:

```python
def check_errors(self) -> Optional[GripperError]:
    """Sprawdza warunki błędów grippera używając wewnętrznego kontekstu.
    
    Kontekst jest zarządzany przez lifecycle callbacks:
    - on_path_start() ustawia self._testing_move, self._watchdog_override
    - on_waypoint_reached() może modyfikować self._watchdog_override
    - on_path_end() resetuje kontekst
    """
    
    # Przypadek 1: Tryb testowy - ignoruj błędy (kontekst z on_path_start)
    if self._testing_move or self._watchdog_override:
        return None
    
    # Przypadek 2: Gripper nieaktywny - nic do sprawdzania
    if not self._is_active():
        return None
    
    # Przypadek 3: Czytaj surowy stan z robot_state_pkg
    try:
        force_voltage = self._io.get_ai("force_sensor")
        position_sensor = self._io.get_di("position_sensor")
    except GripperIOError as e:
        return GripperError(
            error_type="connection_error",
            message=f"IO read failed: {e.message}",
            recoverable=False
        )
    
    # Przypadek 4: Przetwarza i waliduj
    current_force = self._voltage_to_force(force_voltage)
    
    if self._is_open and not position_sensor:
        return GripperError(
            error_type="position_error",
            message="Gripper should be open but position sensor inactive",
            recoverable=True
        )
    
    if current_force > self._config.max_force_n:
        return GripperError(
            error_type="overload_error",
            message=f"Force {current_force}N exceeds max {self._config.max_force_n}N",
            recoverable=False
        )
    
    # Wszystko OK
    return None
```

**Kluczowe punkty**:
- **BEZ PARAMETRÓW**: Gripper używa własnego wewnętrznego kontekstu (self._testing_move, self._watchdog_override)
- Kontekst jest ustawiany przez `on_path_start()` i `on_waypoint_reached()`
- Czytaj `robot_state_pkg` przez `IOManager` dla spójności
- Zdefiniuj jasne `error_type` (watchdog_error, connection_error, overload_error)
- Ustawiaj `recoverable=True` jeśli błąd może być przejściowy
- `recoverable=False` dla błędów wymagających interwencji (uszkodzenie hardware)
- **Uwaga**: Ta metoda jest wywoływana w pętli ruchu - musi być **szybka** (< 10ms)

#### 3.8. Lifecycle Callbacks - Context Management

Gripper śledzi swój kontekst przez callbacks wywoływane przez RobotController:

```python
def on_path_start(self, path: Path) -> None:
    """Wywoływane przed rozpoczęciem ruchu."""
    self._current_path = path
    self._testing_move = path.testing_move
    if self._testing_move:
        self._watchdog_override = True  # Wyłącz watchdog dla testów
    else:
        self._watchdog_override = False

def on_waypoint_reached(self, waypoint: Waypoint) -> None:
    """Wywoływane po osiągnięciu waypointa."""
    if waypoint.watchdog_override:
        self._watchdog_override = True  # Konkretny waypoint może wyłączyć watchdog

def on_path_end(self, path: Path) -> None:
    """Wywoływane po zakończeniu ruchu."""
    self._current_path = None
    self._testing_move = False
    self._watchdog_override = False  # Reset kontekstu

def validate_path_completion(self, path: Path) -> EventResult:
    """Waliduje czy path został pomyślnie ukończony (tylko dla testing_move)."""
    if not path.testing_move:
        return EventResult(success=True)
    
    # Dla testing_move sprawdź czy gripper trzyma przedmiot
    if not self._pump_holding:
        return EventResult(
            success=False,
            data={"reason": "Gripper not holding after testing move"}
        )
    
    return EventResult(success=True)
```

**Kluczowe punkty**:
- Callbacks pozwalają gripperowi **śledzić własny kontekst** bez zewnętrznych parametrów
- RobotController **nie zna** szczegółów grippera (testing_move, watchdog_override)
- Gripper **sam decyduje** co zrobić z informacjami z Path/Waypoint
- `validate_path_completion()` zastępuje hardkodowane sprawdzanie `gripper_state["holding"]`

### Krok 4: Helpery i Kalkulatory

Dla złożonych chwytaków utwórz klasy pomocnicze (wzorowane na `PressureCalculator`):

```python
class ForceCalculator:
    """Konwerter napięcia na siłę z filtrowaniem."""
    
    def __init__(self, max_voltage: float, max_force_n: float, buffer_size: int = 50):
        self._max_voltage = max_voltage
        self._max_force = max_force_n
        self._buffer = deque(maxlen=buffer_size)
    
    def calculate_force(self, voltage: float) -> float:
        """Konwertuje napięcie na siłę z median filterem."""
        # Linear mapping voltage → force
        force = (voltage / self._max_voltage) * self._max_force
        
        self._buffer.append(force)
        
        # Median filter dla stabilności
        if len(self._buffer) >= 10:
            return statistics.median(self._buffer)
        return force
    
    def reset(self):
        """Resetuje bufor."""
        self._buffer.clear()
```

**Dobre praktyki**:
- Separacja logiki obliczeń od logiki grippera
- Używaj buforów i filtrów dla sygnałów analogowych (median, moving average)
- Dokumentuj algorytmy konwersji (wzory, źródła)
- Unit testy dla kalkulatorów są łatwe - skorzystaj z tego!

### Krok 5: Eksportuj w __init__.py

Dodaj nowy gripper do `src/avena_commons/robot/grippers/__init__.py`:

```python
from .my_gripper import MyGripper, MyGripperConfig

__all__ = [
    # ... existing exports ...
    "MyGripper",
    "MyGripperConfig",
]
```

### Krok 6: Testowanie

#### Unit Testy

Testuj każdą metodę w izolacji:

```python
def test_process_event_open():
    # Mock robot and config
    config = MyGripperConfig(...)
    gripper = MyGripper(mock_robot, config)
    
    event = Event(data={"action": "gripper_open"})
    result = gripper.process_event(event)
    
    assert result.success == True
    assert gripper.get_state()["is_open"] == True
```

#### Integration Testy

Testuj z prawdziwym robotem (lub symulatorem):

```python
def test_watchdog_detects_overload():
    gripper = MyGripper(real_robot, config)
    
    # Symuluj overload (force sensor > max)
    # ...
    
    error = gripper.check_errors({})
    assert error is not None
    assert error.error_type == "overload_error"
```

### Krok 7: Dokumentacja

Stwórz plik markdown dokumentujący twój gripper:

- Opis fizyczny i zastosowanie
- Schemat pinów IO
- Lista obsługiwanych eventów z parametrami
- Warunki błędów watchdog
- Przykład konfiguracji
- Procedury kalibracji/setup
- Troubleshooting

## Integracja Grippera z Systemem

### Inicjalizacja w Supervisor

Gdy masz gotowy gripper, zainicjalizuj go i przekaż do Supervisor:

```python
from avena_commons.robot.grippers import MyGripper, MyGripperConfig

# 1. Stwórz konfigurację
gripper_config = MyGripperConfig(
    tool_id=1,
    tool_coordinates=[0, 0, 150, 0, 0, 0],  # TCP offset
    tool_type=1,
    tool_installation=0,
    weight=2.5,  # kg
    mass_coord=[0, 0, 75],  # Center of mass
    io_mapping=IOMapping(
        digital_outputs={"valve_open": 0, "valve_close": 1},
        digital_inputs={"position_sensor": 0},
        analog_inputs={"force_sensor": 0},
        analog_outputs={}
    ),
    max_force_n=50.0,
    timeout_ms=5000,
    calibration_offset=0.0,
    safety_margin=0.9
)

# 2. Stwórz instancję grippera (robot będzie przekazany później)
gripper = MyGripper(config=gripper_config, message_logger=logger)

# 3. Przekaż do Supervisor
supervisor = Supervisor(
    name="robot_supervisor",
    suffix=1,
    message_logger=logger,
    gripper=gripper  # <-- Tu przekazujesz
)
```

**Uwaga**: Robot instance jest przekazywany do grippera w `Supervisor.on_initializing()`, więc w konstruktorze grippera możesz przekazać `None` - zostanie ustawiony później.

### Wysyłanie Eventów

Z zewnętrznego systemu (orchestrator, API):

```python
# Event do otwarcia grippera
event = Event(
    name="gripper",
    data={
        "action": "gripper_open",
        "force": 30.0  # opcjonalny parametr
    }
)

# Supervisor automatycznie przekaże do gripper.process_event()
result = await supervisor.on_event(event)

if result.success:
    print("Gripper opened successfully")
else:
    print(f"Error: {result.message}")
```

### Monitorowanie Stanu

Stan grippera jest dostępny w `RobotController.get_status_update()`:

```python
status = robot_controller.get_status_update()

gripper_state = status.get("gripper_state", {})
print(f"Gripper type: {gripper_state.get('type')}")
print(f"Gripper state: {gripper_state.get('state')}")
# Output z get_state() grippera
```

## Zaawansowane Tematy

### 1. Asynchroniczne Operacje Grippera

Jeśli operacja grippera wymaga czasu (np. pneumatyczny cylinder):

```python
def _handle_close(self, event: Event) -> EventResult:
    """Zamyka gripper z timeoutem."""
    
    # Włącz valve
    self._io.set_do("valve_close", True)
    
    # Czekaj na potwierdzenie sensora pozycji (max timeout)
    start_time = time.time()
    while True:
        if self._io.get_di("position_sensor_closed"):
            self._is_open = False
            return EventResult(success=True, data={"time_ms": elapsed})
        
        elapsed = (time.time() - start_time) * 1000
        if elapsed > self._config.timeout_ms:
            return EventResult(
                success=False,
                data={},
                error=f"Close timeout after {elapsed}ms"
            )
        
        time.sleep(0.01)  # 10ms polling
```

**Uwaga**: `process_event()` jest wywoływana w kontekście async Supervisor, ale sama może być synchroniczna (blocking). Dla długich operacji rozważ:
- Polling z timeoutem (jak powyżej)
- State machine w grippie (rozpocznij akcję, monitoruj w `check_errors()`)
- Event callback (gripper emituje event po zakończeniu)

### 2. Gripper z State Machine

Dla złożonych sekwencji (np. kalibracja, pick-and-place):

```python
class GripperState(Enum):
    IDLE = "idle"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    CALIBRATING = "calibrating"
    ERROR = "error"

class StatefulGripper(BaseGripper):
    def __init__(self, ...):
        self._state = GripperState.IDLE
        self._state_entry_time = time.time()
    
    def process_event(self, event):
        # Transitions zależne od current state
        if self._state == GripperState.IDLE:
            if action == "gripper_close":
                self._state = GripperState.CLOSING
                self._start_close()
        elif self._state == GripperState.CLOSING:
            # Event może być "abort" - przerwanie
            if action == "abort":
                self._state = GripperState.ERROR
    
    def check_errors(self, path_flags):
        # Sprawdź timeouty based on state
        elapsed = time.time() - self._state_entry_time
        
        if self._state == GripperState.CLOSING:
            if elapsed > self._config.close_timeout_s:
                return GripperError("timeout", "Close timeout", True)
```

### 4. Gripper Calibration Workflow

Dodaj event `calibrate` do wykonania procedury kalibracyjnej:

```python
def _handle_calibrate(self, event: Event) -> EventResult:
    """Wykonuje kalibrację grippera."""
    
    # 1. Otwórz do pozycji max
    self._io.set_do("valve_open", True)
    time.sleep(1.0)
    
    # 2. Czytaj pozycję sensora
    open_position = self._io.get_ai("position_sensor")
    
    # 3. Zamknij do pozycji min
    self._io.set_do("valve_close", True)
    time.sleep(1.0)
    
    # 4. Czytaj pozycję sensora
    close_position = self._io.get_ai("position_sensor")
    
    # 5. Oblicz offset i zapisz w config lub state
    self._calibration_offset = (open_position + close_position) / 2
    
    return EventResult(
        success=True,
        data={
            "open_position": open_position,
            "close_position": close_position,
            "offset": self._calibration_offset
        }
    )
```

## Najlepsze Praktyki (Best Practices)

### ✅ DO:

1. **Używaj IOManager**: Zawsze operuj przez `IOManager` zamiast bezpośrednich wywołań robot API
2. **Waliduj parametry**: Sprawdzaj `event.data` przed użyciem, zwracaj error przy błędnych danych
3. **Loguj akcje**: Używaj `message_logger` do logowania istotnych zdarzeń (pump on/off, errors)
4. **Obsługuj wyjątki**: Wszystkie metody powinny mieć try-except i zwracać EventResult/GripperError
5. **Dokumentuj units**: Używaj jednostek w nazwach zmiennych (`force_n`, `time_ms`, `voltage_v`)
6. **Testuj w izolacji**: Unit testy dla każdej metody z mock robot
7. **Filteruj sygnały analogowe**: Używaj median/moving average dla stabilności
8. **Respektuj path_flags**: W `check_errors()` sprawdzaj `testing_move` i inne flagi

### ❌ DON'T:

1. **Nie modyfikuj RobotController**: Gripper musi być standalone - zero zmian w RobotController
2. **Nie blokuj długo**: `process_event()` i `check_errors()` muszą być szybkie (< 100ms)
3. **Nie używaj global state**: Wszystko w `self._*`, żadnych global variables
4. **Nie hardkoduj pinów**: Zawsze przez `IOMapping` - nigdy `robot.SetToolDO(1, ...)`
5. **Nie ignoruj błędów IO**: Zawsze owijaj w try-except i zwracaj GripperIOError
6. **Nie zakładaj initial state**: W konstruktorze czytaj hardware i ustaw stan accordingly
7. **Nie mieszaj jednostek**: Konsekwentnie SI units - nie mieszaj V i mV, N i kgf

## Rozwiązywanie Problemów (Troubleshooting)

### Gripper nie reaguje na eventy

1. Sprawdź `get_supported_events()` - czy event jest na liście?
2. Sprawdź Supervisor logi - czy event dotarł do `gripper.process_event()`?
3. Sprawdź `EventResult.error` - co zwraca `process_event()`?
4. Zweryfikuj `IOMapping` - czy nazwy pinów są poprawne?

### Watchdog fałszywie zgłasza błędy

1. Sprawdź debounce time - czy jest wystarczający dla stabilizacji?
2. Sprawdź thresholdy - czy nie są zbyt restrykcyjne?
3. Dodaj logging w `check_errors()` - jakie wartości czyta?
4. Użyj `testing_move=True` w Path do debugowania

### IO operations rzucają GripperIOError

1. Sprawdź fizyczne połączenia - czy kable są podłączone?
2. Zweryfikuj pin numbers w `IOMapping` - porównaj z dokumentacją robota
3. Sprawdź `robot_state_pkg` - czy IO jest aktywne?
4. Użyj `IOManager.validate_connection()` z test sequence

### Stan grippera nie aktualizuje się

1. Sprawdź czy `process_event()` aktualizuje `self._*` po akcji
2. Sprawdź czy `get_state()` zwraca aktualne wartości
3. Sprawdź czy `RobotController.get_status_update()` wywołuje `gripper.get_state()`
4. Zweryfikuj czy monitoring system czyta `gripper_state` z status update

## Podsumowanie

Architektura modułowych chwytaków zapewnia:

- **Separację odpowiedzialności**: Każdy komponent ma jasno zdefiniowaną rolę
- **Autonomię**: Gripper sam monitoruje stan i przetwarza eventy
- **Wymienność**: Łatwa zmiana typu grippera bez modyfikacji kontrolera
- **Testowalność**: Komponenty można testować w izolacji
- **Rozszerzalność**: Nowe grippery przez implementację BaseGripper

Kluczem do sukcesu jest **zrozumienie przepływów**:
- **Event flow**: Supervisor → Gripper → EventResult
- **Watchdog flow**: RobotController → Gripper → GripperError
- **State flow**: Hardware → Gripper → Status Update

Przestrzegając tych zasad i wzorców, możesz stworzyć niezawodny, testowalny i łatwy w utrzymaniu moduł grippera dla dowolnego typu narzędzia robotycznego.
