# Dokumentacja Supervisor i RobotController

## Przegląd systemu

System sterowania robotem Fairino składa się z dwóch warstw:

- **Supervisor** - warstwa zdarzeniowa, przyjmuje polecenia w formie eventów i zarządza cyklem życia robota
- **RobotController** - warstwa sprzętowa, bezpośrednia komunikacja z robotem przez SDK Fairino

Supervisor działa jako fasada event-driven - odbiera zdarzenia (np. "jedź do punktu X", "włącz pompę"), deleguje je do RobotController i zwraca wyniki asynchronicznie.

## Podstawowe operacje

### Inicjalizacja

Przed rozpoczęciem pracy robot musi zostać zainicjalizowany:

```python
supervisor = Supervisor(
    name="robot_supervisor",
    suffix=1,
    message_logger=logger,
    debug=False
)
# Robot w stanie INITIALIZED
```

Konfiguracja wymaga przekazania:
- adresu IP robota
- pozycji startowej (dla walidacji bezpieczeństwa)
- poziomów wykrywania kolizji dla każdej osi
- parametrów chwytaka (ciężar, współrzędne narzędzia)

### Uruchomienie

Aby włączyć robota i rozpocząć pracę:

```python
# Przejście do stanu RUN
# Robot gotowy do przyjmowania poleceń ruchu
```

Stan RUN uruchamia połączenie z robotem i ustawia tryb automatyczny. Robot może teraz wykonywać ruchy.

### Ruchy robota

System obsługuje dwa typy ruchów:

**Ruch w przestrzeni stawów (move_j)**
```python
from avena_commons.event_listener.types import Waypoint, Path, SupervisorMoveAction

event = Event(
    event_type="move_j",
    data=SupervisorMoveAction(
        path=Path(
            waypoints=[
                Waypoint(waypoint=[x, y, z, rx, ry, rz], joints=[j1, j2, j3, j4, j5, j6])
            ],
            max_speed=100
        )
    ).to_dict()
)
```

**Ruch liniowy (move_l)**
```python
from avena_commons.event_listener.types import Waypoint, Path, SupervisorMoveAction

event = Event(
    event_type="move_l", 
    data=SupervisorMoveAction(
        path=Path(
            waypoints=[
                Waypoint(waypoint=[177.5, -780.0, 510.0, 180.0, 0.0, 180.0]),
                Waypoint(waypoint=[200.0, -750.0, 500.0, 180.0, 0.0, 180.0], blend_radius=20.0)
            ], 
            max_speed=80
        )
    ).to_dict()
)
```

Parametry ścieżki:
- `waypoints` - lista punktów do odwiedzenia (współrzędne kartezjańskie [x,y,z,rx,ry,rz])
- `max_speed` - maksymalna prędkość w procentach (0-100)
- `blend_radius` - promień zaokrąglenia dla płynnych przejść między punktami (w mm)
- `collision_override` - wyłącza wykrywanie kolizji dla tej ścieżki
- `testing_move` - tryb testowy, sprawdza czy ruch jest możliwy bez faktycznego wykonania

### Operacje chwytaka

**Włączenie pompy próżniowej**
```python
from avena_commons.event_listener.types import SupervisorPumpAction

event = Event(
    event_type="pump_on",
    data=SupervisorPumpAction(
        pressure_threshold=-15  # próg ciśnienia w kPa
    ).to_dict()
)
```

System automatycznie monitoruje ciśnienie podczas ruchu. Gdy próg zostanie osiągnięty, robot zatrzymuje się i potwierdza chwyt.

**Wyłączenie pompy**
```python
event = Event(event_type="pump_off")
```

**Watchdog próżniowy** - podczas ruchu z włączoną pompą, system ciągle sprawdza czy podciśnienie jest utrzymywane. Jeśli zostanie utracone:
- w trybie normalnym: błąd `PUMP_WATCHDOG_ERROR`, zatrzymanie ruchu
- z flagą `interruption_move`: zapisanie pozycji i kontynuacja
- z `watchdog_override`: całkowite wyłączenie monitorowania

### Sterowanie oświetleniem

```python
# Włączenie światła (intensywność 0-100%)
event = Event(event_type="light_on", data={"value": 80})

# Wyłączenie
event = Event(event_type="light_off")
```

### Odczyt pozycji

```python
event = Event(event_type="current_position")
# Zwraca natychmiastowy wynik z aktualną pozycją kartezjańską i stawami
```

