# VirtualDeviceErrorCondition - Warunek błędu urządzenia wirtualnego

## Opis

Warunek `virtual_device_error` sprawdza czy urządzenia wirtualne pasujące do podanego wzorca są w stanie ERROR. Umożliwia również ekstrahowanie szczegółowych informacji o błędzie do kontekstu scenariusza.

## Parametry konfiguracji

| Parametr | Typ | Wymagany | Opis |
|----------|-----|----------|------|
| `client` | string | Tak | Nazwa klienta IO w orchestratorze |
| `device_pattern` | string | Tak | Wzorzec nazwy urządzenia wirtualnego (np. "feeder", "chamber", "wydawka") |
| `extract_id_to` | string | Nie | Nazwa zmiennej kontekstu dla ID urządzenia wirtualnego (cyfry z końca nazwy) |
| `extract_physical_device_to` | string | Nie | Nazwa zmiennej kontekstu dla nazwy urządzenia fizycznego które spowodowało błąd |
| `extract_error_message_to` | string | Nie | Nazwa zmiennej kontekstu dla komunikatu błędu z urządzenia fizycznego |
| `extract_device_type_to` | string | Nie | Nazwa zmiennej kontekstu dla typu urządzenia fizycznego (klasa) |

## Jak działa

1. Warunek przeszukuje `io_server.failed_virtual_devices` w stanie klienta IO
2. Sprawdza czy którakolwiek nazwa urządzenia zawiera `device_pattern`
3. Jeśli znaleziono, ekstraktuje żądane informacje do kontekstu
4. Zwraca `True` jeśli znaleziono błąd, `False` w przeciwnym razie

## Przykłady użycia

### Podstawowe sprawdzenie błędu wydawki

```json
{
  "trigger": {
    "conditions": {
      "virtual_device_error": {
        "client": "io",
        "device_pattern": "feeder"
      }
    }
  }
}
```

### Ekstrahowanie ID urządzenia

Dla urządzenia `feeder1`, `feeder2` itp.:

```json
{
  "trigger": {
    "conditions": {
      "virtual_device_error": {
        "client": "io",
        "device_pattern": "feeder",
        "extract_id_to": "wydawka_id"
      }
    }
  },
  "actions": [
    {
      "type": "log_event",
      "message": "Błąd w wydawce numer {{wydawka_id}}"
    }
  ]
}
```

### Pełna ekstrakcja informacji o błędzie

```json
{
  "trigger": {
    "conditions": {
      "virtual_device_error": {
        "client": "io",
        "device_pattern": "feeder",
        "extract_id_to": "wydawka_id",
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
      "subject": "Błąd wydawki {{wydawka_id}} - {{typ_urzadzenia}}",
      "body": "Wykryto błąd w wydawce {{wydawka_id}}.\n\nUrządzenie: {{urzadzenie_fizyczne}} ({{typ_urzadzenia}})\nBłąd: {{komunikat_bledu}}"
    }
  ]
}
```

### Sprawdzanie wielu typów urządzeń

```json
{
  "trigger": {
    "conditions": {
      "or": {
        "conditions": [
          {
            "virtual_device_error": {
              "client": "io",
              "device_pattern": "feeder",
              "extract_id_to": "urzadzenie_id"
            }
          },
          {
            "virtual_device_error": {
              "client": "io",
              "device_pattern": "chamber",
              "extract_id_to": "urzadzenie_id"
            }
          }
        ]
      }
    }
  }
}
```

## Struktura danych failed_virtual_devices

Warunek czyta dane z następującej struktury w stanie klienta IO:

```python
{
  "io_server": {
    "failed_virtual_devices": {
      "feeder1": {
        "state": "ERROR",
        "error_message": "Virtual device error message",
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
```

## ekstraktowane wartości - przykład

Dla urządzenia `feeder1` z błędem sterownika Modbus:

| Parametr ekstrakcji | Wartość ekstraktowana |
|----------------------|----------------------|
| `extract_id_to` | `"1"` (z `feeder1`) |
| `extract_physical_device_to` | `"sterownik_modbus"` |
| `extract_error_message_to` | `"Communication timeout"` |
| `extract_device_type_to` | `"TLC57R24V08"` |

## Użycie w akcjach

Wyekstraktowane zmienne można używać we wszystkich akcjach scenariusza poprzez składnię `{{zmienna}}`:

```json
{
  "actions": [
    {
      "type": "log_event",
      "message": "Błąd w wydawce {{wydawka_id}}: {{urzadzenie_fizyczne}} - {{komunikat_bledu}}"
    },
    {
      "type": "send_custom_command",
      "client": "supervisor",
      "command": "disable_device",
      "data": {
        "device_id": "{{wydawka_id}}",
        "reason": "{{komunikat_bledu}}"
      }
    }
  ]
}
```

## Zalety wobec ErrorMessageCondition

Poprzednio używano `error_message_condition` z regex:

```json
{
  "error_message": {
    "client": "io",
    "pattern": "^feeder(\\d+):",
    "mode": "regex",
    "extract_to_context": {
      "wydawka_id": 1
    }
  }
}
```

**Problemy:**
- Wymaga formatowania wiadomości błędu w kodzie
- Trudne do utrzymania (regex)
- Nie daje dostępu do szczegółów urządzenia fizycznego

**Zalety VirtualDeviceErrorCondition:**
- ✅ Bezpośredni dostęp do struktury `failed_virtual_devices`
- ✅ Proste dopasowanie wzorca (bez regex)
- ✅ Automatyczna ekstrakcja szczegółów urządzenia fizycznego
- ✅ Łatwiejsze w utrzymaniu i debugowaniu
- ✅ Pełen kontekst błędu (urządzenie, typ, wiadomość)

## Zobacz też

- [ErrorMessageCondition](error_message_condition.md) - Warunek sprawdzający komunikaty błędów
- [PhysicalDeviceBase](../io/physical_device_base.md) - FSM urządzeń fizycznych
- [VirtualDevice](../io/virtual_device.md) - Śledzenie błędów urządzeń fizycznych
- [Przykładowe scenariusze](scenarios/) - Kompletne przykłady użycia
