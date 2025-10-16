# Akcja `evaluate_condition` - Dokumentacja

## Opis

Akcja `evaluate_condition` implementuje logikę warunkową if-then-else w scenariuszach orchestratora. Pozwala na ewaluację warunków i wykonanie różnych akcji w zależności od wyniku sprawdzenia.

## Konfiguracja

```yaml
type: evaluate_condition
conditions: []      # Lista warunków do sprawdzenia (wymagane)
true_actions: []    # Lista akcji do wykonania gdy warunki są spełnione (opcjonalne)
false_actions: []   # Lista akcji do wykonania gdy warunki nie są spełnione (opcjonalne)
```

### Parametry

- **`conditions`** (wymagane): Lista warunków do sprawdzenia. Wszystkie warunki muszą być spełnione (logika AND).
- **`true_actions`** (opcjonalne): Lista akcji do wykonania gdy wszystkie warunki są spełnione.
- **`false_actions`** (opcjonalne): Lista akcji do wykonania gdy przynajmniej jeden warunek nie jest spełniony.

> **Uwaga:** Należy zdefiniować przynajmniej `true_actions` lub `false_actions`.

## Logika działania

1. **Ewaluacja warunków**: Wszystkie warunki z listy `conditions` są sprawdzane z użyciem logiki AND.
2. **Wybór akcji**: W zależności od wyniku wybierana jest odpowiednia lista akcji.
3. **Wykonanie akcji**: Akcje są wykonywane sekwencyjnie w podanej kolejności.
4. **Przerwanie przy błędzie**: Jeśli jedna z akcji zakończy się błędem, wykonywanie zostaje przerwane.

## Wartość zwracana

```json
{
  "condition_result": true,         // Wynik ewaluacji warunków
  "executed_branch": "true_actions", // Która gałąź została wykonana
  "executed_actions_count": 2,      // Liczba wykonanych akcji
  "action_results": [               // Szczegóły wykonanych akcji
    {
      "action_index": 0,
      "action_type": "log_event",
      "status": "success",
      "result": {...}
    }
  ]
}
```

## Przykłady użycia

### Przykład 1: Prosty warunek z akcjami

```yaml
- type: evaluate_condition
  conditions:
    - type: client_state
      client: main_database
      state: READY
  true_actions:
    - type: log_event
      level: info
      message: "📊 Baza danych jest gotowa - kontynuuję proces"
    - type: send_command
      target: "@all"
      command: CMD_INITIALIZE
  false_actions:
    - type: log_event
      level: warning
      message: "⚠️ Baza danych nie jest gotowa - czekam"
    - type: wait_for_state
      target: main_database
      state: [READY]
      timeout: 30s
```

### Przykład 2: Wielokrotne warunki (logika AND)

```yaml
- type: evaluate_condition
  conditions:
    - type: client_state
      client: main_database
      state: READY
    - type: client_state
      client: io_service
      state: READY
    - type: time
      time_range: "08:00-18:00"
  true_actions:
    - type: log_event
      level: info
      message: "✅ Wszystkie warunki spełnione - uruchamiam proces produkcyjny"
    - type: execute_scenario
      scenario_name: production_start
  false_actions:
    - type: log_event
      level: debug
      message: "⏸️ Warunki nie spełnione - proces wstrzymany"
```

### Przykład 3: Restart zamówień z błędami

```yaml
- type: evaluate_condition
  description: "Restart zamówień ze statusem error"
  conditions:
    - type: database
      component: main_database
      table: aps_order
      column: "COUNT(*)"
      where:
        status: error
      operator: greater
      expected_value: 0
  true_actions:
    - type: log_event
      level: info
      message: "🔄 Znaleziono {{ action_result.count }} zamówień z błędami - rozpoczynam restart"
    - type: restart_orders
      component: main_database
      orders_source: "{{ trigger.error_orders }}"
      clone_config:
        copy_fields: ["aps_id", "origin", "client_phone_number"]
        default_values:
          pickup_number: null
    - type: send_email
      to: "{{ trigger.admin_email }}"
      subject: "Restart zamówień zakończony"
      message: "Restartowano {{ action_result.success_count }} zamówień"
  false_actions:
    - type: log_event
      level: debug
      message: "ℹ️ Brak zamówień wymagających restartu"
```

