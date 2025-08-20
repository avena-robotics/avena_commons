# 📊 Dashboard z rozwijalnymi drzewami stanu klientów

## 🎯 Opis funkcjonalności

Dashboard wyświetla status klientów testowych i umożliwia przeglądanie ich wygenerowanych stanów w postaci **rozwijanego drzewa HTML**. Każdy klient testowy generuje losowy słownik stanu z zagnieżdżeniami, który jest wyświetlany w czytelnej formie.

## ✨ Nowe! Przebudowana architektura

Dashboard został **całkowicie przebudowany** zgodnie z najlepszymi praktykami programowania:

### 🔧 Modułowa struktura
- **Separacja logiki**: JavaScript wydzielony z template'ów do oddzielnych plików
- **Komentarze**: Obszerna dokumentacja JSDoc w każdym module  
- **Organizacja kodu**: Logika podzielona na specjalizowane moduły
- **Responsywność**: Ulepszone style CSS z lepszą responsywnością
- **Accessibility**: Dodane atrybuty ARIA i obsługa nawigacji klawiaturą

### 📁 Struktura plików
```
src/avena_commons/dashboard/
├── templates/
│   ├── dashboard.html          # ✨ Przebudowany szablon (czytelny HTML)
│   └── base.html              # Szablon bazowy
└── static/
    ├── css/
    │   ├── dashboard.css          # Oryginalne style
    │   └── dashboard-tree.css     # ✨ NOWE: Rozszerzone style z drzewem
    └── js/
        ├── dashboard.js           # Kompatybilność wsteczna
        ├── dashboard-app.js       # ✨ NOWE: Główna logika aplikacji
        ├── dashboard-tree.js      # ✨ NOWE: Logika rozwijanego drzewa
        └── dashboard-utils.js     # ✨ NOWE: Funkcje pomocnicze
```

## 🚀 Funkcje

- ✅ **Rozwijane drzewo JSON** - Hierarchiczne wyświetlanie zagnieżdżonych słowników
- ✅ **Kolorowe wyróżnianie** - Różne kolory dla stringów, liczb, booleanów  
- ✅ **Interaktywne rozwijanie** - Kliknij aby rozwinąć/zwinąć sekcje
- ✅ **Losowy stan** - Każdy klient generuje unikatowy stan z losowymi danymi
- ✅ **Real-time monitoring** - Automatyczne odświeżanie statusu
- ✅ **Responsywny UI** - Nowoczesny interfejs Bootstrap 5
- ✨ **NOWE: Toast notifications** - Eleganckie powiadomienia o błędach/sukcesach
- ✨ **NOWE: Lepsze formatowanie** - Inteligentne formatowanie liczb i dat
- ✨ **NOWE: Obsługa błędów** - Robustna obsługa problemów z API
- ✨ **NOWE: Dark mode** - Automatyczne wsparcie trybu ciemnego
- ✨ **NOWE: Accessibility** - Pełne wsparcie dostępności (ARIA, keyboard navigation)

## 🛠️ Uruchomienie

### 1. Uruchom klientów testowych
```bash
python tests/test_client.py 
```

### 2. Uruchom dashboard (w nowym terminalu)
```bash
python tests/test_dashboard.py
```

### 3. Otwórz dashboard w przeglądarce
```
http://127.0.0.1:10600/dashboard
```

## 📖 Jak używać

1. **Otwórz dashboard** - Przejdź do `http://127.0.0.1:10600/dashboard`
2. **Znajdź klienta** - Zobaczysz karty klientów (test_9201, test_9202, test_9203)
3. **Kliknij "Szczegóły"** - Przycisk przy każdym kliencie pokazuje podstawowe informacje
4. **Kliknij "Dane"** - Przycisk pokazuje liczbę kluczy danych i otwiera rozwijalne drzewo
5. **Przeglądaj drzewo** - Modal pokazuje rozwijalne drzewo z danymi stanu:
   - **▼/▶** - Rozwiń/zwiń sekcje
   - **Kolorowe wartości** - Strings (niebieskie), liczby (czerwone), booleany (pomarańczowe)
   - **Zagnieżdżenia** - Hierarchiczna struktura z wcięciami
   - **Hover efekty** - Podświetlenie elementów przy najechaniu

