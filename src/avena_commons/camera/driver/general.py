import asyncio
import importlib
import threading
import traceback
from concurrent.futures import (
    ProcessPoolExecutor,
    TimeoutError,
    as_completed,
)
from enum import Enum
from typing import Optional

import avena_commons.vision.merge as merge
import avena_commons.vision.sorter as sorter
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import MessageLogger, debug, error, info
from avena_commons.util.worker import Connector, Worker
from avena_commons.vision.camera import create_camera_matrix
from avena_commons.vision.vision import calculate_pose_pnp

# Dodać import kompatybilny z różnymi wersjami Pythona
try:
    from concurrent.futures import BrokenProcessPool, ProcessLookupError
except ImportError:
    # Kompatybilność z Python 3.8/3.9
    class BrokenProcessPool(RuntimeError):
        """Zastępczy wyjątek dla starszych wersji Pythona."""

        pass

    ProcessLookupError = OSError


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

        self.last_frame = None
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

    async def _run_image_processing_workers(self, frame: dict):
        """Uruchom zadania przetwarzania obrazu w procesach z robust error handling."""
        if not self.executor:
            return None

        # Sprawdź czy executor jest uszkodzony przed użyciem
        if self._is_executor_broken():
            debug("Executor uszkodzony, próba odtworzenia", self._message_logger)
            if not await self._recreate_executor_if_broken():
                error("Nie udało się odtworzyć executor-a", self._message_logger)
                return None

        try:
            # Submit zadań z wykrywaniem uszkodzonego pool-a
            futures = {}
            failed_submits = 0

            for i, worker in enumerate(self.image_processing_workers):
                try:
                    # Dodaj timeout dla submit operacji
                    future = self.executor.submit(
                        worker.get("detector"),
                        frame=frame,
                        camera_config=self.camera_configuration,
                        config=worker.get("config"),
                    )
                    futures[future] = i

                except (BrokenProcessPool, RuntimeError) as e:
                    if any(
                        keyword in str(e).lower()
                        for keyword in [
                            "process pool",
                            "terminated abruptly",
                            "child process",
                        ]
                    ):
                        error(
                            f"Process pool uszkodzony podczas submit worker_{i}: {e}",
                            self._message_logger,
                        )
                        failed_submits += 1

                        # Jeśli pierwszy submit kończy się błędem pool-a, spróbuj odtworzyć
                        if len(futures) == 0:
                            if await self._recreate_executor_if_broken():
                                debug(
                                    "Odtworzono executor, ponawianie submit",
                                    self._message_logger,
                                )
                                try:
                                    future = self.executor.submit(
                                        worker.get("detector"),
                                        frame=frame,
                                        camera_config=self.camera_configuration,
                                        config=worker.get("config"),
                                    )
                                    futures[future] = i
                                    failed_submits -= 1
                                except Exception as retry_e:
                                    error(
                                        f"Ponowny submit worker_{i} nieudany: {retry_e}",
                                        self._message_logger,
                                    )
                            else:
                                break  # Nie udało się odtworzyć, przerwij
                        continue
                    else:
                        error(
                            f"Błąd podczas submit worker_{i}: {e}", self._message_logger
                        )
                        continue

                except Exception as e:
                    error(
                        f"Nieoczekiwany błąd podczas submit worker_{i}: {e}",
                        self._message_logger,
                    )
                    continue

            if not futures:
                if failed_submits > 0:
                    error(
                        f"Wszystkie {failed_submits} submit-y nieudane z powodu uszkodzonego pool-a",
                        self._message_logger,
                    )
                else:
                    debug("Brak aktywnych zadań do wykonania", self._message_logger)
                return []

            debug(
                f"Submitted {len(futures)} tasks (failed: {failed_submits})",
                self._message_logger,
            )

            # Zbieranie wyników z rozszerzonym timeout handling
            results = {}
            completed_count = 0

            try:
                for future in as_completed(futures, timeout=30.0):  # Zwiększony timeout
                    config_id = futures[future]
                    completed_count += 1

                    try:
                        if future.cancelled():
                            debug(
                                f"Task config_{config_id} został anulowany",
                                self._message_logger,
                            )
                            continue

                        result = future.result(
                            timeout=10.0
                        )  # Zwiększony timeout na pojedynczy wynik
                        if result is not None:
                            # result[0] to Detection object list
                            # result[1] to debug data dict
                            debug(
                                f"Otrzymano wynik z config_{config_id}, result type: {type(result[0])}, result len: {len(result[0]) if result[0] else 0}",
                                self._message_logger,
                            )
                            sorted_detections = sorter.sort_qr_by_center_position(
                                expected_count=4,  # Max zwracanych detekcji
                                detections=result[0],
                            )
                            debug(
                                f"Otrzymano wynik z config_{config_id}, sorted_detections type: {type(sorted_detections)}, sorted_detections len: {len(sorted_detections) if sorted_detections else 0}, sorted_detections: {sorted_detections}",
                                self._message_logger,
                            )
                            results = merge.merge_qr_detections_with_confidence(
                                sorted_detections,
                                results,
                            )

                            # Konwersja Detection objektów na proste pozycje QR kodów
                            qr_positions = {}
                            for position_id, detection in results.items():
                                if detection is not None:
                                    qr_positions[position_id] = calculate_pose_pnp(
                                        corners=detection.corners,
                                        a=self.postprocess_configuration["a"]["qr_size"]
                                        * 1000,
                                        b=self.postprocess_configuration["a"]["qr_size"]
                                        * 1000,
                                        z=0,
                                        camera_matrix=create_camera_matrix(
                                            self.camera_configuration["camera_params"]
                                        ),
                                    )
                                else:
                                    qr_positions[position_id] = None

                            # Zastąp results uproszczoną strukturą
                            results = qr_positions

                            debug(
                                f"Otrzymano wynik z config_{config_id}, qr_positions type: {type(qr_positions)}, qr_positions: {qr_positions}",
                                self._message_logger,
                            )

                            actual_detections = sum(
                                1 for v in results.values() if v is not None
                            )
                            if actual_detections == 4:
                                debug(
                                    f"Otrzymano pełny zestaw detekcji z config_{config_id}",
                                    self._message_logger,
                                )
                                # Anuluj pozostałe zadania, gdy mamy już wszystkie 4 QR
                                self._cancel_pending_futures(futures)
                                break
                        else:
                            debug(
                                f"Pusty wynik z config_{config_id}",
                                self._message_logger,
                            )

                    except ProcessLookupError as e:
                        error(
                            f"Proces config_{config_id} został zakończony: {e}",
                            self._message_logger,
                        )
                        continue
                    except BrokenProcessPool as e:
                        error(
                            f"Process pool uszkodzony przy config_{config_id}: {e}",
                            self._message_logger,
                        )
                        await self._recreate_executor_if_broken()
                        break
                    except TimeoutError:
                        error(
                            f"Timeout przy pobieraniu wyniku config_{config_id}",
                            self._message_logger,
                        )
                        continue
                    except RuntimeError as e:
                        if any(
                            keyword in str(e).lower()
                            for keyword in ["process", "pool", "terminated abruptly"]
                        ):
                            error(
                                f"Process issue przy config_{config_id}: {e}",
                                self._message_logger,
                            )
                            await self._recreate_executor_if_broken()
                            break
                        else:
                            error(
                                f"Runtime error w config_{config_id}: {e}",
                                self._message_logger,
                            )
                            continue
                    except Exception as e:
                        error(
                            f"Nieoczekiwany błąd w config_{config_id}: {e}",
                            self._message_logger,
                        )
                        continue

            except TimeoutError:
                error(
                    "Timeout podczas oczekiwania na zakończenie zadań",
                    self._message_logger,
                )
                self._cancel_pending_futures(futures)

            debug(
                f"Zakończono przetwarzanie: {completed_count}/{len(futures)} zadań",
                self._message_logger,
            )
            return results

        except Exception as e:
            error(f"Błąd podczas uruchamiania workerów: {e}", self._message_logger)
            if "futures" in locals():
                self._cancel_pending_futures(futures)
            return None

    def _cancel_pending_futures(self, futures: dict):
        """Anuluj pending futures w przypadku błędu.

        Args:
            futures (dict): Słownik future -> config_id do anulowania.
        """
        try:
            for future in futures.keys():
                if not future.done():
                    future.cancel()
            debug("Anulowano pending futures", self._message_logger)
        except Exception as e:
            error(f"Błąd podczas anulowania futures: {e}", self._message_logger)

    async def _recreate_executor_if_broken(self):
        """Odtwórz executor w przypadku uszkodzenia process pool.

        Returns:
            bool: True jeśli udało się odtworzyć executor.
        """
        try:
            debug("Próba odtworzenia uszkodzonego executor-a", self._message_logger)

            # Zamknij uszkodzony executor
            if self.executor:
                try:
                    self.executor.shutdown(wait=False)
                except:
                    pass  # Ignore błędy przy zamykaniu uszkodzonego executora
                self.executor = None

            # Poczekaj chwilę przed odtworzeniem
            await asyncio.sleep(0)

            # Odtwórz setup
            success = await self._setup_image_processing_workers()
            if success:
                debug("Pomyślnie odtworzono executor", self._message_logger)
            else:
                error("Nie udało się odtworzyć executor-a", self._message_logger)
            return success

        except Exception as e:
            error(f"Błąd podczas odtwarzania executor-a: {e}", self._message_logger)
            return False

    def _is_executor_broken(self) -> bool:
        """Sprawdź czy executor jest uszkodzony.

        Returns:
            bool: True jeśli executor jest uszkodzony lub None.
        """
        if not self.executor:
            return True

        # Sprawdź czy executor ma właściwość _broken
        if hasattr(self.executor, "_broken") and self.executor._broken:
            return True

        return False

    async def _setup_image_processing_workers(self):
        """Przygotuj executor z ograniczoną liczbą procesów."""
        try:
            # Zamknij poprzedni executor jeśli istnieje
            if self.executor:
                try:
                    self.executor.shutdown(wait=True)
                except Exception:
                    pass  # Ignoruj błędy przy zamykaniu
                finally:
                    self.executor = None

            # Sprawdź czy mamy konfigurację
            if not self.postprocess_configuration:
                debug(
                    "Brak konfiguracji postprocess, executor nie zostanie utworzony",
                    self._message_logger,
                )
                return True

            # Utwórz nowy executor z ograniczoną liczbą workerów dla stabilności
            max_workers = min(
                len(self.postprocess_configuration), 4
            )  # Maksymalnie 4 procesy
            self.executor = ProcessPoolExecutor(max_workers=max_workers)

            # Przygotuj workery
            self.image_processing_workers = []
            for config_key, config_value in self.postprocess_configuration.items():
                debug(
                    f"config_key: {config_key}, config_value: {config_value}",
                    self._message_logger,
                )
                worker_info = {
                    "detector": self.detector,
                    "config": config_value,
                }
                self.image_processing_workers.append(worker_info)

            debug(
                f"Utworzono executor z {max_workers} workerami dla {len(self.image_processing_workers)} konfiguracji",
                self._message_logger,
            )
            return True

        except Exception as e:
            error(f"Błąd podczas tworzenia workerów: {e}", self._message_logger)
            self.executor = None
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
                                self.camera_configuration = data[1]
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

                        case "GET_LAST_FRAME":
                            try:
                                pipe_in.send(self.last_frame)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error getting last frame: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(None)

                        case "SET_POSTPROCESS_CONFIGURATION":
                            try:
                                debug(
                                    f"{self.device_name} - Received SET_POSTPROCESS_CONFIGURATION: detector: '{data[1]}' postprocess configuration: {len(data[2])}",
                                    self._message_logger,
                                )

                                # Dynamiczny import funkcji detektora z avena_commons.vision.detector
                                detector_name = data[1]
                                if detector_name:
                                    try:
                                        # Import modułu detector z avena_commons.vision
                                        detector_module = importlib.import_module(
                                            "avena_commons.vision.detector"
                                        )

                                        # Pobierz funkcję detektora na podstawie nazwy
                                        if hasattr(detector_module, detector_name):
                                            self.detector = getattr(
                                                detector_module, detector_name
                                            )
                                            debug(
                                                f"{self.device_name} - Successfully imported detector function: {detector_name}",
                                                self._message_logger,
                                            )
                                        else:
                                            error(
                                                f"{self.device_name} - Detector function '{detector_name}' not found in avena_commons.vision.detector",
                                                self._message_logger,
                                            )
                                            self.detector = None
                                    except ImportError as ie:
                                        error(
                                            f"{self.device_name} - Failed to import avena_commons.vision.detector: {ie}",
                                            self._message_logger,
                                        )
                                        self.detector = None
                                    except Exception as de:
                                        error(
                                            f"{self.device_name} - Error importing detector '{detector_name}': {de}",
                                            self._message_logger,
                                        )
                                        self.detector = None
                                else:
                                    self.detector = None
                                    debug(
                                        f"{self.device_name} - No detector name provided, detector set to None",
                                        self._message_logger,
                                    )

                                self.pipeline_configuration = data[2][
                                    "configuration"
                                ]  # ustawienie konfiguracji pipeline
                                self.postprocess_configuration = data[2][
                                    "postprocessors"
                                ]  # ustawienie konfiguracji postprocess
                                debug(
                                    f"{self.device_name} - Detector: {self.detector} Postprocess configuration: {len(self.postprocess_configuration)}",
                                    message_logger=self._message_logger,
                                )
                                await self._setup_image_processing_workers()

                                pipe_in.send(True)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error setting postprocess configuration: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(False)
                        case "RUN_POSTPROCESS":
                            try:
                                debug(
                                    f"{self.device_name} - Received RUN_POSTPROCESS with frames",
                                    self._message_logger,
                                )
                                frames = data[1]
                                results = await self._run_image_processing_workers(
                                    frames
                                )
                                pipe_in.send(results)
                            except Exception as e:
                                error(
                                    f"{self.device_name} - Error running postprocess: {e}",
                                    message_logger=self._message_logger,
                                )
                                pipe_in.send(None)
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
                        self.last_frame = frames
                    # color_image = frames["color"]
                    # depth_image = frames["depth"]
                    debug(
                        f"{self.device_name} - Pobrano ramki Koloru i Głębi w {ct.t * 1_000:.2f}ms",
                        self._message_logger,
                    )
                    # przetwarzanie wizyjne
                    if self.postprocess_configuration:
                        debug(
                            f"{self.device_name} - Postprocess configuration: {len(self.postprocess_configuration)}",
                            message_logger=self._message_logger,
                        )

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

    def get_last_frame(self):
        """Pobierz ostatnio odebrane ramki.

        Returns:
            Any: Struktura ramek (np. dict) lub None.

        Przykład:
            >>> GeneralCameraConnector().get_last_frame() is None
            True
        """
        with self.__lock:
            value = super()._send_thru_pipe(self._pipe_out, ["GET_LAST_FRAME"])
            return value

    def set_postprocess_configuration(
        self, *, detector: str = None, configuration: list = None
    ):
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
            value = super()._send_thru_pipe(
                self._pipe_out,
                ["SET_POSTPROCESS_CONFIGURATION", detector, configuration],
            )
            return value

    def run_postprocess_workers(self, frame: dict):
        """Uruchom postprocess na podanych ramkach.

        Args:
            frames (dict): Ramki do przetworzenia.

        Returns:
            Any: Wyniki postprocessu lub None.

        Przykład:
            >>> GeneralCameraConnector().run_postprocess({}) is None
            True
        """
        with self.__lock:
            value = super()._send_thru_pipe(
                self._pipe_out,
                ["RUN_POSTPROCESS", frame],
            )
            return value
