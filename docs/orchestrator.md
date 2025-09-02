# Przegląd Orchestratora
::: avena_commons.orchestrator.orchestrator
    options:
      members_order: source
      show_root_heading: true
      show_source: true

## Wprowadzenie

Orchestrator jest komponentem sterującym scenariuszami zdarzeniowymi w systemie. Odpowiada za ładowanie scenariuszy, rejestrację i wykonywanie akcji, ewaluację warunków oraz współpracę z komponentami zewnętrznymi (np. bazami danych). Działa jako wyspecjalizowany `EventListener`, reagując na zdarzenia i zarządzając przepływem wykonania scenariuszy.

## Klasa Orchestrator

Klasa `Orchestrator` rozszerza `EventListener` i implementuje logikę:

- **Ładowanie konfiguracji**: scenariusze (systemowe i użytkownika), akcje i warunki.
- **Rejestracja akcji**: dynamiczne rejestrowanie akcji z plików oraz możliwość rejestracji zewnętrznych akcji w runtime.
- **Ewaluacja warunków**: poprzez `ConditionFactory` i zagnieżdżone warunki logiczne oraz warunki oparte o stan klientów czy bazę danych.
- **Zarządzanie komponentami**: inicjalizacja, łączenie i health-check komponentów (np. `DatabaseComponent`).
- **Wykonywanie scenariuszy**: z uwzględnieniem priorytetów, cooldownów i limitów współbieżności.
- **FSM**: implementuje wywołania cyklu życia (`on_initializing`, `on_initialized`, `on_starting`, `on_run`, ...).

Przykładowy fragment klasy i inicjalizacji:

```python
class Orchestrator(EventListener):
    """
    Orchestrator sterujący wykonywaniem scenariuszy zdarzeniowych.

    Odpowiada za:
    - ładowanie i sortowanie scenariuszy,
    - rejestrację i wykonywanie akcji,
    - ładowanie, rejestrację i ewaluację warunków,
    - zarządzanie komponentami zewnętrznymi (np. bazami danych),
    - harmonogram i współbieżne uruchamianie scenariuszy z limitami.

    Współpracuje z `EventListener`, nasłuchując i interpretując zdarzenia systemowe.
    """

    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        message_logger: MessageLogger | None = None,
        debug: bool = True,
    ):
        self._message_logger = message_logger
        self._debug = debug

        # Konfiguracja domyślna z komponentami systemu
        self._default_configuration = {
            "clients": {},
            "components": {},
            "builtin_scenarios_directory": str(Path(__file__).parent / "scenarios"),
            "builtin_actions_directory": str(Path(__file__).parent / "actions"),
            "builtin_conditions_directory": str(Path(__file__).parent / "conditions"),
            "scenarios_directory": None,
            "actions_directory": None,
            "conditions_directory": None,
            "max_concurrent_scenarios": 1,
            "smtp": {"host": "", "port": 587, "username": "", "password": "", "starttls": False, "tls": False, "from": "", "max_error_attempts": 3},
            "sms": {"enabled": False, "url": "", "login": "", "password": "", "cert_path": "", "serviceId": 0, "source": "", "max_error_attempts": 3},
        }
```

## Kluczowe funkcjonalności

- **Ładowanie scenariuszy**: z katalogów wbudowanych oraz użytkownika (JSON), walidacja przez modele Pydantic (`ScenarioModel`).
- **Sortowanie wg priorytetu**: scenariusze są porządkowane rosnąco wg `priority` (nowy format) lub `trigger.conditions.priority` (kompatybilność wsteczna).
- **Tryb autonomiczny**: okresowe sprawdzanie warunków i uruchamianie scenariuszy w tle; wsparcie dla scenariuszy manualnych poprzez flagę `manual_run_requested`.
- **Ograniczenia wykonania**: globalny limit `max_concurrent_scenarios`, lokalne `max_concurrent_executions` oraz `cooldown` scenariuszy.
- **Dynamiczne akcje**: automatyczne wykrywanie klas dziedziczących po `BaseAction` i rejestracja w `ActionExecutor`.
- **Warunki**: logika AND/OR/NOT/XOR/NAND/NOR, warunki czasu, stanu klientów i warunki bazodanowe oparte o `DatabaseComponent`.
- **Komponenty zewnętrzne**: inicjalizacja/połączenie/health-check i raportowanie statusu komponentów.
- **Liczniki błędów akcji**: globalne liczniki kolejnych błędów dla typów akcji (np. `send_email`, `send_sms`) z progiem pomijania wysyłek.