## 🔧 Nowa architektura modułów

### 📦 dashboard-app.js - Główna logika
```javascript
// Użycie w Alpine.js template
x-data="dashboardApp({{ api_port }})"

// Główne funkcje:
- refreshData()          // Pobieranie danych z API
- updateMetrics()        // Aktualizacja statystyk
- filteredServices      // Computed property filtrowania
- showServiceDetails()   // Modal ze szczegółami
- showServiceData()      // Modal z drzewem danych
```

### 🌳 dashboard-tree.js - Drzewo JSON
```javascript
// Generowanie drzewa
DashboardTree.generateTreeHTML(data)

// Główne funkcje:
- createTreeView()       // Główna funkcja tworzenia drzewa
- createArrayView()      // Renderowanie tablic
- createObjectView()     // Renderowanie obiektów  
- formatValue()          // Formatowanie wartości z typami
- toggleNode()           // Rozwijanie/zwijanie węzłów
```

### 🛠️ dashboard-utils.js - Funkcje pomocnicze
```javascript
// Toast notifications
DashboardUtils.showToast(message, type, duration)

// Formatowanie danych
DashboardUtils.formatNumber(num, options)
DashboardUtils.formatBytes(bytes, decimals)
DashboardUtils.formatDuration(seconds)
DashboardUtils.formatPercentage(value, isDecimal)

// Walidacja
DashboardUtils.isValidUrl(url)
DashboardUtils.isValidEmail(email)
DashboardUtils.isValidIP(ip)

// LocalStorage
DashboardUtils.saveToStorage(key, value)
DashboardUtils.loadFromStorage(key, defaultValue)

// Funkcje czasowe
DashboardUtils.debounce(func, wait)
DashboardUtils.throttle(func, limit)
```

## 🗂️ Struktura wygenerowanego stanu

Każdy klient generuje losowy stan zawierający:

```json
{
  "client_info": {
    "name": "test_9201",
    "port": 9201,
    "startup_time": 1641234567.89,
    "session_id": "session_12345"
  },
  "config": {
    "max_connections": 100,
    "timeout": 30,
    "features": {
      "logging": true,
      "caching": false,
      "monitoring": {
        "enabled": true,
        "interval": 5
      }
    }
  },
  "runtime_data": {
    // Losowe zagnieżdżone dane generowane rekurencyjnie
  },
  "statistics": {
    "request_count": 1337,
    "response_times": [23, 45, 12, 67],
    "error_rates": {
      "404": 0.02,
      "500": 0.001
    }
  },
  "user_preferences": {
    // Preferencje użytkownika
  },
  "cache": {
    // Losowe dane cache
  }
}
```

## 💡 Dodatkowe funkcje

### ✨ Auto-odświeżanie
Dashboard automatycznie odświeża status co 5 sekund (można wyłączyć).

### 🔍 Filtry i wyszukiwanie  
- Szukaj klientów po nazwie (case-insensitive)
- Filtruj po statusie: online, offline, oczekujące
- Real-time filtrowanie bez przeładowania strony

### 📊 Metyki systemu
Dashboard pokazuje liczby w czasie rzeczywistym:
- **Online klientów** (zielona karta)
- **Offline klientów** (czerwona karta)  
- **Oczekujących połączeń** (żółta karta)
- **Łączna liczba** (niebieska karta)

### 🔔 Powiadomienia
- Toast notifications dla błędów API
- Ostrzeżenia o timeout połączenia
- Informacje o statusie odświeżania

### ♿ Dostępność
- Obsługa nawigacji klawiaturą
- Atrybuty ARIA dla screen readerów
- Semantyczne znaczniki HTML
- Odpowiednie role i labels

## 🛑 Zatrzymywanie

