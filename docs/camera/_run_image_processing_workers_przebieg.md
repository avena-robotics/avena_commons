# Przebieg procesu przetwarzania obrazów QR kodów i boxów

## Opracowanie

Dokument opisuje kompletny proces przetwarzania obrazów w systemie kamer, obejmujący wykrywanie QR kodów oraz boxów (kontenerów). Główną metodą odpowiedzialną za ten proces jest `_run_image_processing_workers` w klasie `GeneralCameraWorker`, która zarządza równoległym przetwarzaniem obrazów w wielu procesach z wykorzystaniem `ProcessPoolExecutor`.

## Architektura systemu przetwarzania

### Komponenty systemu

**1. GeneralCameraWorker**
- Główna klasa zarządzająca cyklem życia kamery
- Odpowiedzialna za pobieranie ramek i koordynację przetwarzania
- Zarządza ProcessPoolExecutor dla równoległego przetwarzania

**2. Detektory obrazów**
- Moduły z `avena_commons.vision.detector`
- Specjalizowane funkcje do wykrywania QR kodów i boxów
- Wykonywane w oddzielnych procesach roboczych

**3. System scalania wyników**
- Moduły `merge` i `sorter` z `avena_commons.vision`
- Łączenie wyników z różnych konfiguracji detektorów
- Sortowanie według pozycji i pewności detekcji

### Typy przetwarzanych obiektów

#### QR kody
- Używane do identyfikacji pozycji w systemie
- Maksymalnie 4 QR kody na scenie
- Każdy QR kod ma przypisaną pozycję (1-4)
- Zwracane jako pozycje 3D (x, y, z, rx, ry, rz)

#### Boxy (kontenery)
- **TODO**: Implementacja wykrywania boxów w trakcie rozwoju


### Przebieg wykonania

#### 1. Walidacja i przygotowanie executor-a

**Sprawdzenie dostępności executor-a:**
- Funkcja: `if not self.executor:`
- Dane wejściowe: `self.executor` (ProcessPoolExecutor lub None)
- Zwracane: `None` jeśli executor nie istnieje

**Sprawdzenie stanu executor-a:**
- Funkcja: `self._is_executor_broken()`
- Dane wejściowe: `self.executor` (sprawdzenie właściwości `_broken`)
- Zwracane: `bool` - True jeśli executor jest uszkodzony

**Odtworzenie uszkodzonego executor-a:**
- Funkcja: `await self._recreate_executor_if_broken()`
- Dane wejściowe: brak (używa `self.executor`)
- Zwracane: `bool` - True jeśli udało się odtworzyć executor

#### 2. Submit zadań do procesów roboczych

**Iteracja przez workery:**
- Dane wejściowe: `self.image_processing_workers` (lista słowników z kluczami "detector", "config")
- Dla każdego workera wykonywane jest:

**Submit zadania:**
```python
future = self.executor.submit(
    worker.get("detector"),           # Funkcja detektora (np. z avena_commons.vision.detector)
    frame=frame,                      # Ramki obrazu (dict z kluczami 'color', 'depth', etc.)
    camera_config=self.camera_configuration,  # Konfiguracja kamery
    config=worker.get("config")       # Konfiguracja konkretnego detektora
)
```

**Dane przekazywane do detektora:**
- `frame`: dict z ramkami obrazu (np. {'color': numpy.array, 'depth': numpy.array})
- `camera_config`: dict z parametrami kamery (macierz kamery, parametry kalibracji)
- `config`: dict z konfiguracją detektora (progi, parametry algorytmu)

**Dane zwracane przez detektor:**
- `result[0]`: lista obiektów Detection (wykryte QR kody)
- `result[1]`: dict z danymi debug (opcjonalne)

#### 3. Obsługa błędów podczas submit

**Typy błędów:**
- `BrokenProcessPool`: uszkodzony pool procesów
- `RuntimeError`: problemy z procesami
- `Exception`: inne nieoczekiwane błędy