## Zarządzanie stanami

### Stany Supervisor (EventListener)

- **STOPPED** - robot niezainicjalizowany, brak połączenia
- **INITIALIZED** - robot podłączony, serwomechanizmy wyłączone
- **RUN** - robot aktywny, przyjmuje polecenia
- **PAUSE** - ruch wstrzymany, można wznowić
- **FAULT** - błąd wymagający potwierdzenia (ACK) przed kontynuacją

### Stany RobotController

Podczas wykonywania poleceń RobotController przechodzi przez stany:

- **IDLE** - gotowy do przyjęcia polecenia
- **IN_MOVE** - wykonywanie ruchu
- **MOVEMENT_FINISHED** - ruch zakończony
- **WAITING_FOR_GRIPPER_INFO** - oczekiwanie na potwierdzenie stanu pompy
- **GRIPPER_FINISHED** - operacja chwytaka zakończona
- **PUMP_WATCHDOG_ERROR** - utrata podciśnienia podczas trzymania
- **ERROR** - błąd ogólny

### Przetwarzanie eventów

1. Event trafia do Supervisor
2. Supervisor analizuje typ i przekazuje do odpowiedniej akcji
3. RobotController wykonuje operację w osobnym wątku
4. Supervisor monitoruje stan co ~100ms
5. Po zakończeniu wysyła `Result` z wynikiem operacji

Przykładowy wynik sukcesu:
```python
Result(result="success")
```

Wynik błędu:
```python
Result(result="failure", error_code=2, error_message="Pump watchdog failure")
```

## Obsługa błędów i kolizji

### Wykrywanie kolizji

System automatycznie wykrywa kolizje poprzez analizę kodów błędów robota. Gdy kolizja zostanie wykryta:

1. Robot resetuje błąd i wznawia ruch
2. Wyłącza serwomechanizmy (2s przerwa)
3. Włącza ponownie serwomechanizmy
4. Wysyła pozostałe punkty trasy
5. Weryfikuje czy robot przejechał bezpiecznie 100mm od miejsca kolizji

Maksymalnie 3 próby odzyskania na jeden ruch. Po przekroczeniu - wyjątek.

### Walidacja pozycji

Przed każdym ruchem system sprawdza:
- czy robot jest w bezpiecznej odległości od pozycji startowej (domyślnie 200mm)
- po ruchu: czy osiągnął punkt docelowy (tolerancja 10mm)

### Poziomy wykrywania kolizji

Można dostosować czułość wykrywania kolizji dla każdej osi (wartości 1-100):
- wartość (1-10): czułe, zatrzymuje się przy małych oporach, 10 to dosyć spora siła
- wartość 100: brak jakichkolwiek ograniczeń, silniki nie zareagują na opory

Przykładowa konfiguracja:
```python
collision_levels = {
    "j1": 10,  # podstawa - niska czułość
    "j2": 8,   # ramię dolne - niska czułość
    "j3": 10,  # ramię górne - niska czułość
    "j4": 5,   # łokieć - bardzo czuły
    "j5": 3,   # nadgarstek - bardzo czuły
    "j6": 100  # obrót - brak  (kontakt z obiektami)
}
```

## Zaawansowane funkcje

### Płynne łączenie trajektorii (blending)

Parametr `blend_radius` pozwala na płynne przejścia między punktami bez całkowitego zatrzymania:

```python
from avena_commons.event_listener.types import Waypoint, Path

path = Path(
    waypoints=[
        Waypoint(waypoint=[100, -500, 300, 180, 0, 180]),
        Waypoint(waypoint=[200, -500, 300, 180, 0, 180], blend_radius=30.0),
        Waypoint(waypoint=[200, -400, 300, 180, 0, 180], blend_radius=30.0),
        Waypoint(waypoint=[100, -400, 300, 180, 0, 180])  # ostatni bez blend
    ]
)
```

Robot zaczyna skręcać w stronę następnego punktu w odległości `blend_radius` mm od aktualnego celu. Skutkuje to szybszym i płynniejszym ruchem.

### Ruchy testowe

Flaga `testing_move` pozwala sprawdzić czy ruch z chwytaniem jest możliwy:

```python
from avena_commons.event_listener.types import Path, Waypoint

path = Path(
    waypoints=[Waypoint(waypoint=[x, y, z, rx, ry, rz])],
    testing_move=True
)
# Jeśli pompa osiągnie próg ciśnienia - ruch OK
# Wynik: Result(result="success") lub Result(result="test_failed", error_code=1)
```

