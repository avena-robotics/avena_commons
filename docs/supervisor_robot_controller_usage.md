# Użycie Supervisor, RobotController i gripperów (Vacuum oraz prosty IO)

Ten dokument pokazuje, jak uruchomić warstwę `Supervisor`/`RobotController` w modelu event-driven, skonfigurować chwytaki (grippery), oraz tworzyć własny, prosty gripper, który korzysta wyłącznie z kilku portów Control Box (bez własnej logiki narzędzia i o zerowej masie/wymiarach).

## Wymagania wstępne
- Aktywne środowisko wirtualne i instalacja pakietu w trybie editable.
- Plik `.env` z odpowiednimi portami listenerów, np. `SUPERVISOR_1_LISTENER_PORT=9101`.
- Konfiguracja sieci robota zgodna z Twoim środowiskiem.

## Podstawowe pojęcia
- `Supervisor`: Słucha zdarzeń (`EventListener`) i deleguje do `RobotController` oraz grippera.
- `RobotController`: Implementacja sterowania ruchem i integracji z peryferiami.
- `Gripper`: Obiekt zarządzający IO narzędzia i logiką chwytu. W repozytorium jest m.in. `VacuumGripper`.

## Szybki start: uruchomienie Supervisor z RobotController i VacuumGripper

Poniższy przykład pokazuje, jak przygotować konfigurację i uruchomić `Supervisor` w trybie event-driven z gripperem próżniowym:

```python
from avena_commons.robot.supervisor import Supervisor
from avena_commons.robot.grippers.vacuum_gripper import VacuumGripper, VacuumGripperConfig
from avena_commons.robot.grippers.base import IOMapping

# 1) Zdefiniuj mapowanie IO dla grippera (logical name -> physical pin)
io_map = IOMapping(
    digital_outputs={
        "pump": 0,     # DO0: pompa
        "valve": 1,    # DO1: zawór
        "light": 2,    # DO2: oświetlenie
    },
    digital_inputs={
        "vac_ok": 0,   # DI0: czujnik próżni OK
    },
    analog_inputs={
        "pressure": 0, # AI0: czujnik ciśnienia (0-10V)
    },
    analog_outputs={
        "light_pwm": 0 # AO0: sterowanie oświetleniem (0-100)
    }
)

# 2) Konfiguracja VacuumGripper
vac_cfg = VacuumGripperConfig(
    io_mapping=io_map,
    pressure_threshold_kpa=-10.0,
    hold_debounce_ms=250,
    adc_resolution=4096.0,
    adc_supply_voltage=4.5,
    pressure_buffer_size=100,
    light_voltage_range=(43.0, 0.0),
)

# 3) Supervisor: nazwa, sufiks (instancja), tryb debug
sup = Supervisor(name="sup-robot-1", suffix=1, debug=True, load_state=False)

# Supervisor sam utworzy RobotController w on_initializing/on_initialized.
# VacuumGripper utworzy się automatycznie jeśli konfiguracja grippera jest w configu supervisora,
# albo możesz podać konfigurację ręcznie przez event inicjalizacyjny.
```

### Konfiguracja przez plik supervisor_1_config.json
`Supervisor` może wczytać konfigurację z pliku JSON na podstawie sufiksu instancji. Dla `suffix=1` szukany jest plik `supervisor_1_config.json` (w katalogu roboczym), który może nadpisywać domyślne ustawienia, w tym konfigurację grippera.

Przykład poprawnej konfiguracji VacuumGripper w pliku `supervisor_1_config.json` zgodnej ze strukturą używaną przez `Supervisor` i `VacuumGripperConfig`:

```json
{
    "general": {
        "start_position_distance": 3000
    },
    "gripper": {
        "type": "VacuumGripper",
        "config": {
            "adc_resolution": 4096.0,
            "adc_supply_voltage": 4.5,
            "hold_debounce_ms": 250,
            "io_mapping": {
                "analog_inputs": {
                    "pressure_sensor": 0
                },
                "analog_outputs": {
                    "light": 0
                },
                "digital_inputs": {
                    "pump": 0
                },
                "digital_outputs": {
                    "light_control": 0,
                    "pump": 1
                }
            },
            "light_voltage_range": [43.0, 0.0],
            "mass_coord": [6.141, 1.176, 129.238],
            "pressure_buffer_size": 100,
            "pressure_threshold_kpa": -10.0,
            "tool_coordinates": [0.0, 0.0, 280.0, 0.0, 0.0, 0.0],
            "tool_id": 1,
            "tool_installation": 0,
            "tool_type": 0,
            "weight": 2.05
        }
    }
}
```

