# Komponent Lynx API dla Orchestratora

Komponent umożliwia automatyzację zwrotów płatności poprzez integrację z Nayax Core Lynx API. Obsługuje pełny cykl zwrotu: żądanie refund oraz zatwierdzenie refund.

## Konfiguracja

### Wymagane zależności
```bash
pip install requests
```

### Zmienne środowiskowe
```bash
export ACCESS_TOKEN="your_access_token_here"
export SITE_ID="123"  # opcjonalnie, domyślnie 0
```

### Konfiguracja komponentu
```json
{
  "components": {
    "lynx_api": {
      "type": "lynx_api",
      "ACCESS_TOKEN": "your_access_token_here",
      "SITE_ID": "123"
    }
  }
}
```

## Użycie w scenariuszach

### Kompletny workflow refund + approve
```json
{
  "actions": [
    {
      "type": "lynx_refund",
      "component": "lynx_api",
      "transaction_id": 123456,
      "refund_amount": 0,
      "refund_reason": "Auto refund",
      "refund_email_list": "admin@example.com"
    },
    {
      "type": "lynx_refund_approve",
      "component": "lynx_api", 
      "transaction_id": 123456,
      "is_refunded_externally": false,
      "refund_document_url": ""
    }
  ]
}
```

### Parametry akcji `lynx_refund`

| Parametr | Typ | Wymagany | Opis |
|----------|-----|----------|------|
| `component` | string | ✅ | Nazwa komponentu Lynx API w konfiguracji |
| `transaction_id` | int/string | ✅ | ID transakcji do zwrotu |
| `refund_amount` | float | ❌ | Kwota zwrotu (domyślnie 0) |
| `refund_reason` | string | ❌ | Powód zwrotu |
| `refund_email_list` | string | ❌ | Lista emaili do powiadomienia |

### Parametry akcji `lynx_refund_approve`

| Parametr | Typ | Wymagany | Opis |
|----------|-----|----------|------|
| `component` | string | ✅ | Nazwa komponentu Lynx API w konfiguracji |
| `transaction_id` | int/string | ✅ | ID transakcji do zatwierdzenia zwrotu |
| `is_refunded_externally` | bool | ❌ | Czy zwrot wykonany zewnętrznie (domyślnie false) |
| `refund_document_url` | string | ❌ | URL dokumentu zwrotu (domyślnie pusty) |
| `machine_au_time` | string | ❌ | Czas autoryzacji maszyny ISO format (opcjonalny) |

**Uwaga:** `site_id` jest automatycznie pobierane z konfiguracji komponentu Lynx API.

### Zmienne szablonowe
```json
{
  "actions": [
    {
      "type": "lynx_refund",
      "component": "lynx_api",
      "transaction_id": "{{ trigger.transaction_id }}",
      "refund_reason": "Auto refund - {{ trigger.error_message }}",
      "refund_email_list": "{{ trigger.admin_email }}"
    },
    {
      "type": "lynx_refund_approve", 
      "component": "lynx_api",
      "transaction_id": "{{ trigger.transaction_id }}",
      "is_refunded_externally": "{{ trigger.is_refunded_externally }}",
      "refund_document_url": "{{ trigger.refund_document_url }}",
      "machine_au_time": "{{ trigger.machine_au_time }}"
    }
  ]
}
```

#### Dostępne zmienne:
**Dla obu akcji:**
- `{{ trigger.transaction_id }}` - ID transakcji z triggera zdarzenia
- `{{ trigger.error_message }}` - Wiadomość błędu z triggera
- `{{ trigger.source }}` - Źródło triggera (nazwa serwisu)
- `{{ error_message }}` - Uniwersalny error message (z trigger lub stanu systemu)
- `{{ trigger.admin_email }}` - Email administratora (jeśli dostępny w trigger_data)

**Dodatkowe dla lynx_refund_approve:**
- `{{ trigger.refund_document_url }}` - URL dokumentu zwrotu z triggera
- `{{ trigger.machine_au_time }}` - Czas autoryzacji maszyny z triggera
- `{{ trigger.is_refunded_externally }}` - Flaga zwrotu zewnętrznego z triggera

## Przykład kompletnego scenariusza

```json
{
  "name": "automatic_refund_on_error",
  "description": "Automatyczny zwrot przy błędzie płatności - kompletny workflow",
  "priority": 200,
  "trigger": {
    "type": "automatic",
    "conditions": {
      "error_message": {
        "pattern": "PAYMENT_ERROR|PAYMENT_TIMEOUT",
        "source": "payment_service"
      }
    }
  },
  "actions": [
    {
      "type": "log",
      "message": "Wykryto błąd płatności, rozpoczynam refund dla {{ trigger.transaction_id }}",
      "level": "warning"
    },
    {
      "type": "lynx_refund",
      "component": "lynx_api",
      "transaction_id": "{{ trigger.transaction_id }}",
      "refund_reason": "Automatic refund due to payment error - {{ trigger.error_message }}"
    },
    {
      "type": "log",
      "message": "Refund request completed, sending approve for {{ trigger.transaction_id }}",
      "level": "info"
    },
    {
      "type": "lynx_refund_approve",
      "component": "lynx_api", 
      "transaction_id": "{{ trigger.transaction_id }}",
      "is_refunded_externally": false,
      "refund_document_url": ""
    },
    {
      "type": "log",
      "message": "Complete refund workflow finished for transaction {{ trigger.transaction_id }}",
      "level": "info"
    }
  ]
}
```

## Struktura żądań API

### Żądanie refund
Komponent wysyła żądania POST do:
```
https://qa-lynx.nayax.com/operational/v1/payment/refund-request
```

Format żądania:
```json
{
  "RefundAmount": 0,
  "RefundEmailList": "admin@example.com",
  "RefundReason": "Automatic refund due to payment error", 
  "TransactionId": 123456,
  "SiteId": 123,
  "MachineAuTime": "2025-09-09T09:00:51.897Z"
}
```

### Żądanie refund approve
Komponent wysyła żądania POST do:
```
https://qa-lynx.nayax.com/operational/v1/payment/refund-approve
```

Format żądania:
```json
{
  "IsRefundedExternally": true,
  "RefundDocumentUrl": "string",
  "TransactionId": 0,
  "SiteId": 0,
  "MachineAuTime": "2024-10-10T16:30:37.179Z"
}
```

### Automatyczne parametry
- `SiteId` - automatycznie z konfiguracji komponentu
- `MachineAuTime` - automatycznie ustawiane na aktualny czas UTC (dla refund) lub z parametru (dla approve)
- Pozostałe pola z konfiguracji akcji lub zmiennych trigger

## Bezpieczeństwo i logowanie

- `ACCESS_TOKEN` automatycznie jako Bearer token w nagłówku Authorization
- Wszystkie połączenia przez HTTPS
- Tokeny maskowane w logach
- Pełny audyt operacji: inicjalizacja, żądania, błędy, statusy

## Testowanie

```bash
cd /home/avena/avena_commons/src
python3 /home/avena/avena_commons/src/avena_commons/orchestrator/test_lynx_api.py
```

## Rozwiązywanie problemów

| Problem | Rozwiązanie |
|---------|-------------|
| Import Error - brak requests | `pip install requests` |
| Missing ACCESS_TOKEN | Ustaw zmienną środowiskową lub w konfiguracji |
| HTTP 401 Unauthorized | Sprawdź poprawność ACCESS_TOKEN |
| HTTP 404 Not Found | Zweryfikuj dostępność endpoint API |