## Przepływ scenariuszy

1. **Ładowanie**: podczas `on_initializing` ładowane są komponenty, akcje i scenariusze; warunki rejestrowane są wcześniej.
2. **Monitoring**: metoda `_check_local_data` odpytuje klientów o stan (`CMD_GET_STATE`), następnie `_check_scenarios` ocenia warunki.
3. **Decyzja o uruchomieniu**: sprawdzany jest cooldown, warunki (`ConditionFactory`) i limity współbieżności.
4. **Wykonanie**: scenariusz uruchamiany jest w tle przez `_execute_scenario_with_tracking`, a akcje wykonywane sekwencyjnie przez `ActionExecutor`.
5. **Śledzenie i cleanup**: zapisywana jest historia wykonania, ostatnie czasy, a zakończone zadania są porządkowane.

## Ładowanie i rejestracja

- **Warunki**: `_load_conditions` i `_load_conditions_from_directory` ładują moduły warunków i rejestrują klasy w `ConditionFactory` (pomijając `BaseCondition`).
- **Akcje**: `_load_actions` i `_load_actions_from_directory` rejestrują akcje znalezione w plikach `*_action.py` (z wykluczeniem `base_action.py`).
- **Scenariusze**: `_load_scenarios` oraz `_load_scenarios_from_directory` walidują JSON przy użyciu `ScenarioModel`, ustawiają flagi wewnętrzne i dodają metadane źródła.

Fragment ładowania i rejestracji warunków:

```python
def _load_conditions(self):
    """
    Ładuje warunki z dwóch źródeł:
    1. Systemowe (built-in) z paczki
    2. Użytkownika (custom) z JSON
    """
    try:
        info("🔧 Rozpoczynam ładowanie warunków...", message_logger=self._message_logger)
        builtin_dir = self._configuration.get("builtin_conditions_directory")
        if builtin_dir:
            self._load_conditions_from_directory(Path(builtin_dir), "systemowe")
        custom_dir = self._configuration.get("conditions_directory")
        if custom_dir:
            custom_path = Path(custom_dir)
            if custom_path.exists():
                self._load_conditions_from_directory(custom_path, "użytkownika")
            else:
                warning(f"Katalog warunków użytkownika {custom_path} nie istnieje (pomijam)", message_logger=self._message_logger)
        registered_conditions = ConditionFactory.get_registered_conditions()
        if registered_conditions:
            info(f"🎯 Łącznie zarejestrowanych warunków: {len(registered_conditions)}", message_logger=self._message_logger)
```

Rejestracja klas warunków z katalogu:

```python
def _load_conditions_from_directory(self, conditions_dir: Path, source_type: str):
    if not conditions_dir.exists():
        warning(f"Katalog warunków {source_type} {conditions_dir} nie istnieje", message_logger=self._message_logger)
        return
    py_files = [f for f in conditions_dir.glob("*.py") if f.name != "__init__.py"]
    for py_file in py_files:
        try:
            if source_type == "systemowe":
                module_name = f"avena_commons.orchestrator.conditions.{py_file.stem}"
            else:
                custom_dir = str(conditions_dir).replace("\\", "/").strip("/").replace("/", ".")
                module_name = f"{custom_dir}.{py_file.stem}"
            module = importlib.import_module(module_name)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if inspect.isclass(attr) and issubclass(attr, BaseCondition) and attr != BaseCondition:
                    condition_name = attr_name.replace("Condition", "").lower()
                    ConditionFactory.register_condition_type(condition_name, attr)
                    info(f"✅ Zarejestrowano warunek {source_type}: {condition_name} ({attr_name})", message_logger=self._message_logger)
        except Exception as e:
            error(f"❌ Błąd ładowania warunku {source_type} z {py_file}: {e}", message_logger=self._message_logger)
```

Dynamiczna rejestracja akcji z modułów:

```python
for name, obj in inspect.getmembers(action_module, inspect.isclass):
    if issubclass(obj, BaseAction) and obj != BaseAction and obj.__module__ == module_name:
        try:
            action_instance = obj()
            action_type = self._get_action_type_from_class_name(name)
            if hasattr(action_instance, "action_type"):
                action_type = action_instance.action_type
            self._action_executor.register_action(action_type, action_instance)
            info(f"Zarejestrowano akcję {source_type}: {action_type} ({name})", message_logger=self._message_logger)
        except Exception as e:
            error(f"Błąd tworzenia instancji akcji {source_type} {name}: {e}", message_logger=self._message_logger)
```

Ładowanie scenariuszy z katalogów:

