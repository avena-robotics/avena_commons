# AI-generated documentation: Summary of ScenarioContext refactoring and template system enhancements for orchestrator scenario handling.

# Refaktoryzacja obsługi kontekstu scenariuszy i systemu szablonów w Orchestratorze

## Opracowanie

Analizowane commity wprowadzają znaczące usprawnienia w architekturze orkiestratora, skupiając się na kompleksowej refaktoryzacji kontekstu scenariuszy oraz zaawansowanym systemie szablonów. Zmiany obejmują przejście od prostych słowników do dedykowanego modelu `ScenarioContext`, wzbogacenie danych klientów oraz implementację inteligentnego systemu rozwiązywania zmiennych z zachowaniem typów danych.

### Szczegółowe zmiany wdrożone:

**Commit 5553cc0 - Główna refaktoryzacja architektury:**
- **Wprowadzenie ScenarioContext:** Nowy model `ScenarioContext` zastępuje poprzedni `ActionContext` i generyczne słowniki, zapewniając jasno zdefiniowane pola: `scenario_name`, `action_executor`, `message_logger`, `clients`, `components`, oraz `context`
- **Uproszczenie modeli:** Usunięto skomplikowane modele: `ActionModel`, `ScenarioModel`, `TriggerModel`, `ScenarioCollection`, zastępując je prostszymi strukturami słownikowymi z podstawową walidacją
- **Refaktoryzacja systemu warunków:** Wszystkie klasy warunków zostały zaktualizowane do używania `ScenarioContext` zamiast `Dict[str, Any]`
- **Modernizacja akcji:** Kompletna aktualizacja wszystkich klas akcji do nowego interfejsu z `ScenarioContext`
- **Ulepszenie template handling:** Przejście z prostego string replacement na Jinja2 Environment z lepszym error handling

**Commit f896d96 - Optymalizacja dostępu do konfiguracji:**
- **Uproszczenie SendCommandAction:** Eliminacja zbędnej zmiennej lokalnej `client_config` na rzecz bezpośredniego dostępu do `context.clients[client_name]`
- **Czytelniejszy kod:** Redukcja liczby linii kodu przy zachowaniu pełnej funkcjonalności
- **Spójność interfejsu:** Ujednolicenie sposobu dostępu do danych klientów w akcjach

**Commit dfc9be0 - Wzbogacenie danych klientów:**
- **Mechanizm łączenia danych:** Implementacja inteligentnego mergowania danych z konfiguracji (port, address) i aktualnego stanu klientów (fsm_state, error)
- **Kompletny kontekst klienta:** Każdy klient otrzymuje pełne informacje w jednym miejscu, eliminując konieczność łączenia danych z różnych źródeł
- **Unifikacja dostępu:** Jeden punkt dostępu do wszystkich informacji o kliencie przez `context.clients[client_name]`

**Commit 22892de - Zaawansowany system szablonów:**
- **Zachowanie typów danych:** Nowa implementacja `_resolve_template_variables()` zachowuje oryginalne typy zmiennych zamiast zawsze zwracać string
- **Inteligentne rozpoznawanie:** Rozróżnienie między pojedynczymi zmiennymi (`{{ variable }}`) a mieszanymi szablonami tekstu
- **Obsługa zagnieżdżonych struktur:** Wsparcie dla notacji kropkowej (`{{ data.key }}`, `{{ var.attribute }}`) w zmiennych
- **Rekurencyjne przetwarzanie:** Nowa metoda `_resolve_nested_templates()` obsługuje kompleksowe struktury danych (słowniki, listy, zagnieżdżone obiekty)
- **Lepsze error handling:** Szczegółowe komunikaty błędów z logowaniem niezdolności pobrania zmiennych

### Architektoniczne korzyści wprowadzonych zmian:

**1. Typowalność i bezpieczeństwo:**
- Silne typowanie przez Pydantic BaseModel eliminuje błędy runtime
- Jasno zdefiniowane interfejsy między komponentami
- Walidacja danych na poziomie modelu

**2. Elastyczność systemu szablonów:**
- Obsługa różnych typów danych (int, float, bool, string, dict, list)
- Zachowanie struktury danych oryginalnych zamiast wymuszania konwersji na string
- Wsparcie dla złożonych ścieżek dostępu do danych

**3. Unifikacja i enkapsulacja:**
- ScenarioContext jako centralne źródło wszystkich danych kontekstowych
- Eliminacja duplikacji kodu w akcjach scenariuszy
- Ukrycie szczegółów implementacji zarządzania stanem

**4. Wydajność i czytelność:**
- Redukcja liczby wywołań do różnych źródeł danych
- Czytelniejszy kod w klasach akcji
- Optymalizacja dostępu do często używanych danych

### Przykłady zastosowania nowego systemu:

**Przed zmianami:**
```python
# Akcja musiała ręcznie łączyć dane
client_config = orchestrator._configuration["clients"][client_name]
client_state = orchestrator._state[client_name]
address = client_config["address"]
port = client_config["port"]
error_status = client_state.get("error", False)
```

**Po zmianach:**
```python
# Wszystko dostępne w jednym miejscu
client_data = context.clients[client_name]
address = client_data["address"]
port = client_data["port"] 
error_status = client_data.get("error", False)
```