**Reakcja na błędy:**
- Liczenie nieudanych submit-ów (`failed_submits`)
- Próba odtworzenia executor-a przy pierwszym błędzie
- Kontynuacja z pozostałymi workerami

#### 4. Zbieranie wyników z procesów

**Iteracja przez zakończone zadania:**
- Funkcja: `as_completed(futures, timeout=30.0)`
- Dane wejściowe: `futures` (dict future -> config_id)
- Timeout: 30 sekund dla wszystkich zadań

**Pobieranie pojedynczego wyniku:**
- Funkcja: `future.result(timeout=10.0)`
- Dane wejściowe: future object
- Zwracane: tuple (Detection list, debug dict) lub None

#### 5. Przetwarzanie wyników detekcji

##### 5.1 Przetwarzanie QR kodów

**Sortowanie detekcji:**
- Funkcja: `sorter.sort_qr_by_center_position(expected_count=4, detections=result[0])`
- Dane wejściowe:
  - `expected_count`: int (4 - maksymalna liczba QR kodów)
  - `detections`: lista obiektów Detection
- Zwracane: posortowana lista Detection według pozycji środka

**Scalanie detekcji:**
- Funkcja: `merge.merge_qr_detections_with_confidence(sorted_detections, results)`
- Dane wejściowe:
  - `sorted_detections`: posortowana lista Detection
  - `results`: dict z dotychczasowymi wynikami (position_id -> Detection)
- Zwracane: zaktualizowany dict results

**Sprawdzenie kompletności:**
- Warunek: `actual_detections == 4`
- Akcja: anulowanie pozostałych zadań przez `self._cancel_pending_futures(futures)`

##### 5.2 Przetwarzanie boxów

**TODO**: Implementacja w trakcie rozwoju

#### 6. Konwersja na pozycje obiektów

##### 6.1 Konwersja pozycji QR kodów

**Iteracja przez wyniki QR:**
- Źródło: `results` (dict position_id -> Detection)

**Obliczanie pozycji przestrzennej:**
- Funkcja: `calculate_pose_pnp(corners, a, b, z, camera_matrix)`
- Dane wejściowe:
  - `corners`: array z narożnikami QR kodu z obiektu Detection
  - `a`: float (rozmiar QR w mm, z `self.postprocess_configuration["a"]["qr_size"] * 1000`)
  - `b`: float (rozmiar QR w mm, identyczny jak `a`)
  - `z`: float (0 - wysokość referencyjnej płaszczyzny)
  - `camera_matrix`: macierz kamery z `create_camera_matrix(self.camera_configuration["camera_params"])`
- Zwracane: dict z pozycją 3D (x, y, z, rx, ry, rz)

##### 6.2 Konwersja pozycji boxów

**TODO**: Implementacja w trakcie rozwoju


#### 7. Obsługa błędów podczas przetwarzania

**Typy błędów w trakcie zbierania wyników:**
- `ProcessLookupError`: proces został zakończony
- `BrokenProcessPool`: uszkodzony pool procesów
- `TimeoutError`: przekroczenie czasu oczekiwania
- `RuntimeError`: problemy z procesami
- `Exception`: inne błędy

**Reakcja na błędy:**
- Logowanie błędu
- Kontynuacja z następnym zadaniem lub przerwanie pętli
- Próba odtworzenia executor-a w przypadku problemów z pool-em

#### 8. Finalizacja i czyszczenie

**Anulowanie pozostałych zadań:**
- Funkcja: `self._cancel_pending_futures(futures)`
- Wykonywane: przy błędach lub gdy zebrano wszystkie 4 QR kody

**Zamknięcie executor-a (w przypadku błędu):**
- Wywołanie: `self.executor.shutdown(wait=False)`

### Dane wejściowe metody

```python
async def _run_image_processing_workers(self, frame: dict)
```

**Parametr `frame`:**
- Typ: `dict`
- Zawartość: ramki obrazu z kamery
- Przykładowa struktura:
```python
{
    'color': numpy.ndarray,  # obraz kolorowy
    'depth': numpy.ndarray,  # mapa głębi
    # ewentualnie inne typy ramek
}
```

