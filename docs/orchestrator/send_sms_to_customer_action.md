# Akcja send_sms_to_customer - Dokumentacja

## Opis

Akcja `send_sms_to_customer` jest przystosowana do wysyłania wiadomości SMS do klientów, gdzie numery telefonów i dane personalizujące są pobierane z danych triggera scenariusza. Jest to rozszerzenie standardowej akcji `send_sms`, ale zoptymalizowane do pracy z listami klientów z bazy danych.

## Działanie

Akcja automatycznie:
1. Pobiera listę rekordów klientów z `trigger_data`
2. Identyfikuje pole zawierające numer telefonu (automatycznie lub według konfiguracji)
3. Personalizuje treść wiadomości dla każdego klienta
4. Wysyła SMS-y przez bramkę MultiInfo Plus API
5. Normalizuje numery telefonów (obsługa różnych formatów)
6. Obsługuje segmentację długich wiadomości

## Konfiguracja

### Wymagana konfiguracja SMS w orchestratorze

```json
{
  "sms": {
    "enabled": true,
    "url": "https://api.multiinfo.plus",
    "login": "your_login",
    "password": "your_password", 
    "serviceId": "12345",
    "source": "YourCompany",
    "max_length": 160,
    "max_error_attempts": 3
  }
}
```

### Parametry akcji

| Parametr | Typ | Wymagany | Domyślnie | Opis |
|----------|-----|----------|-----------|------|
| `type` | string | ✓ | - | Musi być `"send_sms_to_customer"` |
| `text` | string | ✓ | - | Treść wiadomości z placeholderami |
| `phone_field` | string | ✗ | auto-detect | Nazwa pola z numerem telefonu |
| `ignore_errors` | boolean | ✗ | false | Czy ignorować błędy wysyłki |
| `description` | string | ✗ | - | Opis akcji (dla logów) |

## Przykład użycia w scenariuszu

```json
{
  "name": "Powiadomienia SMS o gotowych zamówieniach",
  "trigger": {
    "type": "automatic",
    "conditions": {
      "database_list": {
        "component": "main_database",
        "table": "orders",
        "columns": ["id", "aps_id", "pickup_number", "kds_order_number", "client_phone_number", "status"],
        "where": {"status": "order_processing_has_started"},
        "result_key": "zamowienia_gotowe"
      }
    }
  },
  "actions": [
    {
      "type": "send_sms_to_customer",
      "description": "Powiadomienie SMS o gotowym zamówieniu",
      "phone_field": "client_phone_number",
      "text": "Twoje zamówienie nr {{ pickup_number }} jest gotowe do odbioru (APS ID: {{ aps_id }}). Pozdrawiamy!"
    }
  ]
}
```

## Placeholdery w treści wiadomości

### Dane z rekordu klienta
Każde pole z rekordu zamówienia można użyć jako placeholder:
- `{{ id }}` - ID zamówienia
- `{{ aps_id }}` - ID zamówienia w systemie APS
- `{{ pickup_number }}` - numer odbioru
- `{{ kds_order_number }}` - numer zamówienia KDS
- `{{ origin }}` - źródło zamówienia (kiosk, app, etc.)
- `{{ status }}` - status zamówienia
- `{{ estimated_time }}` - szacowany czas
- `{{ created_at }}` - data utworzenia
- `{{ updated_at }}` - data aktualizacji
- Itp. (wszystkie pola z rekordu)

### Standardowe placeholdery kontekstu
- `{{ trigger.source }}` - źródło triggera
- Inne dostępne z klasy bazowej `BaseAction`

## Automatyczne wykrywanie pola telefonu

Jeśli `phone_field` nie jest podane, akcja automatycznie szuka pola w następującej kolejności:
1. `client_phone_number`
2. `telefon`
3. `phone` 
4. `numer_telefonu`
5. `phone_number`
6. `tel`

## Normalizacja numerów telefonów

Akcja automatycznie normalizuje numery do formatu wymaganego przez bramkę SMS:
- `+48123456789` → `48123456789`
- `123 456 789` → `48123456789` (dodaje prefix 48 dla polskich numerów)
- `123-456-789` → `48123456789`

## Segmentacja długich wiadomości

Wiadomości dłuższe niż `max_length` (domyślnie 160 znaków) są automatycznie dzielone na segmenty i wysyłane osobno.

## Obsługa błędów

### Globalne wyłączenie SMS
Jeśli `sms.enabled = false`, akcja zostaje pominięta bez błędu.

### Limiter kolejnych błędów
Jeśli `sms.max_error_attempts` jest ustawione, akcja zostanie pominięta po przekroczeniu liczby kolejnych błędów.

### Flaga ignore_errors
Przy `ignore_errors: true` akcja nie przerwie scenariusza nawet jeśli wysyłka nie powiedzie się.

## Wymagania dotyczące danych triggera

Akcja wymaga, aby `trigger_data` zawierało listę rekordów (słowników), gdzie każdy rekord reprezentuje jednego klienta z danymi do personalizacji wiadomości.

### Przykład poprawnych danych triggera:

```json
{
  "trigger_data": {
    "zamowienia_gotowe": [
      {
        "id": 42,
        "aps_id": 28,
        "origin": "kiosk",
        "status": "order_processing_has_started",
        "pickup_number": 1,
        "kds_order_number": 1,
        "client_phone_number": "+48123456789",
        "estimated_time": 0,
        "created_at": "2025-05-30 13:36:25.203 +0200",
        "updated_at": "2025-09-10 09:50:20.137 +0200"
      },
      {
        "id": 43,
        "aps_id": 28,
        "origin": "kiosk", 
        "status": "order_processing_has_started",
        "pickup_number": 2,
        "kds_order_number": 2,
        "client_phone_number": "987654321",
        "estimated_time": 0,
        "created_at": "2025-05-30 14:01:56.559 +0200",
        "updated_at": "2025-09-10 09:50:20.210 +0200"
      }
    ]
  }
}
```

## Logowanie

Akcja zapisuje szczegółowe logi o:
- Liczbie znalezionych rekordów klientów
- Używanym polu telefonu
- Każdej wysłanej wiadomości (z ID SMS)
- Błędach wysyłki
- Końcowym podsumowaniu (ile wysłano/ile łącznie)

## Integracja z orchestratorem

Akcja jest automatycznie rejestrowana w orchestratorze przez mechanizm skanowania modułów. Nie wymaga ręcznej konfiguracji poza ustawieniami SMS w konfiguracji głównej.

## Bezpieczeństwo

- Nie loguje treści wiadomości ani numerów telefonów w pełnej formie
- Respektuje ustawienia globalnego wyłączenia SMS
- Obsługuje certyfikaty TLS dla bramki SMS
- Waliduje wszystkie dane wejściowe

## Testowanie

Akcja jest w pełni pokryta testami jednostkowymi (81% pokrycia) testującymi:
- Pomyślną wysyłkę SMS
- Obsługę błędów konfiguracji i połączenia
- Automatyczne wykrywanie pól telefonu  
- Normalizację numerów
- Segmentację długich wiadomości
- Personalizację treści
- Różne scenariusze błędów
