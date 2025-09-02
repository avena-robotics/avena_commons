# Przegląd Systemu IO Event Listener
::: io_event_listener
    options:
      members_order: source
      show_root_heading: true
      show_source: true

## Wprowadzenie

System Event Listener stanowi fundament architektury sterowanej zdarzeniami, umożliwiając płynną komunikację między różnymi komponentami poprzez mechanizm asynchronicznych zdarzeń. Zapewnia on stabilne i elastyczne środowisko dla przepływu informacji w systemie rozproszonym, gdzie różne komponenty mogą działać niezależnie, ale w skoordynowany sposób.

## Klasa bazowa EventListener

EventListener to klasa bazowa, która dostarcza kluczowe funkcjonalności dla wszystkich komponentów systemu zdolnych do odbierania i przetwarzania zdarzeń. Jej głównym zadaniem jest zarządzanie cyklem życia zdarzeń w systemie - od ich przyjęcia, przez analizę, przetwarzanie, aż po ewentualne przekazanie dalej.

### Kluczowe funkcjonalności

- **Wielowątkowa obsługa zdarzeń** - równoległe przetwarzanie wielu zdarzeń
- **Priorytetyzacja zdarzeń** - obsługa zdarzeń według ich ważności
- **Endpoints HTTP** - integracja z FastAPI umożliwiająca komunikację przez REST API
- **Trwałość stanu** - zachowywanie stanu między restartami systemu
- **Bezpieczna synchronizacja** - mechanizmy blokad dla operacji współbieżnych
- **Dynamiczna konfiguracja** - elastyczne dostosowywanie zachowania systemu

### Przepływ zdarzeń

Zdarzenia w systemie przechodzą przez kilka etapów:

1. **Przyjęcie** - zdarzenie trafia do systemu poprzez endpoint FastAPI
2. **Analiza** - system decyduje jak zdarzenie powinno być obsłużone
3. **Przetwarzanie** - wykonanie odpowiednich akcji związanych ze zdarzeniem
4. **Przekazanie** - opcjonalne przekierowanie zdarzenia do innych komponentów

Ten proces jest obsługiwany przez dedykowane wątki, które monitorują różne kolejki zdarzeń i reagują na zmiany w czasie rzeczywistym.

## Implementacja IO_server

IO_server rozszerza funkcjonalność bazowego EventListener, dodając specjalistyczne mechanizmy do zarządzania urządzeniami wejścia/wyjścia. Jego głównym zadaniem jest pośredniczenie między logiką biznesową a fizycznymi urządzeniami, takimi jak czujniki, silniki czy inne elementy wykonawcze.

### System dynamicznej konfiguracji urządzeń

Jedną z kluczowych cech IO_server jest dynamiczny system konfiguracji urządzeń, który umożliwia:

- Definiowanie struktury urządzeń w pliku JSON bez konieczności modyfikacji kodu źródłowego
- Automatyczne ładowanie i inicjalizację urządzeń na podstawie konfiguracji
- Tworzenie hierarchii urządzeń (np. urządzenia na magistrali)
- Abstrahowanie złożoności sprzętowej za pomocą urządzeń wirtualnych

### Architektura konfiguracji

Plik konfiguracyjny systemu IO wykorzystuje przejrzystą strukturę hierarchiczną z trzema głównymi sekcjami:

- **bus** - definicje magistrali komunikacyjnych (np. Modbus, I2C)
- **device** - definicje fizycznych urządzeń podłączonych do systemu
- **virtual_device** - abstrakty wyższego poziomu, agregujące funkcje urządzeń fizycznych

Taka struktura pozwala na oddzielenie warstw abstrakcji i ułatwia zarządzanie złożonymi systemami sprzętowymi.

## Proces ładowania konfiguracji

Proces inicjalizacji systemu IO obejmuje kilka kluczowych etapów, które zapewniają prawidłowe przygotowanie wszystkich komponentów sprzętowych:

### 1. Przygotowanie środowiska

Na początku system tworzy kontenery dla różnych typów urządzeń:
- Magistrale komunikacyjne
- Urządzenia fizyczne
- Urządzenia wirtualne

### 2. Wczytanie i analiza konfiguracji

