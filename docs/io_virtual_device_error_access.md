# Strukturalny dostęp do błędów urządzeń wirtualnych w IO_server

## Problem

Dotychczas scenariusze musiały używać **regex** do wykrywania błędów konkretnych urządzeń wirtualnych:

```json
{
  "error_message": {
    "mode": "regex",
    "pattern": "feeder(?P<id>\\d+)",
    "case_sensitive": false,
    "fault_clients_only": true
  }
}
```

**Problemy tego podejścia:**
- Kruchy - zmiana formatu wiadomości łamie detekcję
- Nieczytelny - regex trudny do debugowania
- Niepraktyczny - brak type safety, łatwo o błędy w pattern
- Ograniczony - nie ma dostępu do szczegółowych metadanych błędu

## Rozwiązanie

Dodano **strukturalny dostęp** do informacji o błędnych urządzeniach bez potrzeby parsowania stringów.

### 1. Nowe pole w stanie IO_server

Stan eksportowany do orchestrator/scenariuszy zawiera teraz:

```python
state = {
    "io_server": {
        "name": "io1",
        "port": 5001,
        "error": True,
        "error_message": "Virtual device errors detected...",
        # NOWE: Strukturalna lista błędnych urządzeń
        "failed_virtual_devices": {
            "feeder1": {
                "state": "ERROR",
                "error_message": "Physical device 'motor_feeder1' (TLC57R24V08) in ERROR: Communication timeout",
                "failed_physical_devices": {
                    "motor_feeder1": {
                        "state": "ERROR",
                        "error_message": "Communication timeout",
                        "timestamp": 1732800123.456,
                        "device_type": "TLC57R24V08"
                    }
                }
            },
            "robot2": {
                "state": "ERROR",
                "error_message": "Physical device 'encoder_left' (GB4715) in ERROR: Signal lost",
                "failed_physical_devices": {
                    "encoder_left": {...},
                    "encoder_right": {...}
                }
            }
        }
    },
    "virtual_devices": {...},
    "buses": {...}
}
```

### 2. Publiczne metody API w IO_server

```python
class IO_server(EventListener):
    def get_virtual_device_state(self, device_name: str) -> Optional[str]:
        """Zwraca stan urządzenia wirtualnego jako string.
        
        Returns:
            "ERROR" | "WORKING" | "INITIALIZING" | "UNINITIALIZED" | None
        """
        
    def get_failed_virtual_devices(self) -> dict:
        """Zwraca słownik wszystkich urządzeń wirtualnych w stanie ERROR.
        
        Returns:
            {device_name: {state, error_message, failed_physical_devices}}
        """
```

## Przykłady użycia

### W scenariuszach - dostęp przez clients state

Orchestrator przekazuje stan IO_server do scenariuszy przez `clients`:

```python
# W definicji warunku scenariusza:
scenario_context = ScenarioContext(
    clients={
        "io1": {
            "io_server": {
                "failed_virtual_devices": {
                    "feeder1": {...},
                    "robot2": {...}
                }
            }
        }
    }
)
```

#### Przykład 1: Sprawdzenie czy konkretne urządzenie w błędzie

**Stary sposób (regex):**
```json
{
  "conditions": [
    {
      "error_message": {
        "pattern": "feeder1",
        "mode": "contains",
        "fault_clients_only": true
      }
    }
  ]
}
```

**Nowy sposób (strukturalny):**
```python
# W kodzie warunku Python:
def check_feeder1_error(context):
    io_state = context.clients.get("io1", {})
    failed_devices = io_state.get("io_server", {}).get("failed_virtual_devices", {})
    return "feeder1" in failed_devices

# Lub w JSON condition (jeśli wspierane):
{
  "conditions": [
    {
      "virtual_device_in_error": {
        "client": "io1",
        "device_name": "feeder1"
      }
    }
  ]
}
```