Po zakończeniu ruchu testowego sprawdzany jest stan `_testing_move_check` - jeśli False, oznacza że obiekt nie został pobrany.

### Ruchy z przerwaniem

Flaga `interruption_move` pozwala na wcześniejsze zakończenie ruchu po osiągnięciu podciśnienia:

```python
from avena_commons.event_listener.types import Path, Waypoint

path = Path(
    waypoints=[punkt_A, punkt_B, punkt_C],  # obiekty Waypoint
    interruption_move=True,
    interruption_duration=500  # czas potwierdzenia w ms
)
```

Gdy pompa osiągnie próg:
1. Robot zatrzymuje się
2. Czeka `interruption_duration` ms na potwierdzenie
3. Jeśli próg nadal przekroczony - kończy ruch w tym miejscu
4. Zapisuje aktualną pozycję jako punkt zakończenia

### Nadpisywanie progów ciśnienia

Każdy waypoint może mieć własny próg watchdoga:

```python
from avena_commons.event_listener.types import Waypoint, Path

path = Path(
    waypoints=[
        Waypoint(waypoint=[x1, y1, z1, rx, ry, rz]),
        Waypoint(waypoint=[x2, y2, z2, rx, ry, rz], watchdog_override=True)  # wyłącza watchdog
    ]
)
```

Lub globalnie dla całej ścieżki:
```python
from avena_commons.event_listener.types import Path

path = Path(
    waypoints=[...],  # lista obiektów Waypoint
    collision_override=True  # wyłącza wykrywanie kolizji
)
```

## Monitorowanie ciśnienia

System konwertuje napięcie z czujnika (0-10V) na ciśnienie w kPa przy użyciu:
- filtru mediany (100 próbek) dla stabilności odczytu
- rozdzielczości ADC: 4096 (12-bit)
- zakresu: -100 kPa do 0 kPa (podciśnienie)

Odczyt ciśnienia dostępny przez:
```python
pressure = robot_controller.gripper_pressure()  # zwraca float w kPa
```

Próg ciśnienia ustawia się przez `pressure_threshold` w evencie `pump_on` lub w konfiguracji chwytaka.

## Konfiguracja

Minimalna wymagana struktura konfiguracji:

```python
configuration = {
    "network": {
        "ip_address": "192.168.57.2",
        "port": 8003
    },
    "frequencies": {
        "supervisor": 50,  # Hz - częstotliwość pętli kontrolnej
    },
    "general": {
        "start_position_distance": 200,  # mm - max odległość od startu
        "send_requests_retries": 3,
        "post_collision_safe_timeout_s": 2.0
    },
    "collision_levels": {
        "j1": 10, "j2": 8, "j3": 10,
        "j4": 5, "j5": 3, "j6": 100
    },
    "start_position": {
        "pos1": 177.5, "pos2": -780.0, "pos3": 510.0,
        "pos4": 180.0, "pos5": 0.0, "pos6": 180.0
    },
    "gripper": {
        "enabled": True,
        "weight": 2.05,  # kg
        "tool_coordinates": [0.0, 0.0, 280.0, 0.0, 0.0, 0.0],
        "pressure_threshold": -10,  # kPa
        "hold_threshold_ms": 250,  # czas potwierdzenia chwytania
        "pump_DO": 1,  # Digital Output dla pompy
        "pump_DI": 0,  # Digital Input - czujnik pompy
        "pump_AI": 0,  # Analog Input - czujnik ciśnienia
        "light_DO": 0,  # Digital Output - włącznik światła
        "light_AO": 0   # Analog Output - jasność światła
    }
}
```

### Kluczowe parametry

- `supervisor` - częstotliwość pętli kontrolnej (Hz), określa jak często sprawdzany jest stan robota
- `start_position_distance` - maksymalna dozwolona odległość od pozycji startowej przed rozpoczęciem ruchu
- `hold_threshold_ms` - czas w ms, przez który ciśnienie musi być stabilne aby potwierdzić chwyt
- `post_collision_safe_timeout_s` - timeout na przejechanie bezpiecznej odległości (100mm) po kolizji
- `tool_coordinates` - przesunięcie narzędzia względem flanszy robota [x, y, z, rx, ry, rz]

## Zatrzymywanie i wznawianie

### Pauza

```python
# Przejście do stanu PAUSE
# Robot zatrzymuje ruch, eventy pozostają w kolejce
```

