import os
import sys

# Add the src directory to the system path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from dotenv import load_dotenv
from pupil_apriltags import Detector

from avena_commons.camera.camera import Camera
from avena_commons.camera.driver.general import CameraState
from avena_commons.event_listener import EventListenerState
from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
    debug,
    error,
    info,
)


class CameraServer(Camera):
    def __init__(
        self,
        camera_ip: str,
        port: str,
        address: str,
        message_logger: MessageLogger | None = None,
        do_not_load_state: bool = False,
    ):
        # Domyślny stan i konfiguracja
        self._state = {}

        self._default_configuration = {  # domyślna konfiguracja
            "camera_configuration": {
                "camera_ip": camera_ip,
                "model": "orbec_gemini_335le",
            }
        }
        self.detector = None
        self.check_local_data_frequency: int = 60

        # Dodaj detektor apriltag dla QR
        try:
            self.apriltag_detector = Detector(families="tag36h11")
            info("Utworzono detektor apriltag", self._message_logger)
        except Exception as e:
            error(f"Błąd tworzenia detektora apriltag: {e}", self._message_logger)
            self.apriltag_detector = None

        super().__init__(
            name=f"camera_server_{camera_ip}",
            address=address,
            port=port,
            message_logger=message_logger,
            do_not_load_state=do_not_load_state,
        )
        self.start()

    # MARK: SEND EVENTS
    async def on_stopped(self):
        self.fsm_state = EventListenerState.INITIALIZING

    async def on_initialized(self):
        self.fsm_state = EventListenerState.STARTING

    async def _check_local_data(self):
        """
        Periodically checks and processes local data

        Raises:
            Exception: If an error occurs during data processing.
        """
        camera_state = self.camera.get_state()
        # debug(
        #     f"EVENT_LISTENER_CHECK_LOCAL_DATA: {camera_state} {type(camera_state)}",
        #     self._message_logger,
        # )
        match camera_state:
            case CameraState.ERROR:
                self.set_state(EventListenerState.ON_ERROR)
            case CameraState.STARTED:
                # Przykład zapisywania ramek (dla demonstracji)
                # with Catchtime() as ct:
                last_frame = self.camera.get_last_frame()
                # pass
                if last_frame is not None:
                    self.latest_color_frame = last_frame["color"]
                    self.latest_depth_frame = last_frame["depth"]
                    debug(
                        f"Pobrano ramki Koloru i Głębi: {self.latest_color_frame.shape}, {self.latest_depth_frame.shape}",
                        self._message_logger,
                    )
                    result = self.camera.run_postprocess_workers(last_frame)
                    debug(
                        f"result type: {type(result)}, result: {result}",
                        self._message_logger,
                    )
                else:
                    error(
                        f"EVENT_LISTENER_CHECK_LOCAL_DATA: Brak ramki Koloru lub Głębi",
                        self._message_logger,
                    )
            # debug(
            #     f"EVENT_LISTENER_CHECK_LOCAL_DATA: Pobrano ramki Koloru i Głębi w {ct.t * 1_000:.2f}ms",
            #     self._message_logger,
            # )
            case _:
                debug(
                    f"EVENT_LISTENER_CHECK_LOCAL_DATA: {camera_state}",
                    self._message_logger,
                )

    def _clear_before_shutdown(self):
        __logger = self._message_logger  # Zapisz referencję jeśli potrzebna
        # Ustaw na None aby inne wątki nie próbowały używać
        self._message_logger = None


if __name__ == "__main__":
    try:
        message_logger = MessageLogger(
            filename=f"temp/test_camera.log",
            debug=True,
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
            files_count=40,
        )
        load_dotenv(override=True)

        port = 9900

        print("port: ", port)
        listener = CameraServer(
            port=port,
            address="127.0.0.1",
            camera_ip="192.168.1.10",
            message_logger=message_logger,
        )
    except Exception as e:
        # del message_logger
        error(f"Nieoczekiwany błąd w głównym wątku: {e}", message_logger=None)
