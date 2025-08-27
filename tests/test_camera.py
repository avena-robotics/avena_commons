import argparse
import os
import sys
from enum import Enum

# Add the src directory to the system path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from dotenv import load_dotenv

from avena_commons.camera.camera import Camera
from avena_commons.event_listener import EventListenerState
from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger, error


class CameraState(Enum):
    IDLE = 0  # idle
    INIT = 1  # init camera
    START = 2  # start camera pipeline
    RUN = 3  # run camera pipeline
    STOP = 4  # stop camera pipeline
    ERROR = 255  # error


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

        self._default_configuration = {  # domyslna konfiguracja
            "camera_ip": camera_ip,
            "camera_settings": {
                "align": "d2c",  # None, d2c, potem: c2d
                "disparity_to_depth": True,
                "color": {
                    "width": 1280,
                    "height": 800,
                    "fps": 30,
                    "format": "MJPG",
                    "exposure": 500,
                    "gain": 10,
                    "white_balance": 4000,
                },
                "depth": {
                    "width": 640,
                    "height": 400,
                    "fps": 30,
                    "format": "Y16",
                    "exposure": 500,
                    "gain": 10,
                    "laser_power": 5,
                },
                "disparity": {"range_mode": "Default", "search_offset": 0},
                "filters": {
                    "spatial": False,
                    "temporal": False,
                },
            },
            "rois": [
                {"x": [100, 280], "y": [20, 200]},
                {"x": [320, 500], "y": [20, 200]},
                {"x": [100, 280], "y": [220, 400]},
                {"x": [320, 500], "y": [220, 400]},
            ],
        }

        self.check_local_data_frequency: int = 60
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

    #     pass
    # def on_init(self):
    #     pass
    # def on_start(self):
    #     pass
    # def on_run(self):

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
            colors=False,
        )
        load_dotenv(override=True)

        port = 9900

        # if not port:
        #     raise ValueError(
        #         f"Brak wymaganej zmiennej środowiskowej CAMERA{args.number}_LISTENER_PORT"
        #     )

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
