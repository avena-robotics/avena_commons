# Analiza Wydajności Pepper Camera → Pepper EventListener

## Architektura Procesów

### PepperCamera EventListener Process (Core 1)
- **Typ**: EventListener z PepperCameraConnector + PepperCameraWorker
- **Architektura**: Główny proces + worker subprocess (komunikacja przez pipe)
- **Odpowiedzialność**: 
  - Ciągłe przechwytywanie klatek z kamery Orbec
  - Fragmentacja obrazów na 4 ROI
  - Serializacja fragmentów do JSON/base64
  - Wysyłanie przez HTTP do Pepper EventListener
- **Cykl Pracy**:
  1. Worker subprocess: `grab_frames_from_camera()` → `fragment_image()` → `serialize_fragments()`
  2. Główny proces: `_send_fragments_to_pepper_listener()` via HTTP POST
  3. Powtarzanie cyklu przy 30Hz
- **Zarządzanie Stanem**: CameraState (IDLE→INITIALIZING→INITIALIZED→STARTING→STARTED)

### Pepper EventListener Process (Core 1)  
- **Typ**: EventListener z PepperConnector + PepperWorker
- **Architektura**: Główny proces + worker subprocess (komunikacja przez pipe)
- **Odpowiedzialność**:
  - Odbieranie fragmentów JSON przez HTTP
  - Deserializacja base64 → numpy arrays
  - Wykonanie algorytmu pepper vision
  - Logowanie wyników detekcji
- **Cykl Pracy**:
  1. Główny proces: `_analyze_event()` → `_deserialize_fragments()`
  2. Worker subprocess: `process_fragments()` → pepper vision algorithm
  3. Buforowanie wyników i przygotowanie do następnego cyklu
- **Zarządzanie Stanem**: PepperState (IDLE→INITIALIZING→INITIALIZED→STARTING→STARTED→PROCESSING)

## Przepływ Operacji Pipeline

### 1. Przechwytywanie Klatek (PepperCamera EventListener)
- **Źródło**: Kamera Orbec Gemini 335Le (192.168.1.10)
- **Proces**: Ciągłe przechwytywanie klatek przy 30 FPS
- **Wyjście**: Dane klatek kolorowych + głębi

### 2. Fragmentacja Klatek (PepperCamera Worker)
- **Wejście**: Klatki 640x400 kolor + głębia
- **Proces**: Podział na 4 regiony ROI (lewy-górny, prawy-górny, lewy-dolny, prawy-dolny)
- **Konfiguracja**: Na podstawie `pepper_camera_autonomous_benchmark_config.json`
- **Wyjście**: 4 obiekty fragmentów na klatkę

### 3. Serializacja (PepperCamera Worker)
- **Proces**: Konwersja numpy arrays → base64 JSON
- **Format**: `{'data': base64_string, 'dtype': numpy_dtype, 'shape': array_shape}`
- **Transport**: HTTP POST do Pepper EventListener

### 4. Przetwarzanie Fragmentów (Pepper EventListener)
- **Wejście**: Fragmenty JSON przez HTTP
- **Deserializacja**: base64 JSON → numpy arrays
- **Przetwarzanie**: Algorytm pepper vision (szczegóły poniżej)
- **Wyjście**: Wyniki przetwarzania (detekcja overflow, itp.)

#### Operacje Computer Vision w Pepper Processing:
1. **Tworzenie Maski Papryki**:
   - Konwersja BGR → HSV
   - Filtrowanie kolorów czerwonych (dolny i górny zakres HSV)
   - Łączenie masek metodą bitwise OR

2. **Rafinacja Maski**:
   - Operacje morfologiczne: opening (kernel 5x5, 1 iteracja)
   - Operacje morfologiczne: closing (kernel 10x10, 1 iteracja)
   - Usuwanie szumu i wypełnianie dziur

3. **Detekcja Obecności Papryki**:
   - Analiza głębi w obszarach maski
   - Obliczanie średniej głębi z pikseli papryki
   - Porównanie z progiem maksymalnej głębi (245)

4. **Detekcja Dziury**:
   - Konwersja BGR → LAB, ekstrakcja kanału L
   - Gaussian blur (kernel 3x3)
   - CLAHE (Contrast Limited Adaptive Histogram Equalization)
   - Progowanie adaptacyjne na podstawie mediany
   - Detekcja konturów metodą RETR_EXTERNAL
   - Sprawdzenie odległości konturu od centrum obrazu

5. **Detekcja Wypełnienia**:
   - Tworzenie stref wewnętrznej i zewnętrznej (koła koncentryczne)
   - Analiza głębi w strefie wewnętrznej vs zewnętrznej
   - Obliczanie różnicy median głębi
   - Sprawdzenie procentu wypełnienia strefy wewnętrznej

6. **Detekcja Overflow**:
   - Algorytm wykrywania przepełnienia papryki
   - Analiza kombinacji: obecność + dziura + wypełnienie

## Metryki Wydajności (test 60-sekundowy)

### Użycie Zasobów Systemowych
- **Przypisanie Rdzeni**: Oba serwisy na Core 1
- **Użycie CPU**: 17.3% średnio, 50% szczyt
- **Pamięć**: 320.5 MB średnio (stabilne)
- **CPU Systemowe**: 4.6% ogółem

### Wydajność PepperCamera
- **Przetworzone Klatki**: 1,992 klatek
- **Wygenerowane Fragmenty**: 7,968 (4 na klatkę)
- **Tempo Przetwarzania**: 26.6 FPS
- **Średni Czas Klatki**: 3.09ms
- **Zakres**: 0.90ms - 10.59ms
- **Błędy**: 0

### Wydajność Pepper  
- **Sesje Przetwarzania**: 1,944 sesji
- **Przetworzone Fragmenty**: 7,844 fragmentów
- **Tempo Przetwarzania**: 25.9 sesji/sek
- **Średni Czas Sesji**: 2.17ms
- **Przepustowość**: 460.6 fragmentów/sek
- **Deserializacja**: <0.01ms (sub-milisekunda)
- **Zakres**: 1.57ms - 14.61ms
- **Błędy**: 0

## Analiza Efektywności Pipeline

### Integralność Przepływu Danych
- **Stosunek Klatka→Fragment**: 1:4 (idealny)
- **Utrata Fragmentów**: ~124 fragmenty (1.5% - w tolerancji HTTP)
- **Dopasowanie Przetwarzania**: 1,944/1,992 = 97.6% ukończonych sesji

### Analiza Wąskich Gardeł
- **Główne Ograniczenie**: Przetwarzanie vision (2.17ms śr.)
- **Drugorzędne**: Przechwytywanie/fragmentacja klatek (3.09ms śr.)  
- **Obciążenie Sieciowe**: Minimalne (deserializacja <0.01ms)

### Charakterystyki Wydajności
- **Utrzymana Przepustowość**: ~26 FPS end-to-end
- **Stabilność Przetwarzania**: Niska wariancja, stała wydajność
- **Efektywność Zasobów**: 17% wykorzystania CPU z miejscem na skalowanie
- **Ślad Pamięci**: Stabilny (320MB, brak wycieków)

## Podstawa dla Akceleracji GPU
Obecna wydajność tylko-CPU zapewnia bazę odniesienia:
- **Przetwarzanie Vision**: 2.17ms średnio na zestaw fragmentów
- **Całkowity Pipeline**: 5.26ms średnio (przechwytywanie + przetwarzanie)
- **Cel dla GPU**: <1ms na zestaw fragmentów dla znaczącej poprawy
