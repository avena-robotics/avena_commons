# System Dynamicznego Ładowania Akcji - Orchestrator

## Przegląd

System dynamicznego ładowania akcji w orkiestratorze automatycznie wykrywa i rejestruje wszystkie dostępne akcje podczas inicjalizacji. Dzięki temu można łatwo dodawać nowe akcje bez modyfikacji kodu orkiestratora.

## Jak to działa

### 1. Automatyczne wykrywanie akcji

Podczas inicjalizacji orkiestrator:

1. **Przeszukuje katalog `actions/`** w poszukiwaniu plików o nazwie `*_action.py`
2. **Importuje dynamicznie** znalezione moduły
3. **Wykrywa klasy** dziedziczące po `BaseAction`
4. **Tworzy instancje** znalezionych klas akcji
5. **Rejestruje je** w `ActionExecutor` z automatycznie wygenerowanymi typami

### 2. Konwersja nazw klas na typy akcji

System automatycznie konwertuje nazwy klas na typy akcji używane w YAML:

```python
LogAction           -> "log_event"
SendCommandAction   -> "send_command"  
WaitForStateAction  -> "wait_for_state"
TestAction          -> "test"
CustomProcessAction -> "custom_process"
```

### 3. Niestandardowe typy akcji

Akcja może zdefiniować własny typ poprzez atrybut `action_type`:

```python
class MyAction(BaseAction):
    action_type = "my_custom_type"  # Zostanie zarejestrowana jako "my_custom_type"
    
    async def execute(self, action_config, context):
        # implementacja akcji
        pass
```

## Konfiguracja

### Katalog akcji

Domyślnie akcje są ładowane z katalogu `avena_commons/orchestrator/actions/`. Można to zmienić w konfiguracji orkiestratora:

```python
orchestrator._configuration["actions_directory"] = "/path/to/custom/actions"
```

## Tworzenie nowych akcji

### 1. Utwórz plik z akcją

Nazwa pliku musi kończyć się na `_action.py` (np. `my_custom_action.py`):

```python
"""
Niestandardowa akcja dla orkiestratora.
"""

from typing import Any, Dict
from avena_commons.util.logger import info
from .base_action import ActionContext, BaseAction, ActionExecutionError

class MyCustomAction(BaseAction):
    """
    Opis twojej niestandardowej akcji.
    """
    
    # Opcjonalnie: niestandardowy typ akcji
    # action_type = "my_special_action"
    
    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Any:
        """
        Implementacja akcji.
        
        Args:
            action_config: Konfiguracja z pliku YAML
            context: Kontekst wykonania z orchestratorem i loggerem
            
        Returns:
            Wynik wykonania akcji (opcjonalny)
            
        Raises:
            ActionExecutionError: W przypadku błędu wykonania
        """
        
        # Pobierz parametry z konfiguracji
        param1 = action_config.get("param1", "default_value")
        param2 = action_config.get("param2", 42)
        
        # Rozwiąż zmienne szablonowe (np. {{ trigger.source }})
        resolved_param = self._resolve_template_variables(param1, context)
        
        # Loguj działanie
        info(
            f"Wykonuję MyCustomAction z parametrami: {param1}, {param2}",
            message_logger=context.message_logger
        )
        
        # Twoja logika tutaj
        try:
            # ... implementacja ...
            result = {"status": "success", "data": resolved_param}
            
        except Exception as e:
            raise ActionExecutionError(
                "my_custom", f"Błąd w MyCustomAction: {str(e)}", e
            )
        
        return result
```

### 2. Akcja zostanie automatycznie zarejestrowana

Po umieszczeniu pliku w katalogu `actions/`, akcja zostanie automatycznie:
- Wykryta podczas startu orkiestratora
- Zaimportowana dynamicznie  
- Zarejestrowana z typem `"my_custom"` (lub z wartości `action_type`)

### 3. Użyj w scenariuszu YAML