#### Przykład 2: Reakcja na błąd konkretnego urządzenia z kontekstem

**Stary sposób:**
```json
{
  "error_message": {
    "pattern": "Piec",
    "mode": "starts_with"
  }
}
```
Problem: Tylko informacja że "Piec" jest w błędzie, brak szczegółów.

**Nowy sposób:**
```python
def handle_piec_error(context):
    io_state = context.clients.get("io1", {})
    failed_devices = io_state.get("io_server", {}).get("failed_virtual_devices", {})
    
    if "Piec" in failed_devices:
        error_info = failed_devices["Piec"]
        
        # Dostęp do szczegółowych informacji
        error_message = error_info["error_message"]
        physical_devices = error_info["failed_physical_devices"]
        
        # Przykład: Sprawdź czy to błąd sensora temperatury
        if "temp_sensor" in physical_devices:
            temp_error = physical_devices["temp_sensor"]
            if "timeout" in temp_error["error_message"].lower():
                # Reakcja: Sensor timeout - użyj backup readingu
                return "use_backup_temperature"
        
        # Przykład: Sprawdź czy to błąd grzałki
        if "heater_control" in physical_devices:
            heater_error = physical_devices["heater_control"]
            if heater_error["device_type"] == "TLC57R24V08":
                # Reakcja: Modbus komunikacja - retry connection
                return "retry_modbus_connection"
        
        # Default: Piec w błędzie z nieznanej przyczyny
        return "emergency_stop_piec"
    
    return "piec_ok"
```

#### Przykład 3: Sprawdzenie czy DOWOLNE urządzenie w błędzie

**Stary sposób:**
```python
# Sprawdzenie czy client w FAULT
if context.clients["io1"]["fsm_state"] == "FAULT":
    # Ale NIE WIADOMO które urządzenie!
```

**Nowy sposób:**
```python
def check_any_device_error(context):
    io_state = context.clients.get("io1", {})
    failed_devices = io_state.get("io_server", {}).get("failed_virtual_devices", {})
    
    if failed_devices:
        # Mamy błędy - lista urządzeń
        device_names = list(failed_devices.keys())
        print(f"Failed devices: {device_names}")
        
        # Szczegółowa diagnostyka dla każdego
        for device_name, error_info in failed_devices.items():
            print(f"{device_name}: {error_info['error_message']}")
            
        return True
    return False
```

#### Przykład 4: Warunek scenariusza - kontynuuj jeśli błąd to Piec

```python
# Definicja scenariusza - transition condition
{
  "from_state": "running",
  "to_state": "piec_recovery",
  "conditions": [
    {
      "type": "python_eval",
      "expression": "'Piec' in clients.get('io1', {}).get('io_server', {}).get('failed_virtual_devices', {})"
    }
  ],
  "actions": [
    {
      "type": "log",
      "message": "Piec error detected, entering recovery mode"
    }
  ]
}

# Lub z dedykowanym condition checker:
{
  "from_state": "running",
  "to_state": "feeder_recovery",
  "conditions": [
    {
      "type": "virtual_device_error",
      "client": "io1",
      "device_name": "feeder1"
    }
  ]
}
```

### Bezpośrednie wywołanie metod IO_server (Python)

```python
# Jeśli masz bezpośredni dostęp do instancji IO_server:

# Sprawdź stan konkretnego urządzenia
state = io_server.get_virtual_device_state("feeder1")
if state == "ERROR":
    print("Feeder1 is in error!")

# Pobierz wszystkie błędne urządzenia
failed = io_server.get_failed_virtual_devices()
for device_name, error_info in failed.items():
    print(f"{device_name}: {error_info['error_message']}")
    
    # Dostęp do przyczyny błędu (physical devices)
    for phys_name, phys_info in error_info['failed_physical_devices'].items():
        print(f"  - {phys_name} ({phys_info['device_type']}): {phys_info['error_message']}")
```

### W dashboard/monitoring (dostęp przez state)

