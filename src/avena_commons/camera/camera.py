import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import cv2
from dotenv import load_dotenv

from avena_commons.camera.driver.orbec_335le import OrbecGemini335Le
from avena_commons.event_listener import EventListener
from avena_commons.util.logger import MessageLogger, debug, error

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
        self.__camera_config = self._configuration.get("camera_configuration", {})
        debug(f"camera config: {self.__camera_config}", self._message_logger)
        self.__pipelines_config = self._configuration.get("pipelines", {})
        debug(f"pipelines config: {self.__pipelines_config}", self._message_logger)
        self.__save_config = self._configuration.get("save_configuration", {})

        if self.__camera_config.get("camera_ip", None) is None:
            error(
                f"EVENT_LISTENER_INIT: Brak konfiguracji CAMERA_IP dla kamery",
                self._message_logger,
            )
            raise ValueError(f"Brak konfiguracji CAMERA_IP dla kamery")
        self.camera_address = self.__camera_config["camera_ip"]

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
        match self.__camera_config.get("model", None):
            case "orbec_gemini_335le":
                self.camera = OrbecGemini335Le(
                    self.camera_address, self._message_logger
                )
            case _:
                error(
                    f"EVENT_LISTENER_INIT: Brak obsługiwanej kamery {self.__camera_config.get('model', None)} obsługiwane modele: orbec_gemini_335le",
                    self._message_logger,
                )

    async def on_initializing(self):
        """Metoda wywoływana podczas przejścia w stan INITIALIZING.
        Tu komponent powinien nawiązywać połączenia, alokować zasoby itp."""
        self.camera.init(self.__camera_config)

    async def on_starting(self):
        """Metoda wywoływana podczas przejścia w stan STARTING.
        Tu komponent przygotowuje się do uruchomienia głównych operacji."""
        # Uruchom kamerę
        # TODO: Odpowiedź na eventy aby wiedzieć, który postprocess użyć
        self.camera.set_postprocess_configuration(
            detector="qr_detector",
            configuration=self.__pipelines_config["qr_detector"],
        )
        # self.camera.set_postprocess_configuration(
        #     detector="box_detector",
        #     configuration=self.__pipelines_config["box_detector"],
        # )

        self.camera.start()

    async def on_stopping(self):
        self.camera.stop()