### Przykład 4: Warunkowe wysłanie powiadomień

```yaml
- type: evaluate_condition
  conditions:
    - type: error_message
      pattern: "critical"
      source: "any"
  true_actions:
    - type: send_sms
      phone_number: "{{ trigger.admin_phone }}"
      message: "🚨 Błąd krytyczny: {{ trigger.error_message }}"
    - type: send_email
      to: ["admin@company.com", "support@company.com"]
      subject: "Błąd krytyczny w systemie"
      message: "Szczegóły: {{ trigger.error_message }}"
  false_actions:
    - type: log_event
      level: info
      message: "📝 Błąd niekrityczy - zapisano w logach"
```

## Obsługiwane typy warunków

Akcja `evaluate_condition` współpracuje ze wszystkimi dostępnymi typami warunków:

- **`client_state`**: Sprawdza stan komponentu/klienta
- **`database`**: Sprawdza wartość w bazie danych
- **`database_list`**: Sprawdza listę rekordów z bazy danych
- **`time`**: Sprawdza zakres czasowy
- **`error_message`**: Sprawdza komunikaty błędów
- **`and`, `or`, `not`, `xor`, `nand`, `nor`**: Warunki logiczne

## Najlepsze praktyki

### 1. Organizacja warunków

```yaml
# ✅ Dobrze - jasne i czytelne warunki
conditions:
  - type: client_state
    client: main_database
    state: READY
  - type: time
    time_range: "09:00-17:00"

# ❌ Źle - zbyt skomplikowane zagnieżdżenie
conditions:
  - type: and
    conditions:
      - type: or
        conditions:
          - type: client_state
            client: db1
            state: READY
```

### 2. Opisowe komunikaty

```yaml
# ✅ Dobrze - komunikaty opisują co się dzieje
true_actions:
  - type: log_event
    level: info
    message: "🔄 Uruchamiam backup bazy danych - wszystkie serwisy gotowe"
    description: "Rozpoczęcie procesu backup"

# ❌ Źle - komunikaty niejasne
true_actions:
  - type: log_event
    message: "OK"
```

### 3. Obsługa błędów

```yaml
# ✅ Dobrze - zawsze zdefiniuj false_actions
false_actions:
  - type: log_event
    level: warning
    message: "⚠️ Warunki backup nie spełnione - spróbuję ponownie za 5 minut"
  - type: send_email
    to: "admin@company.com"
    subject: "Backup wstrzymany"
```

### 4. Użycie zmiennych z triggera

```yaml
conditions:
  - type: database
    table: orders
    where:
      order_id: "{{ trigger.order_id }}"
true_actions:
  - type: log_event
    message: "Przetwarzam zamówienie {{ trigger.order_id }}"
```

## Rozwiązywanie problemów

### Problem: Warunki zawsze zwracają false

**Sprawdź:**
1. Składnię warunków - czy wszystkie wymagane pola są obecne
2. Stan komponentów - czy komponenty są dostępne w `orchestrator._state`
3. Formatowanie wartości - czy typy danych są zgodne z oczekiwanymi

### Problem: Akcje nie są wykonywane

**Sprawdź:**
1. Czy zdefiniowane są `true_actions` lub `false_actions`
2. Czy akcje w liście mają poprawną składnię (`type` jest wymagane)
3. Logi orchestratora - tam znajdziesz szczegółowe informacje o błędach

### Problem: Błędy wykonania akcji

**Sprawdź:**
1. Czy wszystkie komponenty wymagane przez akcje są dostępne
2. Czy parametry akcji (np. adresy email, numery telefonów) są poprawne
3. Uprawnienia - czy orchestrator ma dostęp do zewnętrznych serwisów

## Przykład debugowania

```yaml
- type: evaluate_condition
  description: "Debug - sprawdź warunki przed głównym procesem"
  conditions:
    - type: client_state
      client: target_service
      state: READY
  true_actions:
    - type: log_event
      level: debug
      message: "🔍 DEBUG: target_service w stanie READY - kontynuuję"
      show_trigger: true  # Pokaż dane triggera
    - type: test
      message: "Debug: aktualny stan systemu"
      show_config: true
  false_actions:
    - type: log_event
      level: debug
      message: "🔍 DEBUG: target_service nie jest READY - stan: {{ orchestrator.state.target_service.fsm_state }}"
```