System wczytuje plik JSON i segreguje zawartość według typów urządzeń. Każdy typ jest przetwarzany oddzielnie, ponieważ różne typy urządzeń wymagają różnych parametrów inicjalizacji i mogą mieć różne zależności.

### 3. Sekwencja inicjalizacji

Inicjalizacja przebiega w ściśle określonej kolejności:

1. **Magistrale (Buses)** - najpierw inicjalizowane są magistrale, ponieważ inne urządzenia mogą być od nich zależne. Przykładem jest magistrala Modbus, która stanowi medium komunikacyjne dla urządzeń podrzędnych.

2. **Urządzenia fizyczne (Physical Devices)** - następnie inicjalizowane są urządzenia fizyczne. Jeśli urządzenie wymaga połączenia z magistralą, otrzymuje referencję do odpowiedniego obiektu magistrali.

3. **Urządzenia wirtualne (Virtual Devices)** - na końcu tworzone są urządzenia wirtualne, które są abstrakcyjnymi warstwami nad urządzeniami fizycznymi. Ich zadaniem jest dostarczenie uproszczonego interfejsu dla złożonych operacji sprzętowych.

### 4. Dynamiczne tworzenie instancji

Dla każdego elementu konfiguracji system:

1. Odnajduje odpowiednią klasę przez dynamiczny import modułu
2. Tworzy instancję z odpowiednimi parametrami
3. Konfiguruje dodatkowe właściwości
4. Zapisuje referencję w odpowiednim kontenerze

Szczególną uwagę poświęcono obsłudze błędów - każdy nieudany import lub inicjalizacja są rejestrowane i nie przerywają całego procesu.

## Typowe przypadki użycia

Typowy scenariusz wykorzystania systemu IO obejmuje:

1. **Definicja magistrali** - np. Modbus RTU podłączony przez port szeregowy
2. **Konfiguracja sterowników urządzeń** - np. sterownik silnika z określonym adresem na magistrali
3. **Abstrakcja wysokiego poziomu** - np. "podajnik" łączący funkcje sterownika silnika i czujników

Po inicjalizacji system oferuje ujednolicony interfejs do kontrolowania urządzeń - aplikacja może wysyłać zdarzenia wysokiego poziomu (np. "uruchom podajnik"), a system IO tłumaczy je na niskopoziomowe operacje sprzętowe.

## Monitorowanie i cykl pracy

System implementuje mechanizm regularnego sprawdzania stanu urządzeń wirtualnych. W określonych odstępach czasu (domyślnie 100 razy na sekundę) wywoływana jest metoda `tick()` na każdym urządzeniu wirtualnym, co pozwala na:

- Regularną aktualizację stanu urządzenia
- Wykrywanie zmian i reagowanie na nie
- Symulację zachowań zależnych od czasu
- Generowanie zdarzeń na podstawie warunków

## Obsługa zdarzeń

Gdy system otrzymuje zdarzenie, analizuje je pod kątem źródła i typu. Na podstawie tych informacji wybierana jest odpowiednia metoda obsługi. Obecnie system jest skonfigurowany głównie do obsługi zdarzeń z komponentu "munchies_algo", ale architektura pozwala na łatwe rozszerzenie o nowe źródła.

## Przykład praktyczny

W dołączonym przykładzie konfiguracyjnym zdefiniowano:

- Magistralę Modbus RTU na porcie `/dev/ttyUSB0`
- Sterownik silnika TLO57R24V08 z określonym adresem i typem konfiguracji
- Urządzenie wirtualne "feeder1", które udostępnia wysokopoziomowe metody do sterowania podajnikiem

Ta konfiguracja pokazuje, jak system umożliwia abstrakcję złożoności sprzętowej - zamiast bezpośrednio obsługiwać rejestry Modbus, aplikacja może używać intuicyjnych metod jak `run()` czy `stop()`.

## Podsumowanie

System Event Listener, a w szczególności jego implementacja IO_server, zapewnia elastyczne i rozszerzalne środowisko do zarządzania komunikacją z urządzeniami sprzętowymi. Dzięki dynamicznemu ładowaniu konfiguracji, obsłudze zdarzeń i warstwom abstrakcji, umożliwia on tworzenie skalowalnych i łatwych w utrzymaniu systemów sterowania.