Uwagi:
- Pole `gripper.type` musi odpowiadać nazwie klasy (np. `VacuumGripper`). `Supervisor` wykorzystuje dynamiczny import (najpierw `lib/robot/grippers`, potem `avena_commons.robot.grippers`).
- `io_mapping` zawiera nazwy logiczne i numery pinów zgodne z `IOMapping`. Nazwy mogą różnić się od przykładów w kodzie — ważne, aby były spójne w Twoich eventach.
- Parametry narzędzia (`tool_coordinates`, `weight`, `mass_coord`, itd.) są przekazywane przez `RobotToolConfig` w gripperze; jeśli używasz prostego IO-only grippera, możesz pozostawić je z wartościami zerowymi lub pominąć, jeśli klasa na to pozwala.

Ładowanie konfiguracji odbywa się podczas inicjalizacji `Supervisor` (`on_initializing`), gdzie wartości z pliku nadpisują domyślną konfigurację.

## Konfiguracja `RobotController` przez Supervisor
`Supervisor` posiada domyślną konfigurację sieci, częstotliwości, poziomów kolizji i pozycji startowej (zob. `supervisor.py`). Kluczowe fragmenty:
- `network.ip_address`, `network.port`: IP robota i port kontrolera.
- `frequencies.supervisor`: częstotliwość pętli supervisora.
- `general.start_position_distance`: limit dystansu akceptacji pozycji startowej.
- `general.post_collision_safe_timeout_s`: czas bezpieczeństwa po kolizji.
- `collision_levels`: poziomy antykolizji `j1`…`j6`.
- `start_position`: domyślna pozycja startowa (j1…j6).

Możesz nadpisać te wartości poprzez konfigurację ładowaną do `Supervisor` (np. z pliku JSON) lub zdarzenie inicjalizacyjne.

## VacuumGripper: obsługiwane zdarzenia i przepływ
`VacuumGripper`:
- Używa `IOManager` i `ToolIO` do operacji IO.
- Posiada kalkulator ciśnienia z filtrem mediany (`PressureCalculator`).
- Monitoruje stan próżni i wspiera watchdog.

Przykładowe zdarzenia:
- `pump_on` / `pump_off`
- `light_on` z parametrem intensywności (0-100) / `light_off`
- `light_control`

Podczas ruchu ścieżki, `Supervisor` wywołuje hooki grippera (`on_path_start`, `on_waypoint_reached`, `on_path_end`) oraz przekazuje aktualny stan IO (`update_io_state`). Gripper może weryfikować zakończenie ścieżki (`validate_path_completion`).

## Prosty gripper IO-only (zerowa masa/wymiary, bez logiki narzędzia)
Czasem potrzebny jest gripper, który tylko wywołuje kilka komend IO, bez modelowania narzędzia i bez dodatkowej logiki. Poniżej przykład minimalnej implementacji, który:
- Definiuje kilka poleceń obsługiwanych jako eventy,
- Korzysta z `IOManager` i mapowania IO,
- Nie raportuje żadnych dodatkowych właściwości narzędzia (masa/wymiary ~ 0).