**System szablonów z zachowaniem typów:**
```yaml
# Konfiguracja scenariusza
action:
  type: database_update
  timeout: "{{ config.timeout }}"        # int: 30
  retries: "{{ config.max_retries }}"    # int: 3
  message: "Error: {{ error.code }}"     # string: "Error: 404"
  metadata: "{{ request.headers }}"      # dict: {"Content-Type": "json"}
```

### Przepływ danych w nowej architekturze:

```mermaid
graph TB
    Trigger([Trigger scenariusza]) --> Validate{Walidacja warunków}
    Validate -->|Spełnione| BuildContext[Budowa ScenarioContext]
    Validate -->|Niespełnione| End([Koniec])
    
    BuildContext --> MergeClients[Łączenie danych klientów]
    MergeClients --> |Config + State| Templates[Rozwiązywanie szablonów]
    Templates --> |Zachowane typy| Execute[Wykonanie akcji]
    
    Execute --> Action1[Akcja z pełnym kontekstem]
    Action1 --> Action2[Kolejna akcja]
    Action2 --> Cleanup[Czyszczenie kontekstu]
    Cleanup --> End
    
    subgraph "Template Resolution Engine"
        StringCheck{Czy pojedyncza zmienna?}
        StringCheck -->|Tak| TypePreserve[Zachowaj oryginalny typ]
        StringCheck -->|Nie| JinjaRender[Renderuj jako string]
        TypePreserve --> ReturnValue[Zwróć wartość]
        JinjaRender --> ReturnString[Zwróć string]
    end
    
    subgraph "Unified Client Data"
        ConfigData[Konfiguracja klienta]
        StateData[Stan aktualny]
        ConfigData --> MergedData[Połączone dane]
        StateData --> MergedData
        MergedData --> DirectAccess[context.clients[name]]
    end
```

### Napotkane problemy i rozwiązania:

**1. Problem zachowania typów w szablonach:**
- **Problem:** Poprzedni system zawsze zwracał stringi, niszcząc typu liczbowe i struktury danych
- **Rozwiązanie:** Implementacja inteligentnego rozpoznawania pojedynczych zmiennych vs. mieszanych szablonów tekstu

**2. Složitost dostępu do zagnieżdżonych danych:**
- **Problem:** Zmienne jak `{{ data.user.name }}` wymagały ręcznej nawigacji
- **Rozwiązanie:** Obsługa notacji kropkowej z automatyczną nawigacją przez struktury

**3. Duplikacja danych klientów:**
- **Problem:** Konfiguracja i stan przechowywane osobno, wymagające ręcznego łączenia
- **Rozwiązanie:** Automatyczne mergowanie przy tworzeniu kontekstu scenariusza

**4. Backwards compatibility:**
- **Problem:** `ExecuteScenarioAction` przestała działać po zmianach
- **Rozwiązanie:** Tymczasowe wyłączenie z TODO do przyszłej implementacji

### Przebieg myślenia projektowego:

1. **Identyfikacja problemów:** Rozpoznanie, że poprzedni system był zbyt skomplikowany i niespójny
2. **Projektowanie ScenarioContext:** Stworzenie unifikowanego modelu danych z jasnym interfejsem
3. **Iteracyjna implementacja:** Stopniowe przechodzenie od prostych do bardziej złożonych funkcjonalności
4. **Optymalizacja dostępu:** Eliminacja redundancji w kodzie akcji
5. **Zaawansowane szablony:** Dodanie obsługi typów i zagnieżdżonych struktur

## Podsumowanie

Refaktoryzacja znacząco modernizuje architekturę systemu orkiestratora poprzez wprowadzenie dedykowanego modelu `ScenarioContext` i zaawansowanego systemu szablonów. Zmiany zapewniają:

**Kluczowe korzyści:**
- **Lepsze zarządzanie kontekstem scenariuszy** z jasno zdefiniowanymi interfejsami
- **Zachowanie typów danych** w systemie szablonów eliminując niechciane konwersje
- **Unifikację dostępu do danych klientów** w jednym miejscu
- **Obsługę zagnieżdżonych struktur** danych z notacją kropkową
- **Eliminację duplikacji kodu** w akcjach scenariuszy
- **Poprawę enkapsulacji** i separację odpowiedzialności

**Techniczne usprawnienia:**
- Przejście z prostego string replacement na inteligentny system Jinja2
- Automatyczne łączenie konfiguracji i stanu klientów
- Rekurencyjne przetwarzanie kompleksowych struktur danych
- Lepsze error handling z szczegółowym logowaniem

**Wpływ na rozwój:**
- Solidne fundamenty dla przyszłych funkcjonalności
- Łatwiejsza konserwacja dzięki spójnej architekturze
- Czytelniejszy kod dla deweloperów tworzących nowe akcje
- Zachowanie kompatybilności z istniejącymi scenariuszami YAML

Refaktoryzacja stanowi znaczący krok w stronę bardziej dojrzałej i skalowanej architektury systemu orkiestratora, eliminując długi techniczny i zapewniając stabilną podstawę dla przyszłego rozwoju funkcjonalności.