```yaml
name: test_my_custom_action
actions:
  - type: my_custom           # Automatycznie wygenerowany typ
    param1: "Hello {{ trigger.source }}"
    param2: 100
```

## Przykłady akcji

### Akcja testowa

```python
class TestAction(BaseAction):
    async def execute(self, action_config: Dict[str, Any], context: ActionContext) -> Any:
        message = action_config.get("message", "Test wykonany!")
        resolved_message = self._resolve_template_variables(message, context)
        
        info(f"[TestAction] {resolved_message}", message_logger=context.message_logger)
        
        return {
            "status": "success", 
            "message": resolved_message,
            "scenario": context.scenario_name
        }
```

Użycie w YAML:
```yaml
actions:
  - type: test
    message: "Test z komponentu: {{ trigger.source }}"
```

### Akcja z niestandardowym typem

```python
class DataProcessorAction(BaseAction):
    action_type = "process_data"  # Niestandardowy typ
    
    async def execute(self, action_config: Dict[str, Any], context: ActionContext) -> Any:
        data = action_config.get("data", [])
        operation = action_config.get("operation", "count")
        
        if operation == "count":
            result = len(data)
        elif operation == "sum":
            result = sum(data) if all(isinstance(x, (int, float)) for x in data) else 0
        else:
            result = f"Unknown operation: {operation}"
            
        return {"operation": operation, "result": result}
```

Użycie w YAML:
```yaml
actions:
  - type: process_data      # Używa action_type zamiast nazwy klasy
    data: [1, 2, 3, 4, 5]
    operation: sum
```

## Rejestracja zewnętrznych akcji

Można również rejestrować akcje programistycznie:

```python
from avena_commons.orchestrator.actions.base_action import BaseAction

class ExternalAction(BaseAction):
    async def execute(self, action_config, context):
        return {"external": True}

# Rejestracja w orkiestratorze
orchestrator.register_action("external_action", ExternalAction())
```

## Debugging i monitorowanie

### Logi ładowania akcji

Podczas startu orkiestrator loguje:
- Ścieżkę katalogu akcji
- Znalezione pliki `*_action.py`
- Zarejestrowane akcje z ich typami
- Podsumowanie wszystkich dostępnych akcji

### Sprawdzanie zarejestrowanych akcji

```python
# Pobierz wszystkie zarejestrowane akcje
registered_actions = orchestrator.get_registered_actions()
print(f"Dostępne akcje: {list(registered_actions.keys())}")
```

### Typowe problemy

1. **Akcja nie została znaleziona**: Sprawdź czy plik kończy się na `_action.py`
2. **Import error**: Sprawdź składnię i zależności w pliku akcji
3. **Klasa nie dziedziczy po BaseAction**: Upewnij się że klasa rozszerza `BaseAction`
4. **Błąd tworzenia instancji**: Sprawdź konstruktor akcji (nie powinien wymagać parametrów)

## Struktura katalogów

```
src/avena_commons/orchestrator/actions/
├── __init__.py
├── base_action.py           # Klasa bazowa
├── action_executor.py       # System wykonywania
├── log_action.py           # Akcja logowania
├── send_command_action.py  # Akcja wysyłania komend
├── wait_for_state_action.py # Akcja oczekiwania na stan
├── test_action.py          # Przykładowe akcje testowe
└── my_custom_action.py     # Twoje niestandardowe akcje
```

## Zalety systemu

1. **Automatyczne wykrywanie** - brak potrzeby modyfikacji kodu orkiestratora
2. **Konwencja nad konfiguracją** - automatyczne mapowanie nazw
3. **Elastyczność** - możliwość definiowania niestandardowych typów
4. **Łatwość rozszerzania** - dodanie nowej akcji to tylko stworzenie pliku
5. **Kompatybilność wsteczna** - istniejące akcje działają bez zmian
6. **Debugging** - szczegółowe logi procesu ładowania 