```python
def _load_scenarios(self):
    self._scenarios = OrderedDict()
    builtin_dir = self._configuration.get("builtin_scenarios_directory")
    if builtin_dir:
        self._load_scenarios_from_directory(Path(builtin_dir), "systemowe")
    custom_dir = self._configuration.get("scenarios_directory")
    if custom_dir:
        custom_path = Path(custom_dir)
        if custom_path.exists():
            self._load_scenarios_from_directory(custom_path, "użytkownika")
        else:
            warning(f"Katalog scenariuszy użytkownika {custom_path} nie istnieje (pomijam)", message_logger=self._message_logger)
```

## Komponenty i stan systemu

- **Komponenty**: `_load_components` tworzy i zapisuje np. `DatabaseComponent`; `_initialize_components` wywołuje `initialize`, `connect`, `health_check` i obsługuje błędy.
- **Status**: `get_components_status()` i `get_scenarios_status()` raportują stan komponentów i scenariuszy (w tym priorytety, liczniki wykonań, ostatnie uruchomienia).

Inicjalizacja komponentów po stronie Orchestratora:

```python
async def _initialize_components(self):
    if not self._components:
        info("ℹ️ Brak komponentów do inicjalizacji", message_logger=self._message_logger)
        return
    info(f"🚀 Inicjalizacja {len(self._components)} komponentów...", message_logger=self._message_logger)
    failed_components = []
    for component_name, component in self._components.items():
        try:
            info(f"🔧 Inicjalizacja komponentu: {component_name}", message_logger=self._message_logger)
            if not await component.initialize():
                error(f"❌ Inicjalizacja komponentu '{component_name}' nie powiodła się", message_logger=self._message_logger)
                failed_components.append(component_name)
                continue
            if not await component.connect():
                error(f"❌ Połączenie komponentu '{component_name}' nie powiodło się", message_logger=self._message_logger)
                failed_components.append(component_name)
                continue
            if not await component.health_check():
                warning(f"⚠️ Health check komponentu '{component_name}' nie powiódł się", message_logger=self._message_logger)
            info(f"✅ Komponent '{component_name}' zainicjalizowany i połączony", message_logger=self._message_logger)
        except Exception as e:
            error(
```

Kluczowe metody `DatabaseComponent`:

```python
async def initialize(self) -> bool:
    try:
        self.validate_config()
        info(f"🔧 Inicjalizacja komponentu bazodanowego: {self.name}", message_logger=self._message_logger)
        self._is_initialized = True
        debug(f"✅ Komponent bazodanowy '{self.name}' zainicjalizowany", message_logger=self._message_logger)
        return True
    except Exception as e:
        error(f"❌ Błąd inicjalizacji komponentu bazodanowego '{self.name}': {e}", message_logger=self._message_logger)
        self._is_initialized = False
        return False
```

```python
async def connect(self) -> bool:
    if not self._is_initialized:
        error(f"❌ Komponent bazodanowy '{self.name}' nie jest zainicjalizowany", message_logger=self._message_logger)
        return False
    try:
        info(f"🔌 Nawiązywanie połączenia z bazą danych: {self.name}", message_logger=self._message_logger)
        safe_params = self._connection_params.copy(); safe_params["password"] = "***"
        debug(f"Parametry połączenia: {safe_params}", message_logger=self._message_logger)
        async with self._conn_lock:
            self._connection = await asyncpg.connect(**self._connection_params)
            result = await self._connection.fetchval("SELECT 1")
        if result == 1:
            self._is_connected = True
            info(f"✅ Połączenie z bazą danych '{self.name}' nawiązane pomyślnie", message_logger=self._message_logger)
            return True
        else:
            raise Exception("Test połączenia nie powiódł się")
    except Exception as e:
        error(f"❌ Błąd nawiązywania połączenia z bazą danych '{self.name}': {e}", message_logger=self._message_logger)
        self._is_connected = False
        self._connection = None
        return False
```

## FSM i cykl życia

Orchestrator implementuje metody cyklu życia FSM (`on_initializing`, `on_initialized`, `on_starting`, `on_run`, `on_pausing`, `on_pause`, `on_resuming`, `on_stopping`, `on_stopped`, `on_soft_stopping`, `on_ack`, `on_error`, `on_fault`), zapewniając przewidywalny przepływ uruchamiania, pracy i zatrzymywania.

## Obsługa zdarzeń

Metoda `_analyze_event` przetwarza wybrane zdarzenia systemowe (np. `CMD_GET_STATE`, `CMD_HEALTH_CHECK`), aktualizując `_state` klientów oraz porządkując kolejkę przetwarzania.

