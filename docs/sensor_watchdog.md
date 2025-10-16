## SensorWatchdog — uniwersalny nadzór timeoutów czujników dla VirtualDevice

### Co to jest?
SensorWatchdog to lekki mechanizm, który pozwala rejestrować warunki (np. oczekiwanie na stan czujnika) z limitem czasu. Po spełnieniu warunku zadanie znika, a po przekroczeniu czasu wywoływana jest akcja timeout (domyślnie: log błędu i przejście urządzenia w stan ERROR).

Wszystkie klasy dziedziczące po `VirtualDevice` mają wbudowanego watchdoga i prosty interfejs API.

### Jak to działa w VirtualDevice
- Instancja watchdoga jest tworzona w `VirtualDevice.__init__` jako `self._watchdog`.
- Domyślny handler timeoutu `_on_sensor_timeout` loguje błąd i wywołuje `set_state(VirtualDeviceState.ERROR)`.
- Metoda `tick()` w klasach potomnych jest automatycznie „owinięta”: zanim wykona się właściwa logika urządzenia, zawsze wywołuje się `self._watchdog.tick()`. Jeśli nie ma zadań, watchdog nic nie robi.

### API dla urządzeń potomnych
- `add_sensor_timeout(condition, timeout_s, description, id=None, on_timeout=None, metadata=None) -> str`
  - Rejestruje zadanie, które zakończy się, gdy `condition()` zwróci True albo gdy minie `timeout_s` sekund.
  - `description`: krótki opis zadania (np. "oic1_to_ooc1").
  - `id`: opcjonalny identyfikator (gdy nie podasz, zostanie nadany automatycznie).
  - `on_timeout`: opcjonalny handler (domyślnie `_on_sensor_timeout`).
  - `metadata`: słownik pomocniczy (np. `{ "lane": 1 }`).

- `cancel_sensor_timeout(id: str) -> bool`
  - Usuwa zadanie po `id`. Zwraca True, jeśli usunięto.

Uwaga: Jeśli chcesz rozszerzyć zachowanie po timeout (np. bezpieczne zatrzymanie napędu), nadpisz w klasie potomnej metodę `_on_sensor_timeout(self, task)` lub podaj dedykowany `on_timeout` podczas rejestracji.

### Przykłady użycia
1) Oczekiwanie na krańcówkę górną rolety po starcie ruchu w górę:
```python
task_id = self.add_sensor_timeout(
    condition=lambda: bool(self.__di_sensors["roleta_1_limit"]["top"]),
    timeout_s=15.0,
    description="roleta1_open_to_top",
    metadata={"roleta": 1, "action": "open"},
)
```

2) Oczekiwanie na OOC po wykryciu OIC (FIFO kolejka zadań w środku):
```python
self.add_sensor_timeout(
    condition=lambda: bool(self.__di_sensors["OOC"][0]),
    timeout_s=300.0,
    description="oic1_to_ooc1",
    metadata={"lane": 1},
)
```

3) Nadpisanie domyślnej reakcji na timeout (np. zatrzymanie napędu):
```python
def _on_sensor_timeout(self, task: SensorTimerTask) -> None:
    # custom cleanup
    self.__stop_roleta(0)
    error(f"{self.device_name} - Timeout: {task.description} {task.metadata}", self._message_logger)
    self.set_state(VirtualDeviceState.ERROR)
```

### Wewnętrznie
- Watchdog przechowuje zadania w wewnętrznej kolejce i w `tick()` wykonuje round-robin:
  - jeśli `resolve()` zwróci True → zadanie usuwa się,
  - jeśli przekroczono `deadline` → wywoływany jest `on_timeout()` i zadanie usuwa się,
  - w przeciwnym razie zadanie wraca na koniec kolejki.

### Podsumowanie
- Wspólny, prosty i bezpieczny mechanizm timeoutów we wszystkich urządzeniach.
- Domyślnie: timeout → log + stan ERROR.
- Elastyczny: możliwość własnego handlera i przekazywania metadanych.

