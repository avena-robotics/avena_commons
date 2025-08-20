# Scenariusze Uruchamiania Usług (@all) - Orchestrator

## Przegląd

Plik `run_services.yaml` zawiera scenariusze do zarządzania wszystkimi usługami systemu oznaczonymi jako `@all`. Scenariusze te umożliwiają jednoczesne uruchamianie, zatrzymywanie i restart wszystkich komponentów systemu.

## Dostępne Scenariusze

### 1. 🚀 Uruchomienie wszystkich usług systemu (@all)

**Pełny scenariusz startowy** - inicjalizuje i uruchamia wszystkie komponenty systemu.

**Kroki:**
1. 📊 Sprawdzenie aktualnego stanu wszystkich komponentów
2. ⚙️ Inicjalizacja wszystkich komponentów (`CMD_INITIALIZE` → `INITIALIZED`)
3. 🔄 Uruchomienie wszystkich komponentów (`CMD_RUN` → `RUN`)
4. ✅ Weryfikacja końcowa

**Użycie:**
```bash
curl -X POST http://127.0.0.1:8000/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "admin",
    "destination": "orchestrator",
    "event_type": "EXECUTE_SCENARIO", 
    "data": {
      "scenario_name": "Uruchomienie wszystkich usług systemu (@all)"
    }
  }'
```

---

### 2. ⚡ Szybkie uruchomienie usług (@all) - bez inicjalizacji

**Szybki start** - uruchamia komponenty które są już zainicjalizowane.

**Kroki:**
1. 🔄 Bezpośrednie uruchomienie (`CMD_RUN` → `RUN`)
2. ✅ Potwierdzenie sukcesu

**Użycie:**
```bash
curl -X POST http://127.0.0.1:8000/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "admin",
    "destination": "orchestrator",
    "event_type": "EXECUTE_SCENARIO",
    "data": {
      "scenario_name": "Szybkie uruchomienie usług (@all) - bez inicjalizacji"
    }
  }'
```

---

### 3. ⏹️ Zatrzymanie wszystkich usług (@all)

**Bezpieczne zatrzymanie** - zatrzymuje wszystkie komponenty systemu.

**Kroki:**
1. 🛑 Wysłanie komendy zatrzymania (`CMD_STOP` → `STOPPED`)
2. ✅ Potwierdzenie zatrzymania

**Użycie:**
```bash
curl -X POST http://127.0.0.1:8000/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "admin",
    "destination": "orchestrator",
    "event_type": "EXECUTE_SCENARIO",
    "data": {
      "scenario_name": "Zatrzymanie wszystkich usług (@all)"
    }
  }'
```

---

### 4. 🔄 Restart wszystkich usług (@all)

**Pełny restart** - zatrzymuje i ponownie uruchamia wszystkie komponenty.

**Kroki:**
1. 1️⃣ Zatrzymanie wszystkich usług (`CMD_STOP` → `STOPPED`)
2. 2️⃣ Inicjalizacja wszystkich usług (`CMD_INITIALIZE` → `INITIALIZED`)
3. 3️⃣ Uruchomienie wszystkich usług (`CMD_RUN` → `RUN`)
4. ✅ Potwierdzenie restartu

**Użycie:**
```bash
curl -X POST http://127.0.0.1:8000/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "admin",
    "destination": "orchestrator",
    "event_type": "EXECUTE_SCENARIO",
    "data": {
      "scenario_name": "Restart wszystkich usług (@all)"
    }
  }'
```

## Komponenty Systemu

Scenariusze operują na wszystkich komponentach zdefiniowanych w konfiguracji orkiestratora:

| Komponent | Port | Grupa | Opis |
|-----------|------|-------|------|
| `io` | 8001 | `base_io` | Warstwa wejść/wyjść |
| `supervisor_1` | 8002 | `supervisors` | Supervisor #1 |
| `supervisor_2` | 8003 | `supervisors` | Supervisor #2 |
| `munchies_algo` | 8004 | `main_logic` | Główna logika biznesowa |

## Komendy FSM i Stany

### Komendy używane w scenariuszach:
- `CMD_INITIALIZE` - Inicjalizuje komponent
- `CMD_RUN` - Uruchamia komponent  
- `CMD_STOP` - Zatrzymuje komponent

### Stany docelowe:
- `INITIALIZED` - Komponent zainicjalizowany
- `RUN` - Komponent uruchomiony i działający
- `STOPPED` - Komponent zatrzymany

## Timeouty

| Operacja | Timeout | Uzasadnienie |
|----------|---------|--------------|
| Inicjalizacja (@all) | 60s | Inicjalizacja może wymagać więcej czasu |
| Uruchomienie (@all) | 30s | Uruchomienie powinno być szybsze |
| Zatrzymanie (@all) | 45s | Bezpieczne zamknięcie może trwać |

## Programowe Wykonywanie Scenariuszy

### Python API

