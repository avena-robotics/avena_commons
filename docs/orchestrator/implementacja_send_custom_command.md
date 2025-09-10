# Implementacja akcji send_custom_command

## Opracowanie

Została zaimplementowana nowa akcja `SendCustomCommandAction` dla systemu Orchestrator, która umożliwia wysyłanie poleceń niestandardowych z dowolnymi danymi do komponentów systemu.

### Nowe komponenty:

1. **`send_custom_command_action.py`** - główna implementacja akcji
   - Obsługuje wszystkie selektory celów jak oryginalna akcja `send_command`
   - Umożliwia przekazywanie dowolnych danych w polu `data`
   - Zawiera pełną walidację i obsługę błędów
   - Implementuje rozwiązywanie zmiennych szablonowych

2. **Rozszerzenie ActionExecutor** - rejestracja nowej akcji
   - Dodano import `SendCustomCommandAction`
   - Zarejestrowano akcję pod typem `send_custom_command`

3. **Rozszerzenie __init__.py** - eksport modułu
   - Dodano eksport `SendCustomCommandAction` 

4. **Testy jednostkowe** - pełna weryfikacja funkcjonalności
   - Test podstawowej funkcjonalności
   - Test rozwiązywania zmiennych szablonowych  
   - Test obsługi błędów
   - Test selektora `@all`

### Możliwości nowej akcji:

#### Selektory celów (identyczne jak w send_command):
- `client` - pojedynczy serwis
- `group` - jedna grupa serwisów
- `groups` - wiele grup serwisów  
- `target: "@all"` - wszystkie serwisy

#### Nowe pola:
- `command` - nazwa polecenia niestandardowego
- `data` - słownik z dowolnymi danymi dla polecenia

#### Przykłady użycia w scenariuszach:

```json
{
  "type": "send_custom_command",
  "client": "io",
  "command": "CUSTOM_CALIBRATE_SENSOR",
  "data": {
    "sensor_id": 42,
    "calibration_values": [1.0, 2.5, 3.7],
    "timeout": 30,
    "mode": "precision"
  },
  "description": "Kalibracja sensora z niestandardowymi parametrami"
}
```

```json
{
  "type": "send_custom_command",
  "group": "supervisors",
  "command": "SET_POSITION", 
  "data": {
    "x": 100.5,
    "y": 200.3,
    "z": 15.0,
    "speed": 0.8
  },
  "description": "Ustawienie pozycji dla wszystkich supervisorów"
}
```

```json
{
  "type": "send_custom_command",
  "target": "@all",
  "command": "GLOBAL_STATUS_UPDATE",
  "data": {
    "status": "maintenance_mode",
    "timestamp": "{{ trigger.timestamp }}",
    "message": "System entering maintenance"
  },
  "description": "Globalna aktualizacja statusu"
}
```

### Zachowana kompatybilność:

- Oryginalna akcja `send_command` pozostaje niezmieniona
- Wszystkie istniejące scenariusze działają bez zmian
- Identyczne selektory celów jak w oryginalnej akcji
- Ten sam mechanizm wysyłania przez `orchestrator._event()`

### Walidacja i obsługa błędów:

- Sprawdzanie obowiązkowego pola `command`
- Walidacja istnienia komponentów docelowych
- Obsługa błędów komunikacji z komponentami
- Informacyjne komunikaty błędów

## Podsumowanie

Implementacja została wykonana zgodnie z najlepszymi praktykami projektu:
- Nowa akcja zamiast modyfikacji istniejącej (bezpieczeństwo)
- Pełna dokumentacja w stylu Google (język polski)
- Nagłówek AI dla każdego pliku
- Obsługa zmiennych szablonowych
- Kompletne testy jednostkowe
- Zachowana kompatybilność wsteczna

Nowa akcja `send_custom_command` rozszerza możliwości Orchestratora o wysyłanie poleceń niestandardowych z dowolnymi danymi, zachowując pełną kompatybilność z istniejącym systemem.