Można wznowić:
```python
# Powrót do stanu RUN
```

### Zatrzymanie miękkie

```python
# Przejście INITIALIZED - robot wyłącza serwomechanizmy ale pozostaje podłączony
```

### Zatrzymanie twarde

```python
# Całkowite rozłączenie, przejście do STOPPED
```

## Typowe scenariusze użycia

### Pobranie obiektu z punktu A do punktu B

```python
from avena_commons.event_listener.types import Waypoint, Path, SupervisorMoveAction, SupervisorPumpAction

# 1. Ruch nad obiekt
move_to_pickup = Event(
    event_type="move_l",
    data=SupervisorMoveAction(
        path=Path(
            waypoints=[Waypoint(waypoint=[x_pickup, y_pickup, z_safe, 180, 0, 180])],
            max_speed=100
        )
    ).to_dict()
)

# 2. Włączenie pompy
pump_on = Event(
    event_type="pump_on",
    data=SupervisorPumpAction(pressure_threshold=-15).to_dict()
)

# 3. Zjazd z chwytaniem (przerywa po osiągnięciu próżni)
pickup = Event(
    event_type="move_l",
    data=SupervisorMoveAction(
        path=Path(
            waypoints=[Waypoint(waypoint=[x_pickup, y_pickup, z_low, 180, 0, 180])],
            interruption_move=True,
            interruption_duration=300
        )
    ).to_dict()
)

# 4. Podniesienie
lift = Event(
    event_type="move_l",
    data=SupervisorMoveAction(
        path=Path(
            waypoints=[Waypoint(waypoint=[x_pickup, y_pickup, z_safe, 180, 0, 180])]
        )
    ).to_dict()
)

# 5. Ruch do miejsca docelowego
move_to_place = Event(
    event_type="move_l",
    data=SupervisorMoveAction(
        path=Path(
            waypoints=[
                Waypoint(waypoint=[x_place, y_place, z_safe, 180, 0, 180]),
                Waypoint(waypoint=[x_place, y_place, z_place, 180, 0, 180])
            ]
        )
    ).to_dict()
)

# 6. Wyłączenie pompy
pump_off = Event(event_type="pump_off")
```

### Test dostępności obiektu

```python
from avena_commons.event_listener.types import Waypoint, Path, SupervisorMoveAction

test_pickup = Event(
    event_type="move_l",
    data=SupervisorMoveAction(
        path=Path(
            waypoints=[Waypoint(waypoint=[x, y, z, 180, 0, 180])],
            testing_move=True
        )
    ).to_dict()
)
# Wynik: success jeśli próżnia osiągnięta, test_failed jeśli nie
```

### Ruch z wyłączoną detekcją kolizji

```python
from avena_commons.event_listener.types import Path, SupervisorMoveAction

# Użyteczne gdy robot musi przejechać przez kontakt z materiałem (np. szczotki)
move_through = Event(
    event_type="move_l",
    data=SupervisorMoveAction(
        path=Path(
            waypoints=[...],  # lista obiektów Waypoint
            collision_override=True
        )
    ).to_dict()
)
```

## Kody błędów w wynikach

System zwraca różne kody błędów w obiektach Result:

- `error_code=1` - test ruchu nieudany (obiekt nieosiągalny)
- `error_code=2` - watchdog pompy zadziałał (utrata próżni)
- `error_code=3` - pompa nie została aktywowana
- `error_code=None, result="failure"` - błąd ogólny (sprawdź `error_message`)

## Podsumowanie

System Supervisor + RobotController zapewnia:

✓ **Sterowanie zdarzeniowe** - asynchroniczne wysyłanie poleceń i odbieranie wyników  
✓ **Automatyczna obsługa kolizji** - wykrywanie, reset i ponawianie ruchu  
✓ **Inteligentny watchdog próżniowy** - monitorowanie chwytania podczas ruchu  
✓ **Płynne trajektorie** - blending dla szybkich i gładkich ruchów  
✓ **Tryby testowe i przerwaniowe** - elastyczne scenariusze pobierania obiektów  
✓ **Walidacja bezpieczeństwa** - sprawdzanie pozycji przed i po ruchu  
✓ **Konfigurowalne poziomy kolizji** - dostosowanie czułości dla każdej osi

Wszystkie operacje są nieblokujące - wysyłasz event i otrzymujesz Result po zakończeniu operacji, co pozwala na budowanie złożonych workflow z równoległymi operacjami wielu robotów.
