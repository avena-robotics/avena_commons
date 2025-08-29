import asyncio
import base64
import threading
import time
import traceback

import cv2
import numpy as np
from dotenv import load_dotenv
from pyorbbecsdk import (
    AlignFilter,
    Config,
    Context,
    OBAlignMode,
    OBFormat,
    OBPermissionType,
    OBPropertyID,
    OBPropertyType,
    OBSensorType,
    OBStreamType,
    Pipeline,
    SpatialAdvancedFilter,
    TemporalFilter,
    VideoStreamProfile,
)

from avena_commons.camera.driver.general import CameraState
from avena_commons.camera.driver.orbec_335le import OrbecGemini335Le
from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
    Result,
)
from avena_commons.util.logger import MessageLogger, debug, error, info

load_dotenv(override=True)


class Camera(EventListener):
    """
    Main logic class for handling events and managing the state of the Munchies system.
    """

    def __init__(
        self,
        name: str,
        address: str,
        port: str,
        message_logger: MessageLogger | None = None,
        do_not_load_state: bool = False,
    ):
        """
        Initializes the Camera with necessary configurations and state.

        Args:
            message_logger (Optional[MessageLogger]): Logger for logging messages.

        Raises:
            ValueError: If required environment variables are missing.
        """

        if not port:
            raise ValueError(
                "Brak wymaganej zmiennej środowiskowej CAMERA_LISTENER_PORT"
            )

        self._check_local_data_frequency = 100
        self.name = name

        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
        )

        debug(f"camera init", self._message_logger)

        # print(self._configuration)

        if self._configuration.get("camera_ip", None) is None:
            error(
                f"EVENT_LISTENER_INIT: Brak konfiguracji CAMERA_IP dla kamery",
                self._message_logger,
            )
            raise ValueError(f"Brak konfiguracji CAMERA_IP dla kamery")
        self.camera_address = self._configuration["camera_ip"]

        self.camera_running = False

        # Bufory dla synchronizacji ramek
        self.latest_color_frame = None
        self.latest_depth_frame = None
        self.last_color_timestamp = 0
        self.last_depth_timestamp = 0
        self.frame_sync_timeout = 500  # ms - maksymalna różnica czasowa między ramkami (zwiększone dla stabilności)

        debug(
            f"EVENT_LISTENER_INIT: Event listener kamery został zainicjalizowany dla ip {self.camera_address}",
            self._message_logger,
        )
        self.camera = OrbecGemini335Le(self.camera_address, self._message_logger)

    async def on_initializing(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZING.
        Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
        self.camera.init(self._configuration["camera_settings"])

    async def on_starting(self):
        """Metoda wywoływana podczas przejścia w stan STARTING.
        Tu komponent przygotowuje się do uruchomienia głównych operacji."""
        self.camera.start()

    async def on_stopping(self):
        self.camera.stop()
