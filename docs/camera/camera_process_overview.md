# Proces Działania Systemu Kamery Avena Commons - Zwięzły Opis

## Architektura i Komponenty

**Główne elementy:**
- **Camera** (EventListener) - zarządza stanem i eventami
- **GeneralCameraWorker/Connector** - uniwersalny system worker-connector 
- **OrbecGemini335Le** - specjalizowany sterownik dla kamery Orbbec

**Stany systemu:**
System przechodzi przez 8 stanów: IDLE → INITIALIZING → INITIALIZED → STARTING → STARTED → RUNNING → STOPPING → STOPPED (plus ERROR)

## Przepływ Inicjalizacji

1. **Uruchomienie EventListenera**
   - Camera tworzy instancję na podstawie konfiguracji
   - Wybiera odpowiedni sterownik (np. OrbecGemini335Le)
   - Konfiguruje parametry kamery (rozdzielczość, ekspozycja, wzmocnienie)

2. **Konfiguracja Worker-Connector**
   - Worker działa w osobnym procesie
   - Komunikacja przez pipe (synchroniczna)
   - Connector zapewnia interfejs do głównego procesu

3. **Inicjalizacja kamery**
   - Tworzenie kontekstu i urządzenia sieciowego
   - Konfiguracja właściwości sprzętowych
   - Ustawienie pipeline'u i profili strumieni
   - Konfiguracja wyrównania (depth-to-color alignment)
   - Włączenie filtrów (spatial, temporal)

## Obsługa Eventów

**Otrzymywanie eventu:**
- Event typu "take_photo_qr" lub "take_photo_box" dociera do Camera
- System analizuje typ eventu i konfiguruje odpowiedni detektor
- Ustawia konfigurację postprocessingu dla wybranego detektora

**Konfiguracja detektorów:**
- QR detector: konfiguracja rozmiarów kodów QR dla różnych pozycji
- Box detector: konfiguracja progów detekcji pudełek
- Każdy detektor może mieć wielokrotne konfiguracje postprocessingu

## Przetwarzanie Obrazu

**Pobieranie ramek:**
1. Worker cyklicznie pobiera ramki z kamery (kolor + głębia)
2. Aplikuje filtry sprzętowe/programowe
3. Synchronizuje ramki koloru i głębi z timeoutem
4. Konwertuje dane do numpy arrays

**Wieloprocesowe przetwarzanie:**
1. Tworzy ProcessPoolExecutor z liczbą workerów = liczba konfiguracji postprocessingu
2. Każdy worker otrzymuje ramkę i swoją konfigurację
3. Wysyła zadania równolegle do wszystkich workerów
4. Zbiera wyniki z timeout'em

**Przetwarzanie wyników:**
- **QR detection**: sortuje kody według pozycji, łączy wyniki z confidence, sprawdza kompletność (4 kody)
- **Box detection**: znajduje pierwszy poprawny box, anuluje pozostałe zadania
- Konwertuje wyniki do pozycji 6DOF (x,y,z,rx,ry,rz)

## Synchronizacja i Komunikacja

**Worker ↔ Connector:**
- Synchroniczna komunikacja przez pipe z mutexami
- Komendy: CAMERA_INIT, CAMERA_START_GRABBING, SET_POSTPROCESS_CONFIGURATION
- Worker odpowiada potwierdzeniami lub danymi

**Cykl życia przetwarzania:**
1. STARTED - pobieranie ramek
2. RUNNING - przetwarzanie w ProcessPool
3. Zwrot wyników lub timeout
4. STOPPING - zatrzymanie pipeline'u

## Obsługa Błędów i Odzyskiwanie

**Automatyczne mechanizmy:**
- Wykrywanie uszkodzonych pul procesów i ich odtwarzanie
- Timeout'y na wszystkie operacje asynchroniczne
- Anulowanie zadań przy pierwszym sukcesie (box detection)
- Graceful degradation przy błędach sprzętowych

**Monitoring:**
- Strukturalne logowanie z pomiarami czasu
- Globalne statystyki wydajności
- Śledzenie stanów procesów i błędów

## Konfiguracja

**Parametry kamery:**
- Adres IP, rozdzielczość, FPS, ekspozycja, wzmocnienie
- Konfiguracja alignment (depth-to-color)
- Filtry: spatial, temporal
- Parametry kalibracji (macierz kamery, dystorsja)

**Pipeline'y detekcji:**
- Definicja detektorów (qr_detector, box_detector)
- Konfiguracje postprocessingu dla każdego detektora
- Parametry specyficzne (rozmiary QR, progi detekcji)

## Wyniki

System zwraca:
- **Sukces**: pozycje 6DOF obiektów w formacie {id: (x,y,z,rx,ry,rz)}
- **Błąd**: komunikat błędu z kontekstem
- **Brak detekcji**: puste wyniki

Cały proces jest zoptymalizowany pod kątem wydajności czasu rzeczywistego z automatycznym odzyskiwaniem po błędach.