```python
# WebSocket/REST API endpoint zwracający stan
def get_io_status():
    state = io_server.update_state()
    
    return {
        "io_server": state["io_server"],
        # Zawiera failed_virtual_devices
    }

# Frontend może wyświetlić:
# - Lista błędnych urządzeń wirtualnych
# - Dla każdego: komunikat błędu + timestamp
# - Lista urządzeń fizycznych które spowodowały błąd
# - Typ urządzenia fizycznego (dla diagnostyki)
```

## Struktura danych

### failed_virtual_devices (top-level w io_server)

```python
{
    "device_name": {
        "state": "ERROR",                    # Always "ERROR" for failed devices
        "error_message": str,                # Human-readable error message
        "failed_physical_devices": {         # Physical devices that caused the error
            "physical_device_name": {
                "state": "ERROR" | "FAULT",  # Physical device FSM state
                "error_message": str,        # Specific error from physical device
                "timestamp": float,          # Unix timestamp when error occurred
                "device_type": str           # Class name (e.g., "TLC57R24V08")
            }
        }
    }
}
```

### Przykładowa wartość

```python
{
    "feeder1": {
        "state": "ERROR",
        "error_message": "Physical device 'motor_feeder1' (TLC57R24V08) in ERROR: Communication timeout",
        "failed_physical_devices": {
            "motor_feeder1": {
                "state": "ERROR",
                "error_message": "Communication timeout",
                "timestamp": 1732800123.456,
                "device_type": "TLC57R24V08"
            }
        }
    },
    "conveyor_system": {
        "state": "ERROR",
        "error_message": "Physical device 'encoder_main' (GB4715) in ERROR: Signal lost",
        "failed_physical_devices": {
            "encoder_main": {
                "state": "ERROR",
                "error_message": "Signal lost",
                "timestamp": 1732800124.789,
                "device_type": "GB4715"
            },
            "power_supply": {
                "state": "ERROR",
                "error_message": "Overvoltage detected",
                "timestamp": 1732800124.800,
                "device_type": "P7674"
            }
        }
    }
}
```

## Migracja z regex do strukturalnego dostępu

### Przed (regex):

```python
# Condition w scenariuszu
{
  "error_message": {
    "pattern": "feeder(?P<id>\\d+)",
    "mode": "regex",
    "extract_to_context": {
      "feeder_id": "id"
    }
  }
}

# W akcji - trzeba parsować error_message
def handle_error(context):
    error_msg = context.clients["io1"]["io_server"]["error_message"]
    if "feeder" in error_msg:
        # Parse message manually...
        import re
        match = re.search(r"feeder(\d+)", error_msg)
        if match:
            feeder_id = match.group(1)
            # Handle error for specific feeder
```

### Po (strukturalny):

```python
# Condition w scenariuszu - prosty, czytelny
{
  "type": "python_eval",
  "expression": "any('feeder' in name for name in clients['io1']['io_server']['failed_virtual_devices'])"
}

# W akcji - bezpośredni dostęp
def handle_error(context):
    failed = context.clients["io1"]["io_server"]["failed_virtual_devices"]
    
    # Znajdź wszystkie feeder'y w błędzie
    failed_feeders = {name: info for name, info in failed.items() if "feeder" in name}
    
    for feeder_name, error_info in failed_feeders.items():
        # Bezpośredni dostęp do ID z nazwy
        feeder_id = feeder_name.replace("feeder", "")
        
        # Dostęp do szczegółowych informacji
        error_message = error_info["error_message"]
        physical_devices = error_info["failed_physical_devices"]
        
        # Diagnostyka: które urządzenie fizyczne zawiodło?
        for phys_name, phys_info in physical_devices.items():
            print(f"Feeder {feeder_id} - {phys_name} ({phys_info['device_type']}): {phys_info['error_message']}")
```

## Kompatybilność wstecz

