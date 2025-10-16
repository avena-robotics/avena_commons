# Implementacja RestartOrdersAction

## Opracowanie

### Cel i zakres funkcjonalności

RestartOrdersAction to zaawansowana akcja orchestratora odpowiedzialna za automatyczny restart zamówień na podstawie dostępności produktów w magazynie. Akcja została zaprojektowana w celu obsługi scenariuszy, gdzie zamówienia muszą być ponownie uruchomione po awarii systemu, problemach z wydawkami lub innych incydentach operacyjnych.

### Architektura i integracja

Akcja dziedziczy po BaseAction i integruje się z istniejącym systemem orchestratora poprzez:
- DatabaseComponent do komunikacji z bazą danych PostgreSQL
- ActionContext do przekazywania danych kontekstowych
- ActionExecutor do rejestracji i wykonywania akcji
- System szablonów zmiennych dla elastycznej konfiguracji

### Główne komponenty biznesowe

#### 1. Walidacja dostępności produktów
- Pobieranie pozycji zamówień (aps_order_item) dla każdego zamówienia
- Grupowanie produktów według item_id z sumowaniem ilości
- Sprawdzanie dostępności w tabeli storage_item_slot
- Logika: każdy aps_order_item reprezentuje 1 sztukę produktu

#### 2. Zarządzanie transakcjami
- Atomowe operacje na bazie danych z pełnym rollback w przypadku błędów
- Obsługa timeout'ów i błędów połączenia
- Izolacja zmian na poziomie transakcji PostgreSQL

#### 3. Klonowanie zamówień
- Konfigurowalny zestaw kopiowanych pól (copy_fields)
- Możliwość pominięcia wybranych pól (skip_fields)
- Ustawianie wartości domyślnych (default_values)
- Automatyczne generowanie nowych ID i timestamp'ów

#### 4. Zarządzanie statusami (stałe, niekonfigurowalne)
- Oryginalne zamówienie: status "canceled" 
- Nowe zamówienie: status "paid" (gotowe do realizacji)
- Produkty w nowym zamówieniu: status "reserved" (zarezerwowane)
- Zamówienia bez dostępnych produktów: status "refund_pending" (wymaga zwrotu)

### Struktura danych

#### Tabele bazodanowe
- **aps_order**: główna tabela zamówień (15 pól)
- **aps_order_item**: pozycje zamówień (7 pól, każda = 1 produkt)
- **storage_item_slot**: stan magazynu (8 pól z current_quantity)

#### Konfiguracja akcji
```json
{
  "type": "restart_orders",
  "component": "main_database",
  "orders_source": "{{ variable_with_orders }}",
  "clone_config": {
    "copy_fields": ["field1", "field2"],
    "skip_fields": ["pickup_number"],
    "default_values": {"field": "value"}
  }
}
```

### Algorytm wykonania

1. **Walidacja wejścia**: Sprawdzenie obecności zamówień w orders_source
2. **Rozpoczęcie transakcji**: Utworzenie atomowej transakcji PostgreSQL
3. **Dla każdego zamówienia**:
   - Pobranie pozycji zamówienia (aps_order_item)
   - Grupowanie produktów i sprawdzenie dostępności
   - Decyzja o klonowaniu lub refund na podstawie dostępności
4. **Operacje bazodanowe**:
   - Zmiana statusu oryginalnego zamówienia na "canceled"
   - Utworzenie nowego zamówienia (jeśli produkty dostępne)
   - Kopiowanie pozycji zamówienia z statusem "reserved"
   - Lub ustawienie statusu "refund_pending" (jeśli brak produktów)
5. **Finalizacja**: Commit transakcji i zwrócenie raportu

### Obsługa błędów i logowanie

#### Poziomy logowania
- **INFO**: Start/koniec procesu, statystyki
- **DEBUG**: Szczegóły operacji dla każdego zamówienia
- **WARNING**: Produkty niedostępne, problemy z danymi
- **ERROR**: Błędy transakcji, problemy z bazą danych

#### Typy błędów
- **ConfigurationError**: Nieprawidłowa konfiguracja akcji
- **DatabaseError**: Problemy z połączeniem/transakcją
- **DataValidationError**: Nieprawidłowe dane zamówień
- **TimeoutError**: Przekroczenie czasu operacji

### Integracja z systemem

#### Rejestracja w ActionExecutor
```python
from .restart_orders_action import RestartOrdersAction
# Automatyczna rejestracja w _register_default_actions()
```

#### Export w module actions
```python
from .restart_orders_action import RestartOrdersAction
__all__ = [..., "RestartOrdersAction"]
```

### Scenariusze użycia

#### 1. Restart zamówień z niesprawnej wydawki
- Filtrowanie zamówień po pickup_number
- Klonowanie bez kopiowania pickup_number

#### 2. Restart zamówień z błędami
- Okresowy restart zamówień ze statusem "error"
- Resetowanie pickup_number na null
- Powiadomienia email o wynikach

#### 3. Migracja zamówień po aktualizacji systemu
- Masowy restart zamówień po zmianach w systemie
- Konfigurowalny zestaw kopiowanych pól
- Raportowanie postępu operacji

## Podsumowanie

RestartOrdersAction to kompleksowe rozwiązanie do zarządzania restartami zamówień w systemie APS. Implementacja zapewnia atomowość operacji, elastyczną konfigurację oraz szczegółowe raportowanie wyników. Akcja integruje się seamlessly z istniejącym systemem orchestratora i może być wykorzystywana w różnych scenariuszach operacyjnych.

Kluczowe zalety implementacji:
- Atomowość operacji dzięki transakcjom PostgreSQL
- Elastyczna konfiguracja kopiowanych pól i wartości domyślnych
- Szczegółowe logowanie i raportowanie błędów
- Automatyczna walidacja dostępności produktów
- Obsługa różnych scenariuszy biznesowych (wydawki, błędy, migracje)
- Pełna integracja z systemem template variables orchestratora

Implementacja jest gotowa do użycia w środowisku produkcyjnym z przykładowymi scenariuszami JSON demonstrującymi praktyczne zastosowania.