### Dane zwracane przez metodę

#### Struktura wyników dla QR kodów

**W przypadku powodzenia:**
- Typ: `dict`
- Struktura: `{position_id: pose_dict}`
- Przykład:
```python
{
    1: {'x': 100.5, 'y': 200.3, 'z': 0.0, 'rx': 0.1, 'ry': 0.2, 'rz': 1.57},
    2: {'x': 150.2, 'y': 250.8, 'z': 0.0, 'rx': 0.0, 'ry': 0.1, 'rz': 1.60},
    3: {'x': 80.1, 'y': 180.5, 'z': 0.0, 'rx': -0.1, 'ry': 0.0, 'rz': 1.55},
    4: None,  # nie wykryto QR kodu na tej pozycji
}
```

#### Struktura wyników dla boxów

**TODO**: Struktura w trakcie projektowania


#### Przypadki błędów

**W przypadku błędu:**
- Typ: `None`
- Przyczyny: problemy z executor-em, timeout, błędy procesów

**W przypadku braku konfiguracji:**
- Typ: `None`
- Przyczyna: `self.postprocess_configuration` jest None

**W przypadku częściowego sukcesu:**
- Typ: `dict` z mieszanymi wynikami
- QR kody: pozycje tam gdzie wykryto, None gdzie nie wykryto
- Boxy: **TODO** 

### Kluczowe zależności

#### Zewnętrzne moduły - QR kody (aktualnie zaimplementowane)
- `avena_commons.vision.merge.merge_qr_detections_with_confidence`
- `avena_commons.vision.sorter.sort_qr_by_center_position`
- `avena_commons.vision.vision.calculate_pose_pnp`
- `avena_commons.vision.camera.create_camera_matrix`
- `avena_commons.vision.detector` - funkcje detektorów QR

#### Zewnętrzne moduły - Boxy (TODO - do implementacji)


#### Wewnętrzne właściwości
- `self.executor`: ProcessPoolExecutor
- `self.image_processing_workers`: lista konfiguracji workerów
- `self.camera_configuration`: konfiguracja kamery
- `self.postprocess_configuration`: konfiguracja postprocessingu (QR + boxy)
- `self._message_logger`: logger komunikatów

#### Konfiguracja postprocessingu

**Aktualna struktura (tylko QR):**
```python
postprocess_configuration = {
    "a": {"qr_size": 0.05, "detector_params": {...}},
    "b": {"qr_size": 0.05, "detector_params": {...}},
    # więcej konfiguracji QR...
}
```


## Podsumowanie

Dokument opisuje kompletny system przetwarzania obrazów obejmujący wykrywanie QR kodów i boxów (kontenerów). Aktualnie system w pełni obsługuje detekcję QR kodów z równoległym przetwarzaniem w wielu procesach, automatycznym zarządzaniem uszkodzonymi procesami oraz scalaniem wyników w spójną strukturę pozycji przestrzennych.

### Aktualny stan implementacji

**QR kody - ZAIMPLEMENTOWANE:**
- Równoległe przetwarzanie z wieloma konfiguracjami detektorów
- Sortowanie i scalanie detekcji według pozycji i pewności
- Konwersja na pozycje 3D z wykorzystaniem kalibracji kamery
- Robust error handling z odtwarzaniem uszkodzonych procesów
- Optymalizacja z early termination przy pełnym zestawie detekcji

**Boxy - TODO:**

### Zalety architektury

1. **Modularność** - łatwe dodawanie nowych typów detektorów
2. **Równoległość** - wykorzystanie wielu procesów dla wydajności  
3. **Odporność** - automatyczne zarządzanie błędami procesów
4. **Skalowalność** - elastyczna konfiguracja liczby workerów
5. **Rozszerzalność** - przygotowana struktura dla funkcji boxów

System zapewnia solidną podstawę do rozbudowy o funkcjonalności wykrywania boxów przy zachowaniu istniejącej wydajności i niezawodności dla QR kodów.