- **Klienci**: Ctrl+C w terminalu z `tests\test_client.py`
- **Dashboard**: Ctrl+C w terminalu z `tests\test_dashboard.py`

## 🐛 Debugowanie

Jeśli dashboard nie działa prawidłowo:

1. **Sprawdź konsolę przeglądarki** - Nowe moduły logują szczegółowe informacje
2. **Sprawdź czy klienci działają**: `python debug_client_response.py`
3. **Sprawdź logi** w folderze `temp/`
4. **Sprawdź konfigurację**: `test_dashboard_config.json`
5. **Sprawdź moduły**: Otwórz konsolę i wpisz `checkModulesAvailability()`

### 🔧 Debugowanie w konsoli
```javascript
// Sprawdź status modułów
checkModulesAvailability()

// Pokaż przewodnik migracji  
showMigrationGuide()

// Sprawdź wsparcie przeglądarki
DashboardLegacy.checkBrowserSupport()

// Wymuś test toast notifications
DashboardUtils.showToast('Test wiadomość', 'success')
```

## 🎨 Customizacja

Możesz dostosować:

### 🎨 Style wizualne
- **Kolory drzewa** - Edytuj CSS w `dashboard-tree.css`
- **Responsywność** - Media queries w sekcjach `@media`
- **Dark mode** - Kolory w sekcji `@media (prefers-color-scheme: dark)`
- **Animacje** - Timing i efekty transition w CSS

### ⚙️ Zachowanie aplikacji
```javascript
// Zmiana częstotliwości odświeżania (domyślnie 5s)
// W dashboard-app.js, linia z setInterval(5000)

// Dodanie nowych formatów dla drzewa
// W dashboard-tree.js, funkcja formatValue()

// Dostosowanie toast notifications
// W dashboard-utils.js, konfiguracja showToast()
```

### 📊 Struktura danych
- **Modyfikuj `_generate_random_state()`** w `test_client.py`
- **Dodaj nowe typy danych** z custom formatowaniem
- **Zmień głębokość zagnieżdżenia** w konfiguracji drzewa

## 🔄 Migracja z poprzedniej wersji

Jeśli używałeś poprzedniej wersji dashboard'a:

### ✅ Kompatybilność wsteczna
- Wszystkie stare funkcje nadal działają
- `showToast()` i `formatNumber()` przekierowują na nowe moduły
- Ostrzeżenia w konsoli pomogą w migracji

### 🆕 Zalecana migracja
```javascript
// STARE użycie → NOWE użycie:
showToast(msg, type)           → DashboardUtils.showToast(msg, type)
formatNumber(num)              → DashboardUtils.formatNumber(num)  
initializeDashboard(port)      → x-data="dashboardApp(port)" w HTML

// W HTML template:
// STARE:
<script>initializeDashboard({{ api_port }})</script>

// NOWE:  
<div x-data="dashboardApp({{ api_port }})" x-init="init()">
```

## 📚 Dokumentacja techniczna

### 🔧 Wymagania
- **Przeglądarka**: Nowoczesna przeglądarka z obsługą ES6, Fetch API, CSS Grid
- **Bootstrap 5.3+**: Dla stylów i komponentów UI
- **Alpine.js 3.13+**: Dla reaktywności template'ów
- **Font Awesome 6.5+**: Dla ikon

### 📖 API Reference
Każdy moduł zawiera szczegółową dokumentację JSDoc:
- Opisy funkcji i parametrów
- Przykłady użycia
- Typy danych (TypeScript-style)
- Informacje o deprecation

### 🧪 Testowanie
Moduły zawierają wbudowane mechanizmy debugging:
- Szczegółowe logi console z emoji
- Sprawdzanie kompatybilności przeglądarki
- Fallback'i dla brakujących funkcji
- Obsługa błędów z user-friendly komunikatami

---

**💡 TIP**: Dla najlepszego doświadczenia, otwórz konsolę deweloperską (F12) podczas używania dashboard'a - moduły logują użyteczne informacje diagnostyczne!
