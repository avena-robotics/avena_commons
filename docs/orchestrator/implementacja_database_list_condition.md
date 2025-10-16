# Implementacja rozszerzenia modelu bazy danych o obsługę list rekordów

## Opracowanie

### Cel zadania
Rozszerzenie obecnego warunku bazy danych w orchestratorze o możliwość sprawdzania i pobierania wielu rekordów spełniających określone kryteria (np. zamówienia w stanie "refund"), oraz udostępnienie tej listy w akcjach scenariusza.

### Analiza obecnej architektury
Przed implementacją przeprowadzono analizę istniejącego kodu:

1. **DatabaseCondition** - istniejący warunek sprawdzający pojedynczy rekord w bazie danych
2. **DatabaseComponent** - komponent zarządzający połączeniami z PostgreSQL
3. **ConditionFactory** - fabryka rejestrująca i tworząca warunki
4. **ActionContext** - kontekst przekazywania danych między warunkami a akcjami

### Wybrana strategia implementacji
Zdecydowano się na utworzenie nowej klasy `DatabaseListCondition` dziedziczącej po `DatabaseCondition` zamiast modyfikacji istniejącej klasy, co zapewnia:
- Pełną zgodność wsteczną z istniejącymi scenariuszami
- Czytelny podział odpowiedzialności
- Łatwość utrzymania kodu

### Zaimplementowane komponenty

#### 1. Rozszerzenie DatabaseComponent
Dodano metodę `fetch_records()` umożliwiającą pobieranie wielu rekordów:

```python
async def fetch_records(
    self,
    table: str,
    columns: list[str],
    where_conditions: Dict[str, Any],
    limit: Optional[int] = None,
    order_by: Optional[str] = None,
) -> list[Dict[str, Any]]
```

**Funkcjonalności:**
- Pobieranie wielu rekordów z określonymi kolumnami
- Obsługa warunków WHERE z konwersją enumów
- Opcjonalne sortowanie i limitowanie wyników
- Pełne wsparcie dla async/await
- Zachowanie bezpieczeństwa z użyciem parametryzowanych zapytań

#### 2. Nowa klasa DatabaseListCondition
Utworzono nową klasę warunku:

```python
class DatabaseListCondition(DatabaseCondition)
```

**Kluczowe cechy:**
- Dziedziczy po DatabaseCondition wykorzystując wspólną logikę
- Dodaje obsługę pobierania list rekordów
- Zapisuje wyniki w kontekście pod kluczem `result_key`
- Zwraca `True` gdy znaleziono rekordy, `False` gdy lista pusta
- Pełna walidacja konfiguracji

**Przykład konfiguracji:**
```json
{
  "database_list": {
    "component": "main_database",
    "table": "zamowienia",
    "columns": ["id", "numer_zamowienia", "stan_zamowienia"],
    "where": {
      "stan_zamowienia": "refund"
    },
    "result_key": "zamowienia_do_zwrotu",
    "limit": 100,
    "order_by": "data_utworzenia DESC"
  }
}
```

#### 3. Modyfikacja Orchestrator
Zaktualizowano metodę `_should_execute_scenario()` aby:
- Zwracała tuple `(bool, Dict[str, Any])` zamiast tylko boolean
- Przekazywała dane z warunków do kontekstu wykonania scenariusza
- Łączyła dane z warunków z systemowymi danymi trigger

#### 4. Rejestracja w systemie
- Dodano import w `__init__.py` modułu conditions
- Zarejestrowano typ `"database_list"` w ConditionFactory
- Utworzono przykładowe scenariusze demonstrujące użycie

### Przykłady użycia

#### Scenariusz obsługi zwrotów
```json
{
  "name": "Obsługa zamówień do zwrotu",
  "trigger": {
    "type": "automatic",
    "conditions": {
      "database_list": {
        "component": "main_database",
        "table": "zamowienia", 
        "columns": ["id", "numer_zamowienia", "klient_id", "wartosc_zamowienia"],
        "where": {
          "stan_zamowienia": "refund"
        },
        "result_key": "zamowienia_do_zwrotu",
        "limit": 50
      }
    }
  },
  "actions": [
    {
      "type": "log_event",
      "message": "Znaleziono {{ trigger.zamowienia_do_zwrotu|length }} zamówień do zwrotu"
    },
    {
      "type": "send_email",
      "body": "{% for zamowienie in trigger.zamowienia_do_zwrotu %}Zamówienie {{ zamowienie.numer_zamowienia }}\n{% endfor %}"
    }
  ]
}
```

#### Dostęp do danych w akcjach
Dane są dostępne przez:
- `{{ trigger.result_key }}` - pełna lista rekordów
- `{{ trigger.result_key|length }}` - liczba rekordów
- `{{ trigger.result_key[0].kolumna }}` - wartość z pierwszego rekordu

### Testy
Utworzono kompletny zestaw testów jednostkowych:
- Test podstawowej funkcjonalności pobierania rekordów
- Test scenariusza bez wyników (pusta lista)
- Test walidacji konfiguracji
- Mockowanie komponentów bazodanowych

## Podsumowanie

Implementacja została zakończona pomyślnie i obejmuje:

1. **Rozszerzenie DatabaseComponent** o metodę `fetch_records()` z pełnym wsparciem dla PostgreSQL
2. **Nową klasę DatabaseListCondition** zapewniającą pobieranie i udostępnianie list rekordów
3. **Modyfikację Orchestrator** dla przekazywania danych z warunków do akcji
4. **Pełną integrację** z systemem warunków i rejestrację w ConditionFactory
5. **Przykładowe scenariusze** demonstrujące praktyczne zastosowanie
6. **Kompleksowe testy** weryfikujące poprawność implementacji
7. **Zachowanie zgodności wstecznej** z istniejącymi scenariuszami

Nowa funkcjonalność umożliwia orchestratorowi efektywną obsługę zamówień w stanie "refund" oraz innych scenariuszy wymagających przetwarzania list rekordów z bazy danych. System jest gotowy do wykorzystania w środowisku produkcyjnym.
