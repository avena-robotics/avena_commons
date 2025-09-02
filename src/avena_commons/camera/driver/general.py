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
    """Stany pracy ogólnego sterownika kamery.

    Enum odzwierciedla cykl życia urządzenia od bezczynności po błąd.

    Przykład:
        >>> state = CameraState.IDLE
        >>> state.name
        'IDLE'

    See Also:
        - `GeneralCameraWorker`: klasa korzystająca z tych stanów.
    """
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
    """Asynchroniczny worker obsługujący cykl życia kamery i postprocess.

    Klasa zarządza inicjalizacją, startem, zatrzymaniem oraz pętlą
    pobierania ramek. Może uruchamiać przetwarzanie obrazu w wielu
    procesach poprzez `ProcessPoolExecutor`.

    Przykład:
        >>> import asyncio
        >>> from avena_commons.util.logger import MessageLogger
        >>> worker = GeneralCameraWorker(message_logger=MessageLogger())
        >>> async def demo():
        ...     await worker.init({})
        ...     await worker.start()
        ...     await worker.stop()
        >>> asyncio.run(demo())

    See Also:
        - `GeneralCameraConnector`: synchronizowany interfejs do workera.
    """
    def __init__(self, message_logger: Optional[MessageLogger] = None):
        """Zainicjalizuj workera kamery.

        Args:
            message_logger (Optional[MessageLogger]): Logger do komunikatów.

        Returns:
            None: Brak zwracanej wartości.

        Przykład:
            >>> worker = GeneralCameraWorker()
            >>> isinstance(worker, GeneralCameraWorker)
            True
        """
        self._message_logger = None
        self.device_name = f"GeneralCamera"
        super().__init__(message_logger=None)
        self.state = CameraState.IDLE

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
        """Zainicjalizuj połączenie i zasoby kamery.

        Metoda do nadpisania w klasie konkretnego sterownika kamery.

        Args:
            camera_settings (dict): Słownik ustawień kamery.

        Returns:
            bool: True gdy inicjalizacja się powiodła.

        Raises:
            Exception: Gdy inicjalizacja nie powiedzie się.

        Przykład:
            >>> import asyncio
            >>> class Dummy(GeneralCameraWorker):
            ...     async def init(self, camera_settings: dict):
            ...         return True
            >>> asyncio.run(Dummy().init({}))
            True
        """
        return True

    async def start(self):
        """Uruchom potok pobierania ramek kamery.

        Do nadpisania w implementacji konkretnej kamery.

        Args:
            None

        Returns:
            bool: True gdy start przebiegł pomyślnie.

        Raises:
            Exception: Gdy start nie powiedzie się.

        Przykład:
            >>> import asyncio
            >>> class Dummy(GeneralCameraWorker):
            ...     async def start(self):
            ...         return True
            >>> asyncio.run(Dummy().start())
            True
        """
        return True

    async def stop(self):
        """Zatrzymaj potok pobierania ramek kamery.

        Do nadpisania w implementacji konkretnej kamery.

        Args:
            None

        Returns:
            bool: True gdy zatrzymanie się powiodło.

        Raises:
            Exception: Gdy zatrzymanie nie powiedzie się.

        Przykład:
            >>> import asyncio
            >>> class Dummy(GeneralCameraWorker):
            ...     async def stop(self):
            ...         return True
            >>> asyncio.run(Dummy().stop())
            True
        """
        return True

    async def grab_frames_from_camera(self):
        """Pobierz aktualne ramki obrazu z kamery.

        Do nadpisania – powinna zwracać strukturę z danymi (np. dict).

        Args:
            None

        Returns:
            Optional[dict]: Zbiór ramek (np. klucze 'color', 'depth') lub None.

        Raises:
            Exception: Gdy pobieranie ramek nie powiedzie się.

        Przykład:
            >>> import asyncio
            >>> class Dummy(GeneralCameraWorker):
            ...     async def grab_frames_from_camera(self):
            ...         return {"color": b"..."}
            >>> asyncio.run(Dummy().grab_frames_from_camera())
            {'color': b'...'}
        """
        return None

    # MARK: WYWOŁYWANE PRZEZ CONNECTOR
    async def init_camera(self, camera_settings: dict):
        """Zainicjalizuj kamerę i zaktualizuj stan.

        Przechwytuje wyjątki i ustawia status błędu w razie problemów.

        Args:
            camera_settings (dict): Konfiguracja startowa kamery.

        Returns:
            bool: True w przypadku powodzenia, False w razie błędu.

        Raises:
            Exception: Nie propaguje; obsługiwane wewnętrznie, ale może się pojawić przy modyfikacjach.

        Przykład:
            >>> import asyncio
            >>> worker = GeneralCameraWorker()
            >>> asyncio.run(worker.init_camera({})) in (True, False)
            True
        """
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
        """Uruchom proces pobierania ramek i zaktualizuj stan.

        Returns:
            bool: True w przypadku powodzenia, False w razie błędu.

        Przykład:
            >>> import asyncio
            >>> worker = GeneralCameraWorker()
            >>> asyncio.run(worker.start_camera()) in (True, False)
            True
        """
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
        """Zatrzymaj proces pobierania ramek i zaktualizuj stan.

        Returns:
            bool: True w przypadku powodzenia, False w razie błędu.

        Przykład:
            >>> import asyncio
            >>> worker = GeneralCameraWorker()
            >>> asyncio.run(worker.stop_camera()) in (True, False)
            True
        """
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
        """Uruchom zadania przetwarzania obrazu w procesach.

        Każda konfiguracja postprocess jest wykonywana jako osobne
        zadanie w `ProcessPoolExecutor`.

        Args:
            frames (dict): Ostatnie ramki do przetwarzania.

        Returns:
            Optional[list]: Lista wyników zadań lub None przy błędzie/braku executor-a.

        Raises:
            Exception: Błędy zadań są przechwytywane i logowane.

        Przykład:
            >>> import asyncio
            >>> worker = GeneralCameraWorker()
            >>> worker.executor = None  # brak executora -> None
            >>> asyncio.run(worker._run_image_processing_workers({})) is None
            True
        """
        if not self.executor:
            return None
        
        try:
            # Submit funkcji do procesów (NIE tworzenie nowych workerów!)
            futures = {}
            for i, config in enumerate(self.postprocess_configuration):
                future = self.executor.submit(
                    self.detector,
                    self._process_single_config,  # Funkcja do wykonania
                    frames,                       # Dane
                    self.postprocess_configuration[i],                       # Konfiguracja
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
            
    async def _setup_image_processing_workers(self):
        """Przygotuj executor i metadane workerów postprocess.

        Tworzy `ProcessPoolExecutor` i listę opisów workerów na
        podstawie `self.postprocess_configuration`.

        Args:
            None

        Returns:
            bool: True po poprawnym przygotowaniu, False w razie błędu.

        Raises:
            Exception: Obsłużone wewnętrznie; błąd jest logowany.

        Przykład:
            >>> import asyncio
            >>> w = GeneralCameraWorker()
            >>> w.postprocess_configuration = []
            >>> asyncio.run(w._setup_image_processing_workers()) in (True, False)
            True
        """
        try:
            # Zamknij poprzedni executor jeśli istnieje
            if self.executor:
                self.executor.shutdown(wait=True)
            
            # Utwórz nowy executor
            self.executor = ProcessPoolExecutor(max_workers=len(self.postprocess_configuration))

            # Przygotuj workery (ale nie uruchamiaj jeszcze!)
            self.image_processing_workers = []
            for i, config in enumerate(self.postprocess_configuration):
                worker_info = {
                    "detector": self.detector,
                    "config": self.postprocess_configuration[i],
                    "config_name": self.postprocess_configuration[i]["mode"],
                }
                self.image_processing_workers.append(worker_info)
            
            debug(f"Utworzono {len(self.image_processing_workers)} workerów do przetwarzania obrazów: detector: '{self.detector}' postprocess configuration: {', '.join(config['mode'] for config in self.postprocess_configuration)}", 
                  self._message_logger)
            
            return True
            
        except Exception as e:
            error(f"Błąd podczas tworzenia workerów: {e}", self._message_logger)
            return False

    async def _run(self, pipe_in):
        """Główna pętla workera nasłuchująca komend przez pipe.

        Odpowiada za obsługę komend kontrolnych oraz cykliczne
        pobieranie ramek i ewentualny postprocess.

        Args:
            pipe_in: Dwukierunkowy kanał komunikacji (multiprocessing Pipe).

        Returns:
            None: Pętla kończy się przy anulowaniu zadania lub błędzie.

        Raises:
            asyncio.CancelledError: Gdy zadanie zostanie anulowane.

        Przykład:
            Nieuruchamialny wprost w docteście (wymaga procesu/pipe),
            ale wywoływany przez `GeneralCameraConnector`.

        See Also:
            - `GeneralCameraConnector._run`: metoda tworząca instancję workera.
        """
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
                                    f"{self.device_name} - Received SET_POSTPROCESS_CONFIGURATION: detector: '{data[1]}' postprocess configuration: {len(data[2])}",
                                    self._message_logger,
                                )
                                self.detector = data[1] # ustawienie detectora
                                self.pipeline_configuration = data[2]["configuration"] # ustawienie konfiguracji pipeline
                                self.postprocess_configuration = data[2]["postprocessors"] # ustawienie konfiguracji postprocess
                                # debug(f"{self.device_name} - Detector: {self.detector} Postprocess configuration: {len(self.postprocess_configuration)}", message_logger=self._message_logger)
                                await self._setup_image_processing_workers()

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
                        debug(f"{self.device_name} - Postprocess configuration: {len(self.postprocess_configuration)}", message_logger=self._message_logger)

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
    """Wątkowo-bezpieczny łącznik do `GeneralCameraWorker`.

    Zapewnia synchroniczne API wykorzystujące wewnętrznie komunikację
    przez pipe do procesu workera.

    Przykład:
        >>> connector = GeneralCameraConnector()
        >>> hasattr(connector, 'init') and hasattr(connector, 'start')
        True

    See Also:
        - `GeneralCameraWorker`: implementacja logiki asynchronicznej.
    """
    def __init__(self, message_logger: Optional[MessageLogger] = None):
        """Utwórz konektor z opcjonalnym loggerem.

        Args:
            message_logger (Optional[MessageLogger]): Zewnętrzny logger.

        Returns:
            None: Brak zwracanej wartości.

        Przykład:
            >>> GeneralCameraConnector() is not None
            True
        """
        self.__lock = threading.Lock()
        self._local_message_logger = message_logger

    def _run(self, pipe_in):
        """Uruchom pętlę workera w tym procesie.

        Tworzy instancję `GeneralCameraWorker` i wykonuje jego pętlę.

        Args:
            pipe_in: Końcówka pipe do komunikacji z workerem.

        Returns:
            None

        Przykład:
            Metoda wykorzystywana przez infrastrukturę `Connector`.
        """
        self.__lock = threading.Lock()
        worker = GeneralCameraWorker(message_logger=None)
        asyncio.run(worker._run(pipe_in))

    def init(self, configuration: dict = {}):
        """
        Zainicjalizuj kamerę przekazując konfigurację.

        Przekazuj tylko serializowalne dane przez pipe.

        Args:
            configuration (dict): Parametry inicjalizacji kamery.

        Returns:
            Any: Wartość zwrócona przez proces workera (zwykle bool).

        Przykład:
            >>> c = GeneralCameraConnector()
            >>> isinstance(c.init({}), (bool, type(None)))
            True
        """
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out, ["CAMERA_INIT", configuration]
            )
            return value

    def start(self):
        """Rozpocznij pobieranie ramek w kamerze.

        Returns:
            Any: Wartość z procesu workera (zwykle bool).

        Przykład:
            >>> GeneralCameraConnector().start() in (True, False, None)
            True
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["CAMERA_START_GRABBING"])
            return value

    def stop(self):
        """Zatrzymaj pobieranie ramek w kamerze.

        Returns:
            Any: Wartość z procesu workera (zwykle bool).

        Przykład:
            >>> GeneralCameraConnector().stop() in (True, False, None)
            True
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["CAMERA_STOP_GRABBING"])
            return value

    def get_state(self):
        """Pobierz aktualny stan kamery.

        Returns:
            Any: Instancja `CameraState` lub None.

        Przykład:
            >>> GeneralCameraConnector().get_state() in (None, CameraState.IDLE)
            True
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["GET_STATE"])
            return value

    def get_last_frames(self):
        """Pobierz ostatnio odebrane ramki.

        Returns:
            Any: Struktura ramek (np. dict) lub None.

        Przykład:
            >>> GeneralCameraConnector().get_last_frames() is None
            True
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["GET_LAST_FRAMES"])
            return value

    def set_postprocess_configuration(self, *, detector: str = None, configuration: list = None):
        """Ustaw konfigurację postprocess oraz nazwę detektora.

        Args:
            detector (str, optional): Nazwa detektora/postprocessu.
            configuration (list, optional): Lista słowników konfiguracji.

        Returns:
            Any: Wartość z procesu workera (zwykle bool).

        Przykład:
            >>> GeneralCameraConnector().set_postprocess_configuration(
            ...     detector="dummy", configuration=[])
            in (True, False, None)
            True
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["SET_POSTPROCESS_CONFIGURATION", detector, configuration])
            return value
