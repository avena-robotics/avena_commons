# Implementacja licznika wykonań scenariuszy

## Opracowanie

Zaimplementowano system licznika wykonań scenariuszy w orchestratorze, który zapobiega niekontrolowanemu zapętleniu scenariuszy i chroni sprzęt przed nadmiernym obciążeniem.

### Zmiany w modelu scenariusza

Do modelu `ScenarioModel` dodano nowe opcjonalne pole:
- `max_executions: Optional[int]` - maksymalna liczba wykonań scenariusza

### Nowe metody w klasie Orchestrator

Dodano następujące metody do zarządzania licznikami:

- `get_scenario_execution_count(scenario_name: str) -> int` - pobiera aktualny licznik wykonań
- `increment_scenario_execution_count(scenario_name: str) -> int` - zwiększa licznik wykonań
- `reset_scenario_execution_count(scenario_name: str)` - resetuje licznik dla scenariusza
- `reset_all_scenario_execution_counters()` - resetuje wszystkie liczniki
- `is_scenario_blocked(scenario_name: str) -> bool` - sprawdza czy scenariusz jest zablokowany
- `should_block_scenario_due_to_limit(scenario_name: str, max_executions: int) -> bool` - sprawdza czy scenariusz powinien być zablokowany
- `get_scenarios_execution_status() -> Dict[str, Dict[str, Any]]` - zwraca status wszystkich liczników

### Logika blokowania scenariuszy

1. Scenariusz jest wykonywany normalnie do osiągnięcia limitu `max_executions`
2. Po przekroczeniu limitu scenariusz jest blokowany i nie może być wykonany
3. Zablokowany scenariusz można odblokować wysyłając ACK do orkiestratora
4. ACK resetuje licznik wykonań dla wszystkich scenariuszy

### Integracja z istniejącymi metodami

- `_should_execute_scenario()` - sprawdza czy scenariusz nie jest zablokowany
- `execute_scenario()` - zwiększa licznik wykonań po udanym wykonaniu
- `on_ack()` - resetuje wszystkie liczniki wykonań scenariuszy
- `get_scenarios_status()` - zawiera informacje o licznikach wykonań

### Testy

Utworzono kompletny zestaw testów jednostkowych w pliku `test_scenario_execution_counter.py` obejmujący:
- Podstawowe operacje na licznikach
- Logikę blokowania scenariuszy
- Integrację z modelem Pydantic
- Testowanie ACK i resetowania liczników

### Przykładowy scenariusz

Utworzono przykładowy scenariusz `test_execution_counter.json.example` demonstrujący użycie parametru `max_executions`.

## Podsumowanie

Implementacja systemu licznika wykonań scenariuszy została ukończona zgodnie z wymaganiami. System zapewnia:

1. **Kontrolę wykonań** - ogranicza liczbę wykonań scenariusza do zdefiniowanego limitu
2. **Blokowanie** - automatycznie blokuje scenariusz po przekroczeniu limitu
3. **Reset przez ACK** - umożliwia serwisowe odblokowywanie przez wysłanie ACK
4. **Monitoring** - dostarcza metody do sprawdzania statusu liczników
5. **Testy** - pełne pokrycie testami jednostkowymi
6. **Kompatybilność** - zachowuje pełną kompatybilność z istniejącym kodem

Funkcjonalność jest gotowa do użycia w środowisku produkcyjnym.
