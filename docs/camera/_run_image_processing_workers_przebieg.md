# Przebieg metody `_run_image_processing_workers`

## Opracowanie

Metoda `_run_image_processing_workers` w klasie `GeneralCameraWorker` zarządza równoległym przetwarzaniem obrazów w wielu procesach z wykorzystaniem `ProcessPoolExecutor`. Głównym celem jest wykonanie detekcji QR kodów na podstawie przekazanych ramek obrazu oraz scalenie wyników z różnych konfiguracji detektorów.

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

#### 6. Konwersja na pozycje QR kodów

**Iteracja przez wyniki:**
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

**W przypadku powodzenia:**
- Typ: `dict`
- Struktura: `{position_id: pose_dict}`
- Przykład:
```python
{
    1: {'x': 100.5, 'y': 200.3, 'z': 0.0, 'rx': 0.1, 'ry': 0.2, 'rz': 1.57},
    2: {'x': 150.2, 'y': 250.8, 'z': 0.0, 'rx': 0.0, 'ry': 0.1, 'rz': 1.60},
    3: {'x': 80.1, 'y': 180.5, 'z': 0.0, 'rx': -0.1, 'ry': 0.0, 'rz': 1.55}
    4: None,  # nie wykryto QR kodu na tej pozycji
}
```

**W przypadku błędu:**
- Typ: `None`
- Przyczyny: problemy z executor-em, timeout, błędy procesów

**W przypadku braku konfiguracji:**
- Typ: `None`
- Przyczyna: `self.postprocess_configuration` jest None

### Kluczowe zależności

**Zewnętrzne moduły:**
- `avena_commons.vision.merge.merge_qr_detections_with_confidence`
- `avena_commons.vision.sorter.sort_qr_by_center_position`
- `avena_commons.vision.vision.calculate_pose_pnp`
- `avena_commons.vision.camera.create_camera_matrix`

**Wewnętrzne właściwości:**
- `self.executor`: ProcessPoolExecutor
- `self.image_processing_workers`: lista konfiguracji workerów
- `self.camera_configuration`: konfiguracja kamery
- `self.postprocess_configuration`: konfiguracja postprocessingu
- `self._message_logger`: logger komunikatów

## Podsumowanie

Metoda `_run_image_processing_workers` implementuje zaawansowany system równoległego przetwarzania obrazów z wykrywaniem QR kodów. Wykorzystuje wieloprocesowość do równoczesnego uruchamiania różnych konfiguracji detektorów, automatycznie zarządza uszkodzonymi procesami oraz scala wyniki w spójną strukturę pozycji przestrzennych QR kodów. Zwraca słownik z pozycjami 3D wykrytych QR kodów lub None w przypadku błędów.