import asyncio
import threading
import traceback
from enum import Enum
from typing import Optional
from concurrent.futures import ProcessPoolExecutor, as_completed  # ← DODAJ TO!

from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import MessageLogger, debug, error, info
from avena_commons.util.worker import Connector, Worker

class CameraState(Enum):
    IDLE = 0  # idle
    INITIALIZING = 1  # init camera
    INITIALIZED = 2  # init camera
    STARTING = 3  # start camera pipeline
    STARTED = 4  # start camera pipeline
    STOPPING = 6  # stop camera pipeline
    STOPPED = 7  # stop camera pipeline
    SHUTDOWN = 8  # stop camera pipeline
    ERROR = 255  # error


class GeneralCameraWorker(Worker):
    def __init__(self, message_logger: Optional[MessageLogger] = None):
        self._message_logger = None
        self.device_name = f"GeneralCamera"
        super().__init__(message_logger=None)
        self.state = CameraState.IDLE

        # self.align_filter = None
        # self.spatial_filter = None
        # self.temporal_filter = None
        self.last_frames = None
        self.postprocess_configuration = None
        self.executor = None
        self.image_processing_workers = []


    @property
    def state(self) -> CameraState:
        return self.__state

    @state.setter
    def state(self, value: CameraState) -> None:
        debug(
            f"{self.device_name} - State changed to {value.name}", self._message_logger
        )
        self.__state = value

    # MARK: METODY DO NADPISANIA
    async def init(self, camera_settings: dict):
        """Initialize camera connection and resources"""
        return True

    async def start(self):
        """Initialize camera connection and resources"""
        return True

    async def stop(self):
        """Initialize camera connection and resources"""
        return True

    async def grab_frames_from_camera(self):
        """Initialize camera connection and resources"""
        return None

    # MARK: WYWOŁYWANE PRZEZ CONNECTOR
    async def init_camera(self, camera_settings: dict):
        """Initialize camera connection and resources"""
        try:
            self.state = CameraState.INITIALIZING
            await self.init(camera_settings)
            self.state = CameraState.INITIALIZED
            return True
        except Exception as e:
            self.state = CameraState.ERROR
            error(f"{self.device_name} - Starting failed: {e}", self._message_logger)
            return False

    async def start_camera(self):
        """Start camera frame grabbing"""
        try:
            self.state = CameraState.STARTING
            await self.start()
            self.state = CameraState.STARTED
            return True
        except Exception as e:
            self.state = CameraState.ERROR
            error(f"{self.device_name} - Starting failed: {e}", self._message_logger)
            return False

    async def stop_camera(self):
        """Stop camera frame grabbing"""
        try:
            self.state = CameraState.STOPPING
            await self.stop()
            self.state = CameraState.STOPPED
            return True
        except Exception as e:
            self.state = CameraState.ERROR
            error(f"{self.device_name} - Stopping failed: {e}", self._message_logger)
            return False

    async def _run_image_processing_workers(self, frames):
        """Uruchom workery przez ProcessPoolExecutor."""
        if not self.executor:
            return None
        
        try:
            # Submit funkcji do procesów (NIE tworzenie nowych workerów!)
            futures = {}
            for i, config in enumerate(self.postprocess_configuration):
                # ✅ POPRAWNE - submit funkcji, nie tworzenie workerów
                future = self.executor.submit(
                    self._process_single_config,  # Funkcja do wykonania
                    frames,                       # Dane
                    config,                       # Konfiguracja
                    i                             # ID
                )
                futures[future] = i
            
            # Zbierz wyniki
            results = []
            for future in as_completed(futures):
                config_id = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    error(f"Błąd w config_{config_id}: {e}", self._message_logger)
            
            return results
            
        except Exception as e:
            error(f"Błąd podczas uruchamiania workerów: {e}", self._message_logger)
            return None
            
    async def _setup_image_processing_workers(self, configs: list):
        """Utwórz workery raz przy konfiguracji."""
        try:
            # Zamknij poprzedni executor jeśli istnieje
            if self.executor:
                self.executor.shutdown(wait=True)
            
            # Utwórz nowy executor
            self.executor = ProcessPoolExecutor(max_workers=len(configs))
            self.postprocess_configuration = configs
            
            # Przygotuj workery (ale nie uruchamiaj jeszcze!)
            self.image_processing_workers = []
            for i, config in enumerate(configs):
                worker_info = {
                    "worker_id": i,
                    "config": config,
                    "config_name": config["mode"],
                    "status": "READY"  # READY, RUNNING, COMPLETED, ERROR
                }
                self.image_processing_workers.append(worker_info)
            
            debug(f"Utworzono {len(self.image_processing_workers)} workerów do przetwarzania obrazów", 
                  self._message_logger)
            
            return True
            
        except Exception as e:
            error(f"Błąd podczas tworzenia workerów: {e}", self._message_logger)
            return False

    async def _run(self, pipe_in):
        from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger

        # Utwórz lokalny logger dla tego procesu
        self._message_logger = MessageLogger(
            filename=f"temp/camera_worker.log",
            debug=True,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=10,
            colors=False,
        )

        debug(
            f"{self.device_name} - Worker started with local logger",
            self._message_logger,
        )

        try:
            while True:
                if pipe_in.poll(0.0005):
                    data = pipe_in.recv()
                    response = None
                    match data[0]:
                        case "CAMERA_INIT":
                            try:
                                debug(
                                    f"{self.device_name} - Received CAMERA_INIT: {data[1]}",
                                    self._message_logger,
                                )
                                # Tu będzie logika inicjalizacji z konfiguracją
                                await self.init_camera(data[1])
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error in CAMERA_INIT: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(False)

                        case "CAMERA_START_GRABBING":
                            try:
                                debug(
                                    f"{self.device_name} - Starting frame grabbing",
                                    self._message_logger,
                                )
                                # Tu będzie logika startowania grabowania
                                await self.start_camera()
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error starting grabbing: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(False)

                        case "CAMERA_STOP_GRABBING":
                            try:
                                debug(
                                    f"{self.device_name} - Stopping OrbecGemini335LeWorker subprocess",
                                    message_logger=self._message_logger,
                                )
                                await self.stop_camera()
                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error stopping grabbing: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(False)

                        case "GET_STATE":
                            try:
                                state = self.state
                                # debug(
                                #     f"{self.device_name} - Getting state: {state.name}",
                                #     message_logger=self._message_logger,
                                # )
                                pipe_in.send(state)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error getting state: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(None)
                        
                        case "GET_LAST_FRAMES":
                            try:
                                pipe_in.send(self.last_frames)
                            except Exception as e:
                                error(f"{self.device_name} - Error getting last frames: {e}", message_logger=self._message_logger)
                                pipe_in.send(None)

                        case "SET_POSTPROCESS_CONFIGURATION":
                            try:
                                debug(
                                    f"{self.device_name} - Received SET_POSTPROCESS_CONFIGURATION: {data[1]}",
                                    self._message_logger,
                                )
                                self.postprocess_configuration = data[1]
                                await self._setup_image_processing_workers(self.postprocess_configuration)

                                pipe_in.send(True)
                            except Exception as e:
                                error(f"{self.device_name} - Error setting postprocess configuration: {e}", message_logger=self._message_logger)
                                pipe_in.send(False)

                        case _:
                            error(
                                f"{self.device_name} - Unknown command: {data[0]}",
                                message_logger=self._message_logger,
                            )

                if self.state == CameraState.STARTED:
                    with Catchtime() as ct:
                        frames = await self.grab_frames_from_camera()
                        if frames is None:
                            continue
                        self.last_frames = frames
                    # color_image = frames["color"]
                    # depth_image = frames["depth"]
                    debug(
                        f"{self.device_name} - Pobrano ramki Koloru i Głębi w {ct.t * 1_000:.2f}ms",
                        self._message_logger,
                    )
                    # przetwarzanie wizyjne
                    if self.postprocess_configuration:
                        print(f"{self.device_name} - Postprocess configuration: {len(self.postprocess_configuration)}")

        except asyncio.CancelledError:
            info(
                f"{self.device_name} - Task was cancelled",
                message_logger=self._message_logger,
            )
        except Exception as e:
            error(
                f"{self.device_name} - Error in Worker: {e}",
                message_logger=self._message_logger,
            )
            error(
                f"Traceback:\n{traceback.format_exc()}",
                message_logger=self._message_logger,
            )
        finally:
            info(
                f"{self.device_name} - Worker has shut down",
                message_logger=self._message_logger,
            )


class GeneralCameraConnector(Connector):
    def __init__(self, message_logger: Optional[MessageLogger] = None):
        self.__lock = threading.Lock()
        self._local_message_logger = message_logger

    def _run(self, pipe_in):
        self.__lock = threading.Lock()
        worker = GeneralCameraWorker(message_logger=None)
        asyncio.run(worker._run(pipe_in))

    def init(self, configuration: dict = {}):
        """
        Initialize camera with configuration.
        Przekazuj tylko serializowalne dane przez pipe.
        """
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["CAMERA_INIT", configuration]
            )
            return value

    def start(self):
        """Start camera frame grabbing"""
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["CAMERA_START_GRABBING"])
            return value

    def stop(self):
        """Stop camera frame grabbing"""
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["CAMERA_STOP_GRABBING"])
            return value

    def get_state(self):
        """Get camera state"""
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["GET_STATE"])
            return value

    def get_last_frames(self):
        """Get last frames"""
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["GET_LAST_FRAMES"])
            return value

    def set_postprocess_configuration(self, *, configuration: list = None):
        """Set postprocess configuration"""
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["SET_POSTPROCESS_CONFIGURATION", configuration])
            return value
