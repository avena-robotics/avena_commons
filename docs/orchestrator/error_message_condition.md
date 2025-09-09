# Error Message Condition - Warunek sprawdzający komunikaty błędów

## Opis

Warunek `error_message_condition` umożliwia uruchamianie scenariuszy w zależności od konkretnych urządzeń lub typów błędów zawartych w komunikatach błędów (`error_message`) od klientów IO.

## Cel

Umożliwia tworzenie scenariuszy specyficznych dla konkretnych urządzeń, które reagują tylko na błędy związane z danym urządzeniem, zamiast ogólnego scenariusza reagującego na wszystkie błędy.

## Konfiguracja

```json
{
  "error_message": {
    "mode": "contains|starts_with|regex|exact",
    "pattern": "tekst_do_wyszukania",
    "case_sensitive": false,
    "fault_clients_only": true,
    "error_clients_only": false,
    "all_clients": false
  }
}
```

### Parametry

#### Wymagane
- **`pattern`** (string) - Wzorzec do wyszukania w komunikacie błędu

#### Opcjonalne
- **`mode`** (string, domyślnie: "contains") - Tryb dopasowania:
  - `contains` - sprawdza czy error_message zawiera określony tekst
  - `starts_with` - sprawdza czy error_message zaczyna się od określonego tekstu
  - `regex` - sprawdza czy error_message pasuje do wzorca regex
  - `exact` - sprawdza dokładne dopasowanie error_message

- **`case_sensitive`** (boolean, domyślnie: false) - Czy uwzględniać wielkość liter

- **`fault_clients_only`** (boolean, domyślnie: true) - Sprawdzać tylko klientów w stanie FAULT

- **`error_clients_only`** (boolean, domyślnie: false) - Sprawdzać tylko klientów z error=True

- **`all_clients`** (boolean, domyślnie: false) - Sprawdzać wszystkich klientów niezależnie od stanu

## Przykłady użycia

### 1. Błąd konkretnej wydawki

```json
{
  "error_message": {
    "mode": "contains",
    "pattern": "feeder1",
    "case_sensitive": false,
    "fault_clients_only": true
  }
}
```

Uruchomi scenariusz gdy którykolwiek klient w stanie FAULT będzie miał error_message zawierający "feeder1".

### 2. Błędy robota (regex)

```json
{
  "error_message": {
    "mode": "regex",
    "pattern": "(robot|fairino|arm|gripper|collision)",
    "case_sensitive": false,
    "fault_clients_only": true
  }
}
```

Uruchomi scenariusz gdy error_message będzie zawierał którekolwiek ze słów: robot, fairino, arm, gripper, collision.

### 3. Konkretny komunikat błędu

```json
{
  "error_message": {
    "mode": "exact",
    "pattern": "IO Device timeout",
    "case_sensitive": true,
    "all_clients": true
  }
}
```

Uruchomi scenariusz gdy error_message będzie dokładnie równy "IO Device timeout" (uwzględniając wielkość liter).

### 4. Błędy zaczynające się od prefiksu

```json
{
  "error_message": {
    "mode": "starts_with",
    "pattern": "MODBUS:",
    "case_sensitive": false,
    "error_clients_only": true
  }
}
```

Uruchomi scenariusz gdy error_message zaczyna się od "MODBUS:" u klientów z error=true.

## Kombinowanie z innymi warunkami

Warunek można łączyć z innymi warunkami używając operatorów logicznych:

```json
{
  "and": {
    "conditions": [
      {
        "client_state": {
          "any_service_in_state": ["FAULT"]
        }
      },
      {
        "error_message": {
          "mode": "contains",
          "pattern": "feeder1",
          "case_sensitive": false,
          "fault_clients_only": true
        }
      }
    ]
  }
}
```

## Scenariusze przykładowe

### Wyłączenie wadliwej wydawki

Scenariusz `disable_faulty_feeder.json` reaguje na błędy zawierające "feeder1" i:
1. Wysyła powiadomienia SMS/email
2. Wyłącza konkretną wydawkę
3. Pozwala systemowi kontynuować pracę z pozostałymi wydawkami

### Obsługa błędów robota

Scenariusz `handle_robot_error.json` reaguje na błędy robota i:
1. Natychmiast zatrzymuje ruch robota
2. Wstrzymuje wszystkie operacje systemu
3. Wysyła alerty krytyczne
4. Dostarcza szczegółowe instrukcje naprawy

## Priorytety scenariuszy

Scenariusze specyficzne dla urządzeń powinny mieć wyższy priorytet (niższą wartość) niż ogólne scenariusze:

- `handle_robot_error.json` - priorytet 1 (najwyższy)
- `disable_faulty_feeder.json` - priorytet 5
- `pause_on_fault_services.json` - priorytet 10 (najniższy)

Dzięki temu system najpierw uruchomi scenariusz specyficzny dla urządzenia, a dopiero potem ogólny scenariusz bezpieczeństwa.

## Logowanie i debugowanie

Warunek loguje szczegółowe informacje o dopasowaniach:

```
ErrorMessageCondition: dopasowanie znalezione w kliencie 'io_server': 
'feeder1: nie wydał tacki' pasuje do wzorca 'feeder1' (tryb: contains)
```

```
ErrorMessageCondition: warunek spełniony - znaleziono 1 dopasowań: ['io_server']
```

## Obsługa błędów

- Nieprawidłowy wzorzec regex zostanie zarejestrowany jako błąd
- Brak wymaganego parametru `pattern` spowoduje zwrócenie False
- Nieprawidłowy tryb `mode` spowoduje ValueError

## Wydajność

Warunek jest zoptymalizowany pod kątem wydajności:
- Wzorce regex są kompilowane tylko raz
- Sprawdzanie odbywa się tylko dla klientów spełniających kryteria zakresu
- Wczesne wyjście przy pierwszym dopasowaniu (jeśli nie potrzeba wszystkich)