✅ **Stary kod nadal działa** - regex na `error_message` ciągle funkcjonuje
✅ **Nowe pole dodatkowe** - `failed_virtual_devices` jest dodatkowe, nie zastępuje istniejących pól
✅ **Opcjonalne użycie** - można stopniowo migrować scenariusze bez breaking changes

## Korzyści

1. **Zero regex** - czytelny, type-safe kod
2. **Szczegółowa diagnostyka** - dostęp do metadanych physical devices
3. **Łatwiejszy debugging** - jasna struktura danych
4. **Lepsze testy** - można testować bez parsowania stringów
5. **Skalowalność** - łatwo dodać więcej metadanych w przyszłości
6. **IDE support** - autocomplete dla kluczy słownika

## Przykład kompletnego scenariusza

```python
# Scenario definition
scenario = {
    "name": "handle_io_errors",
    "states": [
        {
            "name": "monitoring",
            "transitions": [
                {
                    "to": "handle_feeder_error",
                    "conditions": [
                        {
                            "type": "python_eval",
                            "expression": "'feeder1' in clients['io1']['io_server']['failed_virtual_devices']"
                        }
                    ]
                },
                {
                    "to": "handle_piec_error",
                    "conditions": [
                        {
                            "type": "python_eval",
                            "expression": "'Piec' in clients['io1']['io_server']['failed_virtual_devices']"
                        }
                    ]
                }
            ]
        },
        {
            "name": "handle_feeder_error",
            "actions": [
                {
                    "type": "python_function",
                    "function": "diagnose_feeder_error"
                }
            ],
            "transitions": [
                {
                    "to": "recovery",
                    "conditions": [{"type": "action_completed"}]
                }
            ]
        },
        {
            "name": "handle_piec_error",
            "actions": [
                {
                    "type": "python_function",
                    "function": "diagnose_piec_error"
                }
            ],
            "transitions": [
                {
                    "to": "monitoring",
                    "conditions": [
                        {
                            "type": "python_eval",
                            "expression": "'Piec' not in clients['io1']['io_server']['failed_virtual_devices']"
                        }
                    ]
                }
            ]
        }
    ]
}

# Action functions
def diagnose_feeder_error(context):
    failed = context.clients["io1"]["io_server"]["failed_virtual_devices"]
    feeder_error = failed.get("feeder1", {})
    
    physical_devices = feeder_error.get("failed_physical_devices", {})
    
    # Check motor
    if "motor_feeder1" in physical_devices:
        motor_error = physical_devices["motor_feeder1"]
        if "timeout" in motor_error["error_message"].lower():
            return {"action": "restart_motor", "device": "motor_feeder1"}
    
    return {"action": "emergency_stop"}

def diagnose_piec_error(context):
    failed = context.clients["io1"]["io_server"]["failed_virtual_devices"]
    piec_error = failed.get("Piec", {})
    
    physical_devices = piec_error.get("failed_physical_devices", {})
    
    # Detailed diagnostics
    diagnostics = {
        "error_count": len(physical_devices),
        "failed_devices": list(physical_devices.keys()),
        "error_types": [info["device_type"] for info in physical_devices.values()]
    }
    
    # Decision based on diagnostics
    if diagnostics["error_count"] == 1:
        # Single device failure - can continue with backup
        return {"action": "continue_with_backup"}
    else:
        # Multiple failures - critical situation
        return {"action": "emergency_shutdown"}
```

## Podsumowanie

Nowy system zapewnia:
- ✅ **Strukturalny dostęp** do błędów urządzeń wirtualnych
- ✅ **Szczegółowe metadane** o przyczynach błędów (physical devices)
- ✅ **Czytelny kod** w scenariuszach bez regex
- ✅ **Kompatybilność wstecz** ze starym podejściem
- ✅ **Lepszą diagnostykę** i debugging
- ✅ **Łatwiejszą integrację** w nowych scenariuszach
