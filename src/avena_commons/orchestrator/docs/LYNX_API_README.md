# Komponent Lynx API dla Orchestratora

Komponent umożliwia automatyzację zwrotów płatności poprzez integrację z Nayax Core Lynx API. Wysyła żądania refund bezpośrednio z scenariuszy orchestratora.

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

### Podstawowa akcja refund
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
    }
  ]
}
```

#### Dostępne zmienne:
- `{{ trigger.transaction_id }}` - ID transakcji z triggera zdarzenia
- `{{ trigger.error_message }}` - Wiadomość błędu z triggera
- `{{ trigger.source }}` - Źródło triggera (nazwa serwisu)
- `{{ error_message }}` - Uniwersalny error message (z trigger lub stanu systemu)
- `{{ trigger.admin_email }}` - Email administratora (jeśli dostępny w trigger_data)

## Przykład kompletnego scenariusza

```json
{
  "name": "automatic_refund_on_error",
  "description": "Automatyczny zwrot przy błędzie płatności",
  "priority": 200,
  "conditions": [
    {
      "type": "error_message",
      "pattern": "PAYMENT_ERROR|PAYMENT_TIMEOUT",
      "source": "payment_service"
    }
  ],
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
      "message": "Refund completed for transaction {{ trigger.transaction_id }}",
      "level": "info"
    }
  ]
}
```

## Struktura żądania API

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

- `SiteId` - automatycznie z konfiguracji komponentu
- `MachineAuTime` - automatycznie ustawiane na aktualny czas UTC
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
