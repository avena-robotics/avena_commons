# System Scenariuszy Orchestratora

## Przegląd

System scenariuszy umożliwia Orchestratorowi wykonywanie złożonych, wieloetapowych operacji na komponentach systemu zgodnie z dokumentacją architektoniczną. Scenariusze są zapisane w plikach YAML i automatycznie ładowane przy starcie Orchestratora.

## Struktura Plików

```
avena_commons/
├── scenarios/
│   └── system_startup.yaml      # Scenariusz startowy systemu
├── src/avena_commons/orchestrator/
│   └── orchestrator.py          # Rozszerzony Orchestrator
└── requirements_orchestrator.txt   # Dodatkowe zależności
```

## Instalacja Zależności

```bash
pip install -r avena_commons/requirements_orchestrator.txt
```

## Scenariusz Startowy

Plik `avena_commons/scenarios/system_startup.yaml` zawiera scenariusz przeprowadzający komponenty ze stanu **STOPPED** do stanu **RUN** z zachowaniem prawidłowej kolejności:

### Kolejność uruchamiania:
1. **io** - warstwa I/O (podstawa systemu)
2. **supervisor_1, supervisor_2** - supervisory (zależne od I/O)  
3. **munchies_algo** - główna logika biznesowa (uruchamiana jako ostatnia)
4. Wszystkie komponenty przechodzą do stanu **RUN**

### Kroki scenariusza:
- **KROK 1:** Inicjalizacja warstwy I/O (`CMD_INITIALIZE` → `INITIALIZED`)
- **KROK 2:** Inicjalizacja supervisorów (`CMD_INITIALIZE` → `INITIALIZED`) 
- **KROK 3:** Inicjalizacja munchies_algo (`CMD_INITIALIZE` → `INITIALIZED`)
- **KROK 4:** Uruchomienie wszystkich komponentów (`CMD_RUN` → `RUN`)

## Sposoby Uruchomienia Scenariusza

### 1. Przez Wydarzenie HTTP (Zalecane)

```python
# Użyj przygotowanego skryptu
python example_trigger_scenario.py

# Lub wyślij wydarzenie bezpośrednio:
curl -X POST http://127.0.0.1:8000/event \
  -H "Content-Type: application/json" \
  -d '{
    "source": "manual_trigger",
    "destination": "orchestrator", 
    "event_type": "EXECUTE_SCENARIO",
    "data": {
      "scenario_name": "Scenariusz startowy systemu - STOPPED do RUN"
    }
  }'
```

### 2. Przez Test Programistyczny

```python
# Użyj przygotowanego skryptu testowego
python test_orchestrator_scenario.py
```

## Konfiguracja Komponentów

Orchestrator ma wbudowaną domyślną konfigurację komponentów:

```python
"components": {
    "io": {"address": "127.0.0.1", "port": 8001, "group": "base_io"},
    "supervisor_1": {"address": "127.0.0.1", "port": 8002, "group": "supervisors"}, 
    "supervisor_2": {"address": "127.0.0.1", "port": 8003, "group": "supervisors"},
    "munchies_algo": {"address": "127.0.0.1", "port": 8004, "group": "main_logic"}
}
```

## Tworzenie Nowych Scenariuszy

### Format YAML:

```yaml
- name: "Nazwa scenariusza"
  trigger:
    type: "manual"
    description: "Opis wyzwalacza"

  actions:
    - type: "log_event"
      level: "info"
      message: "Komunikat do logów"
      
    - type: "send_command"
      component: "nazwa_komponentu"        # pojedynczy komponent
      # components: ["komp1", "komp2"]    # lub lista komponentów  
      command: "CMD_INITIALIZE"
      
    - type: "wait_for_state"
      component: "nazwa_komponentu"        # pojedynczy komponent
      # components: ["komp1", "komp2"]    # lub lista komponentów
      target_state: "INITIALIZED"
      timeout: "30s"                       # 30s, 2m, itd.
```

### Dostępne Akcje:

- **log_event:** Zapisuje komunikat do logów (`level`: info, warning, error, success)
- **send_command:** Wysyła komendę FSM do komponentów (`CMD_INITIALIZE`, `CMD_RUN`, itd.)
- **wait_for_state:** Czeka aż komponenty osiągną określony stan z timeout

## Monitorowanie

### Sprawdzenie stanu Orchestratora:
```bash
python example_trigger_scenario.py status
```

### Logi scenariusza:
Wszystkie akcje scenariusza są logowane przez Orchestratora z odpowiednimi poziomami:
- **INFO:** Postęp scenariusza
- **SUCCESS:** Pomyślne zakończenie  
- **ERROR:** Błędy i timeouty

## Rozszerzenia

System został zaprojektowany z myślą o łatwym rozszerzaniu:

1. **Dodawanie nowych akcji:** Rozszerz metodę `_execute_action()` w Orchestratorze
2. **Nowe triggery:** Dodaj obsługę innych wyzwalaczy oprócz `manual`
3. **Grupowanie komponentów:** Wykorzystaj pole `group` z konfiguracji dla operacji grupowych
4. **Warunki i logika:** Dodaj conditional actions w przyszłości

## Przykład Użycia w Produkcji

1. Uruchom Orchestrator: `python -m avena_commons.orchestrator.orchestrator`
2. Uruchom komponenty systemu na odpowiednich portach (8001-8004)
3. Wyślij żądanie uruchomienia scenariusza przez HTTP API
4. Monitoruj logi Orchestratora w czasie rzeczywistym 