# Rozszerzenie systemu śledzenia błędów urządzeń fizycznych

## Cel modyfikacji

Rozszerzenie systemu propagacji błędów o:
1. **Metadane źródła błędu** - każde urządzenie wirtualne śledzi które dokładnie urządzenie fizyczne wywołało błąd
2. **Agregacja przed eskalacją** - IO_server sprawdza wszystkie urządzenia wirtualne przed zmianą stanu FSM
3. **Deduplikacja błędów** - gdy to samo urządzenie fizyczne wpada w błąd i jest używane przez wiele urządzeń wirtualnych, logowane jest tylko raz

## Architektura

### 1. VirtualDevice - tracking metadanych urządzeń fizycznych

**Nowe pole:**
```python
self._failed_physical_devices: Dict[str, Dict[str, Any]] = {}
```

**Format wpisu:**
```python
{
    "device_name": {
        "state": "ERROR" | "FAULT",          # Stan PhysicalDeviceState
        "error_message": "konkretny błąd",   # Komunikat z urządzenia fizycznego
        "timestamp": 1234567890.123,         # Unix timestamp
        "device_type": "TLC57R24V08",        # Typ klasy urządzenia
    }
}
```

**Logika działania:**
- `_check_physical_devices_health()` przy każdym tick() sprawdza stan wszystkich urządzeń fizycznych
- Jeśli wykryje ERROR/FAULT - dodaje wpis do `_failed_physical_devices`
- Jeśli urządzenie powróci do WORKING - usuwa wpis (device recovered)
- Metadane są dostępne dla IO_server do agregacji

### 2. VirtualDevice._check_physical_devices_health() - rozszerzone śledzenie

**Rozszerzona logika:**
```python
# FAULT state - critical, immediate escalation
if device_state == PhysicalDeviceState.FAULT:
    error_msg = getattr(device, "_error_message", "Unknown fault")
    
    # Record metadata
    self._failed_physical_devices[device_name] = {
        "state": "FAULT",
        "error_message": error_msg,
        "timestamp": time.time(),
        "device_type": type(device).__name__,
    }
    
    # Escalate to VirtualDevice.ERROR
    self.set_state(VirtualDeviceState.ERROR)
    self._error_message = f"Physical device '{device_name}' ({type(device).__name__}) in FAULT: {error_msg}"
    return

# ERROR state - call handler (customizable)
elif device_state == PhysicalDeviceState.ERROR:
    # Record metadata
    self._failed_physical_devices[device_name] = {
        "state": "ERROR",
        "error_message": error_msg,
        "timestamp": time.time(),
        "device_type": type(device).__name__,
    }
    
    # Call overridable handler
    self._on_physical_device_error(device_name, error_msg)

# WORKING state - recovery
elif device_state == PhysicalDeviceState.WORKING:
    if device_name in self._failed_physical_devices:
        debug(f"Physical device '{device_name}' recovered")
        del self._failed_physical_devices[device_name]
```

### 3. IO_server._check_local_data() - agregacja błędów

**Stary flow (problematyczny):**
```python
for device_name, device in self._devices.items():
    if device.get_current_state() == ERROR:
        self._error = True
        self._error_message = device._error_message
        self._change_fsm_state(ON_ERROR)
        return  # ❌ IMMEDIATE return - nie sprawdza pozostałych urządzeń
```

