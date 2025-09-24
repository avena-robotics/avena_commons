# System Kamery Avena Commons - Proces Działania

## Przegląd Systemu

System kamery to zaawansowany moduł event-driven do obsługi kamer przemysłowych w architekturze Avena Commons. Zapewnia asynchroniczne przetwarzanie obrazu z wykorzystaniem wieloprocesowego pipeline'u detekcji oraz synchronizację ramek koloru i głębi.

**Główne komponenty**:
- **Camera** (EventListener) - główna logika zarządzania stanem i eventami
- **GeneralCameraWorker/Connector** - uniwersalny system worker-connector dla kamer
- **OrbecGemini335Le** - specjalizowany sterownik kamery Orbbec

**Repozytorium**: [avena_commons](https://github.com/avena-robotics/avena_commons)

## Struktura Danych

### Główne Klasy i Stany

#### CameraState (Stany Kamery)
```python
class CameraState(Enum):
    IDLE = 0           # bezczynność
    INITIALIZING = 1   # inicjalizacja kamery  
    INITIALIZED = 2    # kamera zainicjalizowana
    STARTING = 3       # uruchamianie pipeline'u
    STARTED = 4        # pipeline uruchomiony
    RUNNING = 9        # przetwarzanie obrazu w toku
    STOPPING = 6       # zatrzymywanie
    STOPPED = 7        # zatrzymany
    ERROR = 255        # błąd
```

#### Camera - Dane Instancji
```python
class Camera(EventListener):
    def __init__(self, name, address, port, message_logger=None):
        # Konfiguracja kamery
        self.__camera_config = self._configuration.get("camera_configuration", {})
        self.__pipelines_config = self._configuration.get("pipelines", {})
        
        # Synchronizacja ramek
        self.latest_color_frame = None
        self.latest_depth_frame = None
        self.last_color_timestamp = 0
        self.last_depth_timestamp = 0
        self.frame_sync_timeout = 500  # ms
        
        # Instancja sterownika kamery
        match self.__camera_config.get("model", None):
            case "orbec_gemini_335le":
                self.camera = OrbecGemini335Le(self.camera_address, self._message_logger)
```

#### GeneralCameraWorker - Stan Workera
```python
class GeneralCameraWorker(Worker):
    def __init__(self, message_logger=None):
        self.state = CameraState.IDLE
        self.last_frame = None
        self.postprocess_configuration = None
        self.detector = None
        self.detector_name = None  # 'qr_detector' lub 'box_detector'
        self.executor = None  # ProcessPoolExecutor
        self.last_result = None
        self.image_processing_workers = []
```

### Konfiguracja Pipeline'u

#### Konfiguracja Kamery
```json
{
  "camera_configuration": {
    "camera_ip": "192.168.1.10",
    "model": "orbec_gemini_335le",
    "color": {
      "width": 1280,
      "height": 800,
      "fps": 30,
      "format": "BGR",
      "exposure": 500,
      "gain": 10,
      "white_balance": 4000
    },
    "depth": {
      "exposure": 500,
      "gain": 10,
      "laser_power": 5
    },
    "align": "d2c",
    "filters": {
      "spatial": true,
      "temporal": true
    }
  }
}
```

#### Konfiguracja Detektorów
```json
{
  "pipelines": {
    "qr_detector": {
      "configuration": {},
      "postprocessors": {
        "a": {"qr_size": 0.05},
        "b": {"qr_size": 0.05},
        "c": {"qr_size": 0.05}
      }
    },
    "box_detector": {
      "configuration": {},
      "postprocessors": {
        "config_1": {"threshold": 0.5},
        "config_2": {"threshold": 0.7}
      }
    }
  }
}
```

## Architektura i Przepływ Danych

### Hierarchia Klas
```
EventListener
├── Camera (główna logika obsługi eventów)

Worker  
├── GeneralCameraWorker (bazowa implementacja workera kamery)
│   └── OrbecGemini335LeWorker (implementacja dla kamery Orbbec)

Connector
└── GeneralCameraConnector (synchroniczny interfejs do workera)
    └── OrbecGemini335Le (konektor dla kamery Orbbec)
```

### Cykl Życia Systemu

#### 1. Inicjalizacja
```python
# 1. Camera EventListener
async def on_initializing(self):
    self.camera.init(self.__camera_config)

# 2. Worker w procesie potomnym  
async def init_camera(self, camera_settings):
    self.state = CameraState.INITIALIZING
    await self.init(camera_settings)  # Implementacja specyficzna dla kamery
    self.state = CameraState.INITIALIZED
```

#### 2. Obsługa Eventów
```python
async def _analyze_event(self, event):
    match event.event_type:
        case "take_photo_box":
            # Konfiguracja box_detector
            self.camera.set_postprocess_configuration(
                detector="box_detector",
                configuration=self.__pipelines_config["box_detector"]
            )
        case "take_photo_qr":
            # Konfiguracja qr_detector
            self.camera.set_postprocess_configuration(
                detector="qr_detector", 
                configuration=self.__pipelines_config["qr_detector"]
            )
    
    # Start kamery
    self.camera.start()
```

#### 3. Pętla Przetwarzania
```python
async def _check_local_data(self):
    camera_state = self.camera.get_state()
    
    match camera_state:
        case CameraState.STARTED:
            # Pobierz ramki
            last_frame = self.camera.get_last_frame()
            if last_frame:
                self.latest_color_frame = last_frame["color"]
                self.latest_depth_frame = last_frame["depth"]
                
                # Uruchom postprocess
                confirmed = self.camera.run_postprocess_workers(last_frame)
                
        case CameraState.RUNNING:
            # Pobierz wyniki
            result = self.camera.get_last_result()
            if result:
                self.camera.stop()
                event = self._find_and_remove_processing_event(self._current_event)
                event.result = Result(result="success")
                event.data = result
```

### Komunikacja Worker ↔ Connector

#### Synchroniczna Komunikacja przez Pipe
```python
class GeneralCameraConnector(Connector):
    def init(self, configuration):
        with self.__lock:
            return super()._send_thru_pipe(
                self._pipe_out, ["CAMERA_INIT", configuration]
            )
    
    def start(self):
        with self.__lock:
            return super()._send_thru_pipe(
                self._pipe_out, ["CAMERA_START_GRABBING"]
            )
    
    def set_postprocess_configuration(self, detector, configuration):
        with self.__lock:
            return super()._send_thru_pipe(
                self._pipe_out, ["SET_POSTPROCESS_CONFIGURATION", detector, configuration]
            )
```

#### Asynchroniczna Pętla Workera
```python
async def _run(self, pipe_in):
    while True:
        if pipe_in.poll(0.0005):
            data = pipe_in.recv()
            match data[0]:
                case "CAMERA_INIT":
                    await self.init_camera(data[1])
                    pipe_in.send(True)
                    
                case "SET_POSTPROCESS_CONFIGURATION":
                    detector_name = data[1]
                    self.detector_name = detector_name
                    
                    # Dynamiczny import detektora
                    detector_module = importlib.import_module("avena_commons.vision.detector")
                    self.detector = getattr(detector_module, detector_name)
                    
                    self.postprocess_configuration = data[2]["postprocessors"]
                    await self._setup_image_processing_workers()
                    pipe_in.send(True)
        
        # Cykliczne pobieranie ramek
        if self.state == CameraState.STARTED:
            frames = await self.grab_frames_from_camera()
            self.last_frame = frames
```

## Przetwarzanie Obrazu

### System Wieloprocesowy

#### Konfiguracja ProcessPoolExecutor
```python
async def _setup_image_processing_workers(self):
    max_workers = len(self.postprocess_configuration)
    self.executor = ProcessPoolExecutor(max_workers=max_workers)
    
    self.image_processing_workers = []
    for config_key, config_value in self.postprocess_configuration.items():
        worker_info = {
            "detector": self.detector,
            "config": config_value,
        }
        self.image_processing_workers.append(worker_info)
```

#### Wysyłanie Zadań do Workerów
```python
async def _run_image_processing_workers(self, frame):
    futures = {}
    
    for i, worker in enumerate(self.image_processing_workers):
        future = self.executor.submit(
            worker["detector"],
            frame=frame,
            camera_config=self.camera_configuration,
            config=worker["config"]
        )
        futures[future] = i
    
    # Przetwarzanie wyników
    if self.detector_name == "qr_detector":
        self.last_result = await self._process_qr_detection_results(futures)
    elif self.detector_name == "box_detector":
        self.last_result = await self._process_box_detection_results(futures)
```

### Detekcja QR Kodów

```python
async def _process_qr_detection_results(self, futures):
    results = {}
    
    for future in as_completed(futures, timeout=30.0):
        result = future.result(timeout=10.0)
        if result:
            # Sortowanie detekcji według pozycji środkowej
            sorted_detections = sorter.sort_qr_by_center_position(
                expected_count=4, detections=result[0]
            )
            
            # Łączenie wyników z uwzględnieniem confidence
            results = merge.merge_qr_detections_with_confidence(
                sorted_detections, results
            )
            
            # Sprawdź czy mamy komplet 4 QR kodów
            actual_detections = sum(1 for v in results.values() if v is not None)
            if actual_detections == 4:
                self._cancel_pending_futures(futures)
                break
    
    # Konwersja na pozycje 6DOF (x,y,z,rx,ry,rz)
    qr_positions = {}
    for position_id, detection in results.items():
        if detection:
            qr_positions[position_id] = calculate_pose_pnp(
                corners=detection.corners,
                a=self.postprocess_configuration["a"]["qr_size"] * 1000,
                b=self.postprocess_configuration["a"]["qr_size"] * 1000,
                z=detection.z,
                camera_matrix=create_camera_matrix(
                    self.camera_configuration["camera_params"]
                )
            )
        else:
            qr_positions[position_id] = None
            
    return qr_positions
```

### Detekcja Pudełek

```python
async def _process_box_detection_results(self, futures):
    for future in as_completed(futures, timeout=30.0):
        result = future.result(timeout=10.0)
        if result:
            center, sorted_corners, angle, z, detect_image, debug_data = result
            
            if center is not None:
                # Konwersja na pozycję 6DOF
                box_result = calculate_pose_pnp(
                    corners=sorted_corners,
                    a=400,  # szerokość pudełka [mm]
                    b=300,  # wysokość pudełka [mm] 
                    z=z,
                    camera_matrix=create_camera_matrix(
                        self.camera_configuration["camera_params"]
                    )
                )
                
                # Box znaleziony - zatrzymaj dalsze przetwarzanie
                self._cancel_pending_futures(futures)
                return box_result
                
    return None  # Brak detekcji
```

## Implementacja Orbbec Gemini 335LE

### Inicjalizacja Kamery

```python
async def init(self, camera_settings):
    # Tworzenie kontekstu i urządzenia sieciowego
    ctx = Context()
    dev = ctx.create_net_device(self.__camera_ip, 8090)
    
    # Konfiguracja właściwości kamery
    color_settings = camera_settings.get("color", {})
    depth_settings = camera_settings.get("depth", {})
    
    self.set_int_property(dev, OBPropertyID.OB_PROP_COLOR_EXPOSURE_INT, 
                         color_settings.get("exposure", 500))
    self.set_int_property(dev, OBPropertyID.OB_PROP_COLOR_GAIN_INT,
                         color_settings.get("gain", 10))
    self.set_int_property(dev, OBPropertyID.OB_PROP_DEPTH_EXPOSURE_INT,
                         depth_settings.get("exposure", 500))
    
    # Tworzenie pipeline'u i konfiguracji
    self.camera_pipeline = Pipeline(dev)
    self.camera_config = Config()
    
    # Konfiguracja profili strumieni
    color_profile = color_profile_list.get_video_stream_profile(
        width, height, color_format, fps
    )
    
    # Obsługa wyrównania strumieni (align)
    match camera_settings.get("align", None):
        case "d2c":  # Depth to Color alignment
            hw_d2c_profile_list = self.camera_pipeline.get_d2c_depth_profile_list(
                color_profile, OBAlignMode.HW_MODE
            )
            if hw_d2c_profile_list:
                depth_profile = hw_d2c_profile_list[0]
            else:
                # Fallback do programowego wyrównania
                self.align_filter = AlignFilter(align_to_stream=OBStreamType.COLOR_STREAM)
    
    # Włączenie strumieni
    self.camera_config.enable_stream(depth_profile)
    self.camera_config.enable_stream(color_profile)
    
    # Konfiguracja filtrów
    filter_settings = camera_settings.get("filters", {})
    if filter_settings.get("spatial", False):
        self.spatial_filter = SpatialAdvancedFilter()
    if filter_settings.get("temporal", False):
        self.temporal_filter = TemporalFilter()
```

### Pobieranie i Przetwarzanie Ramek

```python
async def grab_frames_from_camera(self):
    # Pobierz FrameSet z pipeline'u
    frames = self.camera_pipeline.wait_for_frames(3)
    if frames is None:
        return None
    
    # Ekstrakcja ramek koloru i głębi
    frame_color = frames.get_color_frame()
    frame_depth = frames.get_depth_frame()
    
    if frame_color is None or frame_depth is None:
        return None
    
    self.frame_number += 1
    
    # Aplikacja filtrów
    if self.align_filter:
        aligned_frames = self.align_filter.process(frames)
        aligned_frames = aligned_frames.as_frame_set()
        frame_depth = aligned_frames.get_depth_frame()
    
    if self.spatial_filter and frame_depth:
        frame_depth = self.spatial_filter.process(frame_depth)
        
    if self.temporal_filter and frame_depth:
        frame_depth = self.temporal_filter.process(frame_depth)
    
    # Konwersja do numpy arrays
    # Obsługa MJPG dla ramek kolorowych
    if frame_color.get_format() == OBFormat.MJPG:
        color_data = frame_color.get_data()
        color_image = cv2.imdecode(
            np.frombuffer(color_data, np.uint8), cv2.IMREAD_COLOR
        )
    else:
        color_data = frame_color.get_data()
        color_image = np.frombuffer(color_data, dtype=np.uint8).reshape(
            (frame_color.get_height(), frame_color.get_width(), 3)
        )
        
        if frame_color.get_format() == OBFormat.RGB:
            color_image = cv2.cvtColor(color_image, cv2.COLOR_RGB2BGR)
    
    # Ramka głębi
    depth_data = frame_depth.get_data()
    depth_image = np.frombuffer(depth_data, dtype=np.uint16).reshape(
        (frame_depth.get_height(), frame_depth.get_width())
    )
    
    return {
        "timestamp": frame_color.get_timestamp(),
        "number": self.frame_number,
        "color": color_image,
        "depth": depth_image
    }
```

## Obsługa Błędów i Odzyskiwanie

### Strategie Obsługi Błędów

#### 1. Automatyczne Odtwarzanie ProcessPool
```python
async def _recreate_executor_if_broken(self):
    try:
        # Zamknij uszkodzony executor
        if self.executor:
            self.executor.shutdown(wait=False)
            self.executor = None
        
        # Odtwórz setup
        success = await self._setup_image_processing_workers()
        return success
        
    except Exception as e:
        error(f"Błąd podczas odtwarzania executor-a: {e}", self._message_logger)
        return False

def _is_executor_broken(self):
    if not self.executor:
        return True
    if hasattr(self.executor, "_broken") and self.executor._broken:
        return True
    return False
```

#### 2. Obsługa Timeout'ów i Anulowanie Zadań
```python
try:
    for future in as_completed(futures, timeout=30.0):
        result = future.result(timeout=10.0)
        # Przetwarzanie wyniku
        
except TimeoutError:
    error("Timeout podczas oczekiwania na zakończenie zadań", self._message_logger)
    self._cancel_pending_futures(futures)

def _cancel_pending_futures(self, futures):
    for future in futures.keys():
        if not future.done():
            future.cancel()
```

#### 3. Obsługa Błędów Kamery
```python
async def _check_local_data(self):
    camera_state = self.camera.get_state()
    
    match camera_state:
        case CameraState.ERROR:
            self.set_state(EventListenerState.ON_ERROR)
            
        case CameraState.RUNNING:
            result = self.camera.get_last_result()
            if result is None:
                # Błąd przetwarzania
                event = self._find_and_remove_processing_event(self._current_event)
                event.result = Result(result="error", error_message="Postprocess error")
                self.set_state(EventListenerState.ON_ERROR)
```

### Logowanie i Monitoring

#### Strukturalne Logowanie
```python
# Logowanie z pomiarami czasu
with Catchtime() as t:
    last_frame = self.camera.get_last_frame()
global_timing_stats.add_measurement("camera_get_last_frame", t.ms)
debug(f"Get last frame time: {t.ms:.5f}ms", self._message_logger)

# Logowanie błędów z kontekstem
error(f"Błąd podczas uruchamiania workerów: {e}", self._message_logger)
error(f"Traceback: {traceback.format_exc()}", self._message_logger)
```

#### Statystyki Wydajności
```python
# Globalne pomiary czasu
global_timing_stats.add_measurement("camera_analyze_event_setup", t.ms)
global_timing_stats.add_measurement("camera_start", t2.ms) 
global_timing_stats.add_measurement("camera_run_postprocess_workers", ct.ms)
```

## Konfiguracja i Zmienne Środowiskowe

### Wymagane Zmienne Środowiskowe
```bash
CAMERA_LISTENER_PORT=9000  # Port Event Listenera kamery
```

### Przykładowa Konfiguracja JSON
```json
{
  "camera_configuration": {
    "camera_ip": "192.168.1.10",
    "model": "orbec_gemini_335le",
    "color": {
      "width": 1280,
      "height": 800,
      "fps": 30,
      "format": "BGR",
      "exposure": 500,
      "gain": 10,
      "white_balance": 4000
    },
    "depth": {
      "exposure": 500, 
      "gain": 10,
      "laser_power": 5
    },
    "disparity": {
      "range_mode": "CLOSE",
      "search_offset": 50
    },
    "align": "d2c",
    "filters": {
      "spatial": true,
      "temporal": true
    },
    "camera_params": {
      "fx": 615.123,
      "fy": 615.456, 
      "cx": 640.0,
      "cy": 400.0,
      "k1": -0.12,
      "k2": 0.05
    }
  },
  "pipelines": {
    "qr_detector": {
      "configuration": {},
      "postprocessors": {
        "a": {"qr_size": 0.05},
        "b": {"qr_size": 0.05}
      }
    },
    "box_detector": {
      "configuration": {},  
      "postprocessors": {
        "config_1": {"threshold": 0.5}
      }
    }
  }
}
```

## Przykłady Użycia

### Przykład 1: Uruchomienie Kamery
```python
from avena_commons.camera import Camera
from avena_commons.util.logger import MessageLogger

# Utworzenie instancji
camera = Camera(
    name="camera_1",
    address="127.0.0.1", 
    port="9000",
    message_logger=MessageLogger()
)

# Uruchomienie FSM
camera.set_state(EventListenerState.INITIALIZING)
```

### Przykład 2: Wysłanie Eventu Zdjęcia
```python
from avena_commons.event_listener import Event

# Event zdjęcia QR kodów
event = Event(
    event_type="take_photo_qr",
    source="munchies_algo",
    source_port=8001,
    destination_port=9000,
    is_processing=True
)

# Wysłanie przez HTTP POST
import requests
response = requests.post(
    "http://127.0.0.1:9000/event", 
    json=event.to_dict()
)
```

### Przykład 3: Obsługa Wyniku
```python
# W pętli _check_local_data() klasy Camera
case CameraState.RUNNING:
    result = self.camera.get_last_result()
    if result:
        if isinstance(result, dict) and all(v is not None for v in result.values()):
            # Sukces - QR kody znalezione
            event.result = Result(result="success")
            event.data = result  # {1: (x,y,z,rx,ry,rz), 2: ..., 3: ..., 4: ...}
        else:
            # Brak detekcji
            event.result = Result(result="failure") 
            event.data = {}
```

## Podsumowanie

System kamery Avena Commons zapewnia kompleksową obsługę kamer przemysłowych w architekturze event-driven:

### Kluczowe Funkcjonalności
- **Event-driven architecture** z FSM dla zarządzania stanami życiowymi
- **Wieloprocesowe przetwarzanie obrazu** przez ProcessPoolExecutor z automatycznym odtwarzaniem
- **Wsparcie dla różnych typów kamer** przez wzorzec Worker-Connector
- **Zaawansowana synchronizacja ramek** koloru i głębi z filtrami sprzętowymi/programowymi
- **Detekcja QR kodów i pudełek** z konwersją do pozycji 6DOF (x,y,z,rx,ry,rz)
- **Automatyczne odzyskiwanie po błędach** z monitoringiem ProcessPool i timeout'ami
- **Kompletne logowanie i pomiary wydajności** z globalną statystyką czasów

### Architektura Systemu
```
Event → Camera._analyze_event() → Konfiguracja detektora → Worker przez pipe
     → Cykliczne pobieranie ramek → Worker.grab_frames_from_camera()  
     → Przetwarzanie w ProcessPool → Zwrot wyników przez pipe
     → Event completion z danymi pozycji
```

### Bezpieczeństwo i Niezawodność
- Automatyczne wykrywanie uszkodzonych pul procesów i ich odtwarzanie
- Timeout'y na wszystkie operacje asynchroniczne z graceful degradation
- Thread-safe komunikacja między procesami z blokowaniem mutexami
- Obsługa błędów sprzętowych kamery z przejściem do stanów awaryjnych
- Strukturalne logowanie błędów z pełnym kontekstem dla diagnostyki

System zapewnia skalowalność, odporność na błędy oraz łatwość rozszerzania o nowe typy kamer i algorytmy detekcji, przy zachowaniu wysokiej wydajności przetwarzania obrazu w czasie rzeczywistym.
