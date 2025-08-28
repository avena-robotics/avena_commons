import argparse
import os
import sys
from enum import Enum

# Add the src directory to the system path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from dotenv import load_dotenv

from avena_commons.camera.camera import Camera, CameraState
from avena_commons.event_listener import Event, EventListenerState
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger, debug, error
from avena_commons.vision.detector import ObjectDetector


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
                # "disparity": {"range_mode": "Default", "search_offset": 0},
                "filters": {
                    "spatial": False,
                    "temporal": False,
                },
            },
        }
        self.detector = ObjectDetector()
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

    async def _check_local_data(self):
        """
        Periodically checks and processes local data

        Raises:
            Exception: If an error occurs during data processing.
        """
        camera_state = self.camera.get_state()
        debug(
            f"EVENT_LISTENER_CHECK_LOCAL_DATA: {camera_state} {type(camera_state)}",
            self._message_logger,
        )
        match camera_state:
            case CameraState.ERROR:
                self.set_state(EventListenerState.ON_ERROR)
            case CameraState.STARTED:
                pass
            # with Catchtime() as ct:
            # last_frames = self.camera.get_last_frames()
            # pass
            #             if last_frames is not None:
            #                 self.latest_color_frame = last_frames["color"]
            #                 self.latest_depth_frame = last_frames["depth"]
            #             else:
            #                 error(
            #                     f"EVENT_LISTENER_CHECK_LOCAL_DATA: Brak ramki Koloru lub Głębi",
            #                     self._message_logger,
            #                 )
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
            colors=False,
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