**Nowy flow (batch processing):**
```python
# KROK 1: Collect errors from ALL virtual devices (no immediate return)
for device_name, device in self._devices.items():
    if device.get_current_state() == ERROR:
        if not hasattr(self, "_virtual_device_errors"):
            self._virtual_device_errors = {}
        
        failed_physical = getattr(device, "_failed_physical_devices", {})
        self._virtual_device_errors[device_name] = {
            "error_message": device._error_message,
            "failed_physical_devices": failed_physical.copy(),
        }

# KROK 2: Aggregate failed physical devices (deduplication)
all_failed_physical = {}  # {phys_name: {state, error_message, device_type, affected_virtual_devices[]}}

for vdev_name, error_info in self._virtual_device_errors.items():
    for phys_name, phys_info in error_info["failed_physical_devices"].items():
        if phys_name not in all_failed_physical:
            # First occurrence
            all_failed_physical[phys_name] = {
                "state": phys_info["state"],
                "error_message": phys_info["error_message"],
                "device_type": phys_info["device_type"],
                "affected_virtual_devices": [vdev_name],
            }
        else:
            # Same physical device failed in multiple virtual devices
            all_failed_physical[phys_name]["affected_virtual_devices"].append(vdev_name)

# KROK 3: Build comprehensive error message
error_parts = [f"Virtual device errors detected ({len(self._virtual_device_errors)} devices):"]
for vdev_name, error_info in self._virtual_device_errors.items():
    error_parts.append(f"  - {vdev_name}: {error_info['error_message']}")

if all_failed_physical:
    error_parts.append(f"\nRoot cause - Failed physical devices ({len(all_failed_physical)}):")
    for phys_name, phys_info in all_failed_physical.items():
        affected = phys_info["affected_virtual_devices"]
        error_parts.append(
            f"  - {phys_name} ({phys_info['device_type']}): {phys_info['state']} - {phys_info['error_message']}"
        )
        if len(affected) > 1:
            error_parts.append(f"    Affects {len(affected)} virtual devices: {', '.join(affected)}")

self._error_message = "\n".join(error_parts)

# KROK 4: Escalate AFTER checking all devices
if self.fsm_state not in {ON_ERROR, FAULT}:
    error(self._error_message, message_logger=self._message_logger)
    self._change_fsm_state(EventListenerState.ON_ERROR)
```

## Przykładowe scenariusze

### Scenariusz 1: Pojedyncze urządzenie fizyczne w błędzie

**Stan:**
- PhysicalDevice: `motor_controller_1` (TLC57R24V08) → ERROR: "Communication timeout"
- VirtualDevice: `conveyor_belt` używa `motor_controller_1`

**VirtualDevice._failed_physical_devices:**
```python
{
    "motor_controller_1": {
        "state": "ERROR",
        "error_message": "Communication timeout",
        "timestamp": 1704123456.789,
        "device_type": "TLC57R24V08",
    }
}
```

**IO_server error message:**
```
Virtual device errors detected (1 devices):
  - conveyor_belt: Physical device 'motor_controller_1' (TLC57R24V08) in ERROR: Communication timeout

Root cause - Failed physical devices (1):
  - motor_controller_1 (TLC57R24V08): ERROR - Communication timeout
```

### Scenariusz 2: Jedno urządzenie fizyczne używane przez wiele wirtualnych

**Stan:**
- PhysicalDevice: `power_supply_main` (P7674) → ERROR: "Overvoltage detected"
- VirtualDevice: `station_A` używa `power_supply_main`
- VirtualDevice: `station_B` używa `power_supply_main`
- VirtualDevice: `station_C` używa `power_supply_main`

**Każde VirtualDevice._failed_physical_devices:**
```python
# station_A, station_B, station_C - wszystkie mają:
{
    "power_supply_main": {
        "state": "ERROR",
        "error_message": "Overvoltage detected",
        "timestamp": 1704123456.789,
        "device_type": "P7674",
    }
}
```

**IO_server error message (deduplikacja!):**
```
Virtual device errors detected (3 devices):
  - station_A: Physical device 'power_supply_main' (P7674) in ERROR: Overvoltage detected
  - station_B: Physical device 'power_supply_main' (P7674) in ERROR: Overvoltage detected
  - station_C: Physical device 'power_supply_main' (P7674) in ERROR: Overvoltage detected

Root cause - Failed physical devices (1):
  - power_supply_main (P7674): ERROR - Overvoltage detected
    Affects 3 virtual devices: station_A, station_B, station_C
```

✅ **Widać że błąd w jednym urządzeniu fizycznym wpłynął na 3 wirtualne - nie 3 duplikaty tego samego błędu**

### Scenariusz 3: Wiele urządzeń fizycznych w błędzie