```python
async def _analyze_event(self, event: Event) -> bool:
    match event.event_type:
        case "CMD_GET_STATE":
            if event.result is not None:
                old_state = self._state.get(event.source, {}).get("fsm_state", "UNKNOWN")
                new_state = event.data["fsm_state"]
                self._state[event.source]["fsm_state"] = new_state
                self._state[event.source]["error"] = bool(event.data.get("error", False))
                self._state[event.source]["error_message"] = event.data.get("error_message")
                debug(f"📊 _state update: {event.source} FSM: {old_state} → {new_state}", message_logger=self._message_logger)
                self._find_and_remove_processing_event(event)
        case "CMD_HEALTH_CHECK":
            if event.result is not None:
                self._state[event.source]["health_check"] = event.data
                self._find_and_remove_processing_event(event)
        case _:
            pass
    return True
```

## Manualne uruchamianie scenariuszy

Dla scenariuszy z `trigger.type = "manual"` dostępna jest wewnętrzna flaga `manual_run_requested`. Metoda `set_manual_scenario_run_requested(name, value=True)` pozwala oznaczyć scenariusz do jednorazowego uruchomienia podczas następnego sprawdzenia.

```python
def set_manual_scenario_run_requested(self, scenario_name: str, value: bool = True) -> bool:
    if scenario_name not in self._scenarios:
        warning(f"Nie znaleziono scenariusza: {scenario_name}", message_logger=self._message_logger)
        return False
    scenario = self._scenarios[scenario_name]
    trigger_cfg = scenario.get("trigger", {}) or {}
    trigger_type = str(trigger_cfg.get("type", "")).lower()
    if trigger_type != "manual":
        warning(f"Scenariusz '{scenario_name}' nie jest manualny - pomijam ustawienie flagi", message_logger=self._message_logger)
        return False
    internal = scenario.setdefault("_internal", {})
    internal["manual_run_requested"] = bool(value)
    info(f"Ustawiono manual_run_requested={value} dla scenariusza: {scenario_name}", message_logger=self._message_logger)
    return True
```

## Błędy i niezawodność

- **Liczniki błędów akcji**: metody `get_action_error_count`, `increment_action_error_count`, `reset_action_error_count`, `should_skip_action_due_to_errors` pozwalają kontrolować próby wysyłek.
- **Odporność**: błędy ładowania modułów/warunków/akcji/scenariuszy nie zatrzymują całego systemu; błędy w pojedynczych scenariuszach są izolowane.

Globalne liczniki błędów akcji (w `Orchestrator`):

```python
def get_action_error_count(self, action_type: str) -> int:
    return int(self._action_error_counts.get(action_type, 0))

def increment_action_error_count(self, action_type: str) -> int:
    current = int(self._action_error_counts.get(action_type, 0)) + 1
    self._action_error_counts[action_type] = current
    return current

def reset_action_error_count(self, action_type: str) -> None:
    if action_type in self._action_error_counts:
        del self._action_error_counts[action_type]

def should_skip_action_due_to_errors(self, action_type: str, max_attempts: int) -> bool:
    if max_attempts is None:
        return False
    try:
        max_attempts_int = int(max_attempts)
    except Exception:
        max_attempts_int = 0
    if max_attempts_int <= 0:
        return False
    return self.get_action_error_count(action_type) >= max_attempts_int
```

Przykład użycia liczników w akcji e-mail:

```python
except Exception as e:
    had_action_error = True
    error(f"send_email: błąd wysyłki e-mail: {e}", message_logger=context.message_logger)
    raise ActionExecutionError("send_email", f"Błąd wysyłki e-mail: {e}", e)
finally:
    try:
        if success:
            orch.reset_action_error_count(self.action_type)
        elif had_action_error:
            orch.increment_action_error_count(self.action_type)
    except Exception:
        pass
```

Wykonanie scenariusza i delegacja akcji:

```python
scenario = self._scenarios[scenario_name]
context = ActionContext(
    orchestrator=self,
    message_logger=self._message_logger,
    trigger_data=trigger_data,
    scenario_name=scenario_name,
)
actions = scenario.get("actions", [])
for action_config in actions:
    await self._action_executor.execute_action(action_config, context)
```

## Przykładowe użycie (wysokopoziomowe)

```python
from avena_commons.orchestrator.orchestrator import Orchestrator

orch = Orchestrator(name="orch", port=5000, address="127.0.0.1")
# ... integracja z pętlą asynchroniczną oraz cyklem życia FSM
```