```python
import asyncio
from avena_commons.orchestrator.orchestrator import Orchestrator

async def run_all_services():
    orchestrator = Orchestrator(
        name="my_orchestrator",
        port=8000,
        address="127.0.0.1"
    )
    
    # Wykonaj scenariusz uruchomienia
    result = await orchestrator.execute_scenario(
        "Uruchomienie wszystkich usług systemu (@all)",
        trigger_data={
            "source": "automation_script",
            "event_type": "SCHEDULED_START"  
        }
    )
    
    if result:
        print("✅ Wszystkie usługi uruchomione pomyślnie!")
    else:
        print("❌ Błąd podczas uruchamiania usług")

# Uruchom
asyncio.run(run_all_services())
```

### Test Script

```python
# Plik: test_run_services.py
import requests
import json
import time

def trigger_scenario(scenario_name):
    """Wyzwala scenariusz przez HTTP."""
    
    payload = {
        "source": "test_script",
        "destination": "orchestrator", 
        "event_type": "EXECUTE_SCENARIO",
        "data": {
            "scenario_name": scenario_name
        }
    }
    
    response = requests.post(
        "http://127.0.0.1:8000/event",
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload)
    )
    
    if response.status_code == 200:
        print(f"✅ Scenariusz '{scenario_name}' wyzwolony pomyślnie")
        return True
    else:
        print(f"❌ Błąd wyzwalania scenariusza: {response.status_code}")
        return False

# Przykłady użycia
if __name__ == "__main__":
    # Uruchom wszystkie usługi
    trigger_scenario("Uruchomienie wszystkich usług systemu (@all)")
    
    time.sleep(5)  # Poczekaj na zakończenie
    
    # Sprawdź status (jeśli masz endpoint statusu)
    print("System powinien być teraz uruchomiony!")
```

## Monitorowanie i Debugging

### Sprawdzenie Stanu Komponentów

```bash
# Sprawdź stan pojedynczego komponentu
curl -X POST http://127.0.0.1:8001/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "admin",
    "destination": "io",
    "event_type": "CMD_GET_STATE",
    "data": {}
  }'
```

### Logi Orkiestratora

Orkiestrator loguje wykonanie scenariuszy z emoji dla lepszej czytelności:

```
[INFO] 🚀 Rozpoczynam uruchamianie wszystkich usług systemu (@all)
[INFO] 📊 Sprawdzam aktualny stan wszystkich komponentów...
[INFO] ⚙️ Inicjalizuję wszystkie komponenty (@all) równolegle...
[INFO] Wysłano komendę 'CMD_INITIALIZE' do komponentu 'io'
[INFO] Wysłano komendę 'CMD_INITIALIZE' do komponentu 'supervisor_1'
[INFO] Wysłano komendę 'CMD_INITIALIZE' do komponentu 'supervisor_2'
[INFO] Wysłano komendę 'CMD_INITIALIZE' do komponentu 'munchies_algo'
[INFO] 🔄 Uruchamiam wszystkie komponenty (@all) - przejście do stanu RUN...
[SUCCESS] ✅ Wszystkie usługi systemu zostały pomyślnie uruchomione!
```

## Rozwiązywanie Problemów

### Częste Problemy

1. **Timeout podczas wait_for_state**
   - Sprawdź czy komponenty rzeczywiście działają na podanych portach
   - Zwiększ timeout w scenariuszu jeśli potrzeba

2. **Scenariusz nie został znaleziony** 
   - Sprawdź czy `run_services.yaml` jest w katalogu `scenarios/`
   - Sprawdź literówki w nazwie scenariusza

3. **Komponenty nie odpowiadają**
   - Sprawdź czy usługi są uruchomione na portach 8001-8004
   - Sprawdź łączność sieciową

### Debug Commands

```bash
# Sprawdź załadowane scenariusze
PYTHONPATH=src python3 -c "
from avena_commons.orchestrator.orchestrator import Orchestrator
from unittest.mock import Mock
orch = Orchestrator('test', 9999, '127.0.0.1', Mock())
print('Załadowane scenariusze:')
for name in orch._scenarios.keys():
    print(f'  - {name}')
"

# Sprawdź konfigurację komponentów
PYTHONPATH=src python3 -c "
from avena_commons.orchestrator.orchestrator import Orchestrator
from unittest.mock import Mock
orch = Orchestrator('test', 9999, '127.0.0.1', Mock())
import json
print('Komponenty:')
print(json.dumps(orch._configuration['clients'], indent=2))
"
```

## Zalety Scenariuszy @all

1. **Jednoczesność** - Wszystkie komponenty operowane równolegle
2. **Atomowość** - Albo wszystkie się udają, albo cały scenariusz kończy się błędem
3. **Prostota** - Jeden scenariusz zamiast ręcznego zarządzania każdym komponentem
4. **Niezawodność** - Wbudowane timeouty i obsługa błędów
5. **Czytelność** - Emoji i jasne komunikaty w logach
6. **Testowalność** - Pełne pokrycie testami jednostkowymi

## Następne Kroki

- 📈 **Monitoring**: Dodaj endpoint do sprawdzania stanu wszystkich komponentów
- 🔔 **Alerting**: Powiadomienia przy błędach scenariuszy
- 📊 **Metryki**: Zbieranie czasu wykonania scenariuszy
- 🎯 **Warunkowe scenariusze**: Scenariusze reagujące na stan systemu 