**Stan:**
- PhysicalDevice: `encoder_left` (GB4715) → ERROR: "Signal lost"
- PhysicalDevice: `encoder_right` (GB4715) → ERROR: "Signal lost"
- VirtualDevice: `robot_arm` używa `encoder_left` i `encoder_right`

**VirtualDevice._failed_physical_devices:**
```python
{
    "encoder_left": {
        "state": "ERROR",
        "error_message": "Signal lost",
        "timestamp": 1704123456.789,
        "device_type": "GB4715",
    },
    "encoder_right": {
        "state": "ERROR",
        "error_message": "Signal lost",
        "timestamp": 1704123456.790,
        "device_type": "GB4715",
    }
}
```

**IO_server error message:**
```
Virtual device errors detected (1 devices):
  - robot_arm: Physical device 'encoder_left' (GB4715) in ERROR: Signal lost

Root cause - Failed physical devices (2):
  - encoder_left (GB4715): ERROR - Signal lost
  - encoder_right (GB4715): ERROR - Signal lost
```

## Integracja z istniejącym kodem

### VirtualDevice.to_dict() - rozszerzone o metadane błędów

```python
result = {
    "name": self.device_name,
    "connected_devices": connected_devices_info,
    "failed_physical_devices": self._failed_physical_devices.copy() if hasattr(self, "_failed_physical_devices") else {},
}
```

Dzięki temu dashboard/monitoring może wyświetlić:
- Które urządzenie wirtualne jest w błędzie
- Które konkretnie urządzenie fizyczne spowodowało błąd
- Typ błędu (ERROR vs FAULT)
- Komunikat z urządzenia fizycznego
- Timestamp wystąpienia błędu

### Recovery - czyszczenie metadanych

Gdy urządzenie fizyczne powraca do stanu WORKING:
```python
if device_state == PhysicalDeviceState.WORKING:
    if device_name in self._failed_physical_devices:
        debug(f"Physical device '{device_name}' recovered from error")
        del self._failed_physical_devices[device_name]
```

Automatycznie usuwa wpis z listy błędów.

## Kompatybilność wstecz

✅ **Wszystkie istniejące VirtualDevice potomne działają bez zmian:**
- `_failed_physical_devices` inicjalizowane w `__init__`
- Domyślna implementacja `_on_physical_device_error()` zachowana (immediate escalation)
- Potomne klasy mogą nadpisać `_on_physical_device_error()` aby implementować retry logic

✅ **IO_server batch processing nie wpływa na logikę biznesową:**
- Nadal eskaluje do ON_ERROR gdy wykryje błędy
- Różnica: sprawdza WSZYSTKIE urządzenia przed eskalacją zamiast immediate return
- Więcej informacji w error message (root cause analysis)

## Korzyści

1. **Lepsza diagnostyka** - dokładnie wiadomo które urządzenie fizyczne zawiodło
2. **Przejrzysty monitoring** - dashboard widzi metadane błędów (state, timestamp, device_type)
3. **Unikanie duplikacji logów** - jedno urządzenie fizyczne = jeden komunikat błędu (mimo wielu wirtualnych)
4. **Batch processing** - kompletny obraz stanu wszystkich urządzeń przed decyzją o eskalacji
5. **Backward compatible** - istniejący kod działa bez zmian

## Testy

Należy przetestować:
- [x] VirtualDevice z jednym urządzeniem fizycznym w ERROR
- [x] VirtualDevice z wielu urządzeń fizycznych (niektóre w ERROR)
- [x] Jedno urządzenie fizyczne używane przez wiele VirtualDevice (deduplikacja)
- [x] Recovery urządzenia fizycznego (usunięcie z _failed_physical_devices)
- [x] IO_server agregacja błędów przed eskalacją
- [x] IO_server error message format (czytelność)

## Podsumowanie

Implementacja spełnia wszystkie wymagania:
✅ Metadane urządzenia fizycznego w VirtualDevice (`_failed_physical_devices`)
✅ Batch processing w IO_server (check all before escalate)
✅ Deduplikacja błędów urządzeń fizycznych używanych przez wiele wirtualnych
✅ Kompatybilność wstecz z istniejącym kodem
✅ Przejrzysty error message z root cause analysis
