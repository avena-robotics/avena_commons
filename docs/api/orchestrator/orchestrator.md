# Przegląd Orchestratora
:::: orchestrator
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

## Komponenty i stan systemu

- **Komponenty**: `_load_components` tworzy i zapisuje np. `DatabaseComponent`; `_initialize_components` wywołuje `initialize`, `connect`, `health_check` i obsługuje błędy.
- **Status**: `get_components_status()` i `get_scenarios_status()` raportują stan komponentów i scenariuszy (w tym priorytety, liczniki wykonań, ostatnie uruchomienia).

## FSM i cykl życia

Orchestrator implementuje metody cyklu życia FSM (`on_initializing`, `on_initialized`, `on_starting`, `on_run`, `on_pausing`, `on_pause`, `on_resuming`, `on_stopping`, `on_stopped`, `on_soft_stopping`, `on_ack`, `on_error`, `on_fault`), zapewniając przewidywalny przepływ uruchamiania, pracy i zatrzymywania.

## Obsługa zdarzeń

Metoda `_analyze_event` przetwarza wybrane zdarzenia systemowe (np. `CMD_GET_STATE`, `CMD_HEALTH_CHECK`), aktualizując `_state` klientów oraz porządkując kolejkę przetwarzania.

## Manualne uruchamianie scenariuszy

Dla scenariuszy z `trigger.type = "manual"` dostępna jest wewnętrzna flaga `manual_run_requested`. Metoda `set_manual_scenario_run_requested(name, value=True)` pozwala oznaczyć scenariusz do jednorazowego uruchomienia podczas następnego sprawdzenia.

## Błędy i niezawodność

- **Liczniki błędów akcji**: metody `get_action_error_count`, `increment_action_error_count`, `reset_action_error_count`, `should_skip_action_due_to_errors` pozwalają kontrolować próby wysyłek.
- **Odporność**: błędy ładowania modułów/warunków/akcji/scenariuszy nie zatrzymują całego systemu; błędy w pojedynczych scenariuszach są izolowane.

## Przykładowe użycie (wysokopoziomowe)

```python
from avena_commons.orchestrator.orchestrator import Orchestrator

orch = Orchestrator(name="orch", port=5000, address="127.0.0.1")
# ... integracja z pętlą asynchroniczną oraz cyklem życia FSM
```


