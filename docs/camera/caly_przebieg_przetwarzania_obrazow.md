# Przebieg przetwarzania obrazów w systemie kamer

## Opracowanie

System składa się z trzech komponentów: `GeneralCameraConnector` (synchroniczny interfejs), `GeneralCameraWorker` (asynchroniczny worker w procesie) i `ProcessPoolExecutor` (równoległe przetwarzanie obrazów).

## Przebieg główny

### 1. Inicjalizacja
```python
connector = GeneralCameraConnector()
```
- Tworzenie connectora z thread lock
- Automatyczne uruchomienie procesu workera przy pierwszym użyciu

### 2. Konfiguracja kamery
```python
connector.init(camera_configuration)
```
**Dane:** parametry kalibracji (fx,fy,cx,cy), rozdzielczość, FPS
**Worker:** `CameraState.INITIALIZING → INITIALIZED`, wywołuje `await self.init()`

### 3. Konfiguracja postprocessingu  
```python
connector.set_postprocess_configuration(detector="detect_qr_codes", configuration={...})
```
**Worker:** import detektora, setup ProcessPoolExecutor, tworzenie listy workerów

### 4. Uruchomienie kamery
```python
connector.start()
```
**Worker:** `CameraState.STARTING → STARTED`, wywołuje `await self.start()`

### 5. Pętla przetwarzania
**Worker automatycznie:**
- Pobiera ramki: `frames = await self.grab_frames_from_camera()`
- Zapisuje: `self.last_frame = frames`
- Jeśli skonfigurowane postprocessing: `await self._run_image_processing_workers(frames)`

### 6. Przetwarzanie obrazów (ProcessPoolExecutor)

#### Submit zadań:
```python
for worker in self.image_processing_workers:
    future = executor.submit(worker["detector"], frame=frames, camera_config=config, config=worker["config"])
```

#### Zbieranie wyników:
- Timeout: 30s dla wszystkich, 10s na pojedynczy wynik
- Każdy detektor zwraca: `(Detection_list, debug_dict)`
- Early termination przy 4 wykrytych QR kodach

#### Przetwarzanie detekcji:
1. `sorter.sort_qr_by_center_position(expected_count=4, detections)`
2. `merge.merge_qr_detections_with_confidence(sorted_detections, results)`
3. `calculate_pose_pnp(corners, qr_size, camera_matrix)` → pozycje 3D

### 7. Zewnętrzne wywołanie postprocessingu
```python
results = connector.run_postprocess_workers(frames)
```
**Zwraca:** `{position_id: {"x":float, "y":float, "z":float, "rx":float, "ry":float, "rz":float}}`

### 8. Zatrzymanie
```python
connector.stop()
```
**Worker:** `CameraState.STOPPING → STOPPED`, wywołuje `await self.stop()`

## Kluczowe struktury danych

### Camera Configuration
```python
{
    "camera_params": {"fx": float, "fy": float, "cx": float, "cy": float, "k1": float, "k2": float, "p1": float, "p2": float},
    "resolution": {"width": int, "height": int},
    "fps": int
}
```

### Postprocess Configuration
```python
{
    "config_name": {
        "qr_size": 0.05,  # rozmiar QR w metrach
        "detection_params": {"adaptiveThresholdConstant": int, "adaptiveThresholdBlockSize": int, "minContourAreaRate": float}
    }
}
```

### Frames Structure
```python
{
    "color": numpy.ndarray,   # obraz RGB (H, W, 3)
    "depth": numpy.ndarray,   # mapa głębi (H, W)
    "timestamp": float,       # czas pobrania
    "frame_id": int          # identyfikator ramki
}
```

### Detection Object
```python
{
    "corners": numpy.ndarray,  # 4 narożniki (4, 2)
    "center": (x, y),         # środek QR kodu
    "confidence": float,      # pewność detekcji
    "data": "QR_CONTENT",     # zawartość QR kodu
    "id": "position_1"        # identyfikator pozycji
}
```

### Result Structure
```python
{
    1: {"x": float, "y": float, "z": float, "rx": float, "ry": float, "rz": float},
    2: {"x": float, "y": float, "z": float, "rx": float, "ry": float, "rz": float},
    3: {"x": float, "y": float, "z": float, "rx": float, "ry": float, "rz": float}
    4: None,  # nie wykryto
}
```

## Zarządzanie błędami

### Stany kamery
```
IDLE → INITIALIZING → INITIALIZED → STARTING → STARTED → STOPPING → STOPPED
                                                 ↓
                                              ERROR
```

### Obsługa błędów ProcessPoolExecutor
- `BrokenProcessPool` → odtworzenie executor-a
- `TimeoutError` → kontynuacja z następnym zadaniem  
- `ProcessLookupError` → logowanie i kontynuacja
- Early termination przy 4 wykrytych QR kodach

## Metody do implementacji w klasach dziedziczących

- `async def init(camera_settings: dict) → bool` - inicjalizacja sprzętu
- `async def start() → bool` - uruchomienie pipeline kamery
- `async def stop() → bool` - zatrzymanie pipeline
- `async def grab_frames_from_camera() → dict|None` - pobieranie ramek

## Podsumowanie

System trójwarstwowy (Connector-Worker-Executor) zapewniający równoległe przetwarzanie obrazów z automatycznym zarządzaniem błędami. Kluczowe cechy: separacja procesów, konfigurowalność detektorów, odporność na awarie procesów, early termination przy pełnym zestawie detekcji QR kodów.