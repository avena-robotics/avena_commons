# ErrorMessageCondition z obsługą urządzeń IO

## Nowa funkcjonalność: check_io_devices

Warunek `error_message` został rozszerzony o możliwość sprawdzania struktury `io_server.failed_virtual_devices` zamiast parsowania tekstu `error_message` przez regex.

## Porównanie: Stara vs Nowa metoda

### ❌ Stara metoda (regex na error_message)

**Problem**: Wymaga formatowania wiadomości błędu w kodzie IO i parsowania przez regex

```json
{
  "error_message": {
    "mode": "regex",
    "pattern": "^feeder(\\d+):",
    "case_sensitive": false,
    "extract_to_context": {
      "wydawka_id": 1
    }
  }
}
```

**Wady**:
- Wymaga prefixowania error_message nazwą urządzenia
- Regex trudny w utrzymaniu
- Brak dostępu do szczegółów urządzenia fizycznego
- Błędoprzyjemne (typo w formacie = nie zadziała)

### ✅ Nowa metoda (check_io_devices=true)

**Zalety**: Bezpośredni dostęp do struktury `failed_virtual_devices`, pełne informacje o urządzeniach

```json
{
  "error_message": {
    "mode": "contains",
    "pattern": "feeder",
    "check_io_devices": true,
    "extract_physical_device_to": "urzadzenie_fizyczne",
    "extract_error_message_to": "komunikat_bledu",
    "extract_device_type_to": "typ_urzadzenia"
  }
}
```

**Zalety**:
- ✅ Prosty pattern matching (bez regex)
- ✅ Automatyczna ekstrahacja szczegółów urządzenia fizycznego
- ✅ Nie wymaga zmian w kodzie IO
- ✅ Łatwiejsze w debugowaniu

## Parametry

| Parametr | Typ | Opis |
|----------|-----|------|
| `check_io_devices` | bool | Sprawdza `io_server.failed_virtual_devices` zamiast `error_message` |
| `extract_physical_device_to` | string | Nazwa zmiennej dla urządzenia fizycznego |
| `extract_error_message_to` | string | Nazwa zmiennej dla komunikatu błędu |
| `extract_device_type_to` | string | Nazwa zmiennej dla typu urządzenia |

## Przykłady użycia

### Przykład 1: Podstawowe sprawdzenie urządzenia

```json
{
  "trigger": {
    "conditions": {
      "error_message": {
        "pattern": "feeder",
        "check_io_devices": true
      }
    }
  }
}
```

### Przykład 2: Pełna ekstrahacja informacji

```json
{
  "trigger": {
    "conditions": {
      "error_message": {
        "pattern": "feeder",
        "check_io_devices": true,
        "extract_physical_device_to": "urzadzenie_fizyczne",
        "extract_error_message_to": "komunikat_bledu",
        "extract_device_type_to": "typ_urzadzenia"
      }
    }
  },
  "actions": [
    {
      "type": "send_email",
      "to": "operator@example.com",
      "subject": "Błąd urządzenia fizycznego",
      "body": "Urządzenie: {{urzadzenie_fizyczne}}\nTyp: {{typ_urzadzenia}}\nBłąd: {{komunikat_bledu}}"
    }
  ]
}
```

### Przykład 3: Sprawdzanie wielu wzorców (OR)

```json
{
  "trigger": {
    "conditions": {
      "or": {
        "conditions": [
          {
            "error_message": {
              "pattern": "feeder",
              "check_io_devices": true,
              "extract_physical_device_to": "urzadzenie"
            }
          },
          {
            "error_message": {
              "pattern": "chamber",
              "check_io_devices": true,
              "extract_physical_device_to": "urzadzenie"
            }
          }
        ]
      }
    }
  }
}
```

### Przykład 4: Exact match dla konkretnego urządzenia

```json
{
  "error_message": {
    "mode": "exact",
    "pattern": "feeder1",
    "check_io_devices": true,
    "extract_physical_device_to": "device",
    "extract_error_message_to": "error"
  }
}
```

## Kompatybilność

- ✅ **check_io_devices=false** (domyślnie): Działa jak dotychczas (sprawdza `error_message`)
- ✅ **check_io_devices=true**: Nowa funkcjonalność (sprawdza `io_server.failed_virtual_devices`)
- ⚠️ **check_io_devices=true** działa tylko dla klientów typu IO (z polem `io_server`)
- ✅ Istniejące scenariusze działają bez zmian

## Struktura danych

Warunek czyta dane z:

```python
{
  "clients": {
    "io": {
      "fsm_state": "ERROR",
      "error_message": "Virtual device errors detected: ['feeder1']",
      "io_server": {
        "failed_virtual_devices": {
          "feeder1": {
            "state": "ERROR",
            "error_message": "...",
            "failed_physical_devices": {
              "sterownik_modbus": {
                "state": "ERROR",
                "error_message": "Communication timeout",
                "device_type": "TLC57R24V08",
                "timestamp": 1234567890.123
              }
            }
          }
        }
      }
    }
  }
}
```

## Kiedy używać której metody?

| Scenariusz | Metoda | Powód |
|-----------|--------|-------|
| Klient IO z urządzeniami wirtualnymi | `check_io_devices=true` | Pełne informacje o urządzeniach |
| Inny typ klienta | `check_io_devices=false` | Nie ma `io_server` |
| Potrzebujesz typu urządzenia fizycznego | `check_io_devices=true` | Tylko tam są te dane |
| Prosty check "czy błąd zawiera X" | `check_io_devices=false` | Szybsze |

## Migracja ze starych scenariuszy

**Przed** (regex na error_message):
```json
{
  "error_message": {
    "mode": "regex",
    "pattern": "^feeder(\\d+):",
    "extract_to_context": {"id": 1}
  }
}
```

**Po** (check_io_devices):
```json
{
  "error_message": {
    "mode": "contains",
    "pattern": "feeder",
    "check_io_devices": true,
    "extract_physical_device_to": "device_name",
    "extract_error_message_to": "device_error"
  }
}
```

**Lub użyj dedykowanego warunku**:
```json
{
  "virtual_device_error": {
    "client": "io",
    "device_pattern": "feeder",
    "extract_id_to": "id",
    "extract_physical_device_to": "device_name",
    "extract_error_message_to": "device_error",
    "extract_device_type_to": "device_type"
  }
}
```

## Zobacz też

- [VirtualDeviceErrorCondition](virtual_device_error_condition.md) - Dedykowany warunek dla urządzeń wirtualnych
- [PhysicalDeviceBase](../io/physical_device_base.md) - FSM urządzeń fizycznych
- [VirtualDevice](../io/virtual_device.md) - Śledzenie błędów urządzeń fizycznych
