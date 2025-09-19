# Optymalizacja Template Rendering w BaseAction

## Opracowanie

Zaimplementowano ulepszoną obsługę renderowania templateów Jinja2 w klasie BaseAction, która zachowuje oryginalne typy danych dla pojedynczych zmiennych, jednocześnie zapewniając standardowe renderowanie tekstowe dla mieszanych templateów.

### Zmiany implementacyjne:

1. **Rozszerzona metoda `_resolve_template_variables`**:
   - Dodano regex pattern `r'^\s*\{\{\s*([^}]+)\s*\}\}\s*$'` do wykrycia pojedynczych zmiennych
   - Implementacja bezpośredniego dostępu do wartości z kontekstu dla `{{ variable }}`
   - Obsługa zagnieżdżonych kluczy przez notację kropkową `{{ data.key.subkey }}`
   - Fallback do standardowego renderowania Jinja2 dla mieszanych templateów

2. **Dodana metoda `_get_nested_value`**:
   - Pomocnicza funkcja do nawigacji przez zagnieżdżone struktury danych
   - Obsługuje zarówno słowniki (dict) jak i obiekty (getattr)
   - Zachowuje oryginalne typy danych podczas traversowania

3. **Rozszerzona metoda `_resolve_nested_templates`**:
   - Rekurencyjne przetwarzanie zagnieżdżonych struktur (dict, list)
   - Wywołuje `_resolve_template_variables` tylko dla stringów
   - Zachowuje typy dla wszystkich innych danych (int, float, bool, None)

4. **Zaktualizowana metoda `_get_config_value`**:
   - Używa `_resolve_nested_templates` zamiast tylko sprawdzania stringów
   - Zapewnia zachowanie typów dla wszystkich wartości konfiguracyjnych

### Przykłady użycia:

```python
# Pojedyncza zmienna - zachowuje oryginalny typ
"{{ my_dict }}" → zwraca dict
"{{ my_list }}" → zwraca list
"{{ my_number }}" → zwraca int/float

# Zagnieżdżone klucze - zachowuje typ
"{{ data.config.timeout }}" → zwraca int/float
"{{ user.settings }}" → zwraca dict

# Mieszany tekst - renderuje jako string
"Wynik: {{ my_dict.key }} dla użytkownika" → zwraca string
"Status: {{ status }} ({{ timestamp }})" → zwraca string
```

### Obsługa błędów:
- Logowanie błędów dostępu do zmiennych przez `avena_commons.util.logger`
- Graceful handling missing keys/attributes
- Fallback do oryginalnego tekstu przy błędach renderowania

## Podsumowanie

Implementacja zapewnia:
- **Zachowanie typów danych** dla pojedynczych zmiennych Jinja2
- **Standardowe renderowanie tekstowe** dla mieszanych templateów
- **Obsługę zagnieżdżonych struktur** przez notację kropkową
- **Rekurencyjne przetwarzanie** złożonych struktur danych
- **Kompatybilność wsteczną** z istniejącym kodem

Przebieg pracy:
- Zidentyfikowano potrzebę zachowania oryginalnych typów danych w template rendering
- Zastosowano regex do wykrywania pojedynczych zmiennych vs mieszanych templateów
- Dodano bezpośredni dostęp do kontekstu dla zachowania typów
- Zaimplementowano rekurencyjne przetwarzanie zagnieżdżonych struktur
- Zachowano kompatybilność z istniejącymi funkcjonalnościami Jinja2
- Dodano odpowiednie obsługę błędów i logowanie

Rozwiązanie umożliwia elastyczne użycie templateów zachowując wydajność i czytelność kodu.