```python
# File: your_module/simple_io_gripper.py
from typing import Any, Dict, Optional

from avena_commons.util.logger import debug, warning
from avena_commons.robot.grippers.base import BaseGripper, EventResult, GripperError, IOMapping, RobotToolConfig
from avena_commons.robot.grippers.io_manager import IOManager
from pydantic import Field

class SimpleIOGripperConfig(RobotToolConfig):
    """Minimalna konfiguracja dla prostego grippera IO.
    Masa/wymiary traktujemy jako zerowe (domyślne RobotToolConfig mogą być 0),
    definiujemy tylko mapowanie IO.
    """
    io_mapping: IOMapping = Field(..., description="Mapowanie nazw logicznych na piny")

class SimpleIOGripper(BaseGripper):
    """Prosty gripper korzystający wyłącznie z kilku portów Control Box.

    Obsługuje podstawowe zdarzenia:
    - do_on:<name>, do_off:<name>  — ustaw DO high/low dla wskazanego logicznego portu
    - ao_set:<name>:<value>        — ustaw AO (0-100)
    - di_get:<name>                — odczyt DI, zwracany w EventResult.data
    - ai_get:<name>                — odczyt AI, zwracany w EventResult.data
    """
    def __init__(self, robot, config: SimpleIOGripperConfig, message_logger=None):
        super().__init__(robot, config, message_logger)
        self._io_manager = IOManager(robot, config.io_mapping, message_logger)
        self._last_state: Dict[str, Any] = {}

    def get_robot_config(self) -> RobotToolConfig:
        return self._config

    def get_io_mapping(self) -> IOMapping:
        return self._config.io_mapping

    def get_supported_events(self) -> set[str]:
        return {
            "do_on", "do_off",
            "ao_set",
            "di_get", "ai_get",
        }

    def on_initialize(self) -> None:
        debug("SimpleIOGripper initialized")

    def on_enable(self) -> None:
        debug("SimpleIOGripper enabled")

    def on_disable(self) -> None:
        debug("SimpleIOGripper disabled")

    def update_io_state(self, io_state: dict) -> None:
        self._io_manager.update_io_state(io_state)

    def process_event(self, event) -> EventResult:
        action = getattr(event, "action", None)
        if not action or not hasattr(action, "type"):
            return EventResult(ok=False, message="Invalid event action")

        t = action.type
        # Parametry przekazywane np. w event.action.params
        params = getattr(action, "params", {}) or {}

        try:
            if t == "do_on":
                name = params.get("name")
                self._io_manager.set_do(name, True)
                return EventResult(ok=True, message=f"DO '{name}'=ON")
            elif t == "do_off":
                name = params.get("name")
                self._io_manager.set_do(name, False)
                return EventResult(ok=True, message=f"DO '{name}'=OFF")
            elif t == "ao_set":
                name = params.get("name")
                value = float(params.get("value", 0))
                self._io_manager.set_ao(name, value)
                return EventResult(ok=True, message=f"AO '{name}'={value}")
            elif t == "di_get":
                name = params.get("name")
                v = self._io_manager.get_di(name)
                return EventResult(ok=True, data={"di": {name: v}}, message=f"DI '{name}'={v}")
            elif t == "ai_get":
                name = params.get("name")
                v = self._io_manager.get_ai(name)
                return EventResult(ok=True, data={"ai": {name: v}}, message=f"AI '{name}'={v}")
            else:
                warning(f"Unsupported event type: {t}")
                return EventResult(ok=False, message=f"Unsupported event type: {t}")
        except GripperError as e:
            return EventResult(ok=False, message=str(e))

    def get_state(self) -> Dict[str, Any]:
        return dict(self._last_state)

    def check_errors(self) -> Optional[GripperError]:
        return None
```

### Użycie prostego grippera z Supervisor
W zależności od mechanizmu tworzenia gripperów w `Supervisor` (dynamiczny import na podstawie nazwy klasy `gripper_type`), możesz:
- Dodać `SimpleIOGripper` do własnego modułu dostępnego w ścieżce `lib/robot/grippers` (lokalny override), lub
- Umieścić go w `avena_commons.robot.grippers` i wskazać `gripper_type="SimpleIOGripper"` w konfiguracji.

Przykładowa konfiguracja fragmentu grippera (JSON lub dict) przekazywana do `Supervisor`:
```json
{
  "gripper": {
    "type": "SimpleIOGripper",
    "config": {
      "io_mapping": {
        "digital_outputs": {"pump": 0, "valve": 1},
        "digital_inputs": {"vac_ok": 0},
        "analog_inputs": {"pressure": 0},
        "analog_outputs": {"light_pwm": 0}
      }
            "tool_coordinates": [0, 0, 0, 0, 0, 0],
            "weight": 0.0,
            "mass_coord": [0, 0, 0]
    }
  }
}
```

### Wysyłanie zdarzeń do prostego grippera
```python
from avena_commons.event_listener import Event
from avena_commons.event_listener.types import SupervisorGripperAction

# Włącz DO o nazwie logical "pump"
ev_on = Event(action=SupervisorGripperAction(type="do_on", params={"name": "pump"}))
await sup.on_event(ev_on)

# Ustaw AO 70% na "light_pwm"
ev_ao = Event(action=SupervisorGripperAction(type="ao_set", params={"name": "light_pwm", "value": 70}))
await sup.on_event(ev_ao)

# Odczytaj DI "vac_ok"
ev_di = Event(action=SupervisorGripperAction(type="di_get", params={"name": "vac_ok"}))
await sup.on_event(ev_di)
```

## Uruchamianie i testowanie
- Zbuduj pakiet, aby upewnić się, że konfiguracja i importy są poprawne:

```bash
python -m build
```

- W trakcie rozwoju możesz korzystać z istniejących skryptów w `tests/` do wywoływania zdarzeń i inspekcji logów.

## Dobre praktyki
- Mapowanie IO trzymaj w konfiguracji, a nie w kodzie.
- Zdarzenia projektuj jako jednoznaczne komendy (nazwy typu + parametry).
- Utrzymuj spójne logowanie (`debug/info/warning/error`) dla łatwego śledzenia.
- Dbaj o walidację (Pydantic Config, typy, zakresy) i o testy jednostkowe.

---