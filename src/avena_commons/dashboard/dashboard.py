import importlib
import json
import traceback
from typing import Any, Dict, Optional

from avena_commons.event_listener.event import Event, Result
from avena_commons.event_listener.event_listener import (
    EventListener,
)
from avena_commons.util.logger import MessageLogger, debug, error, warning
from avena_commons.util.measure_time import MeasureTime


class Dashboard(EventListener):
    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        message_logger: MessageLogger | None = None,
        do_not_load_state: bool = True,
        debug: bool = True,
    ):
        self._message_logger = message_logger
        self._debug = debug
        try:
            super().__init__(
                name=name,
                port=port,
                address=address,
                message_logger=self._message_logger,
                do_not_load_state=True,
            )
        except Exception as e:
            error(f"Initialisation error: {e}", message_logger=self._message_logger)

    async def _analyze_event(self, event: Event) -> bool:
        match event.event_type:
            case "CMD_GET_STATE":
                if event.result is not None:
                    # Event ma result - usuń go z processing
                    self._find_and_remove_processing_event(
                        event_type=event.event_type,
                        id=event.id,
                        timestamp=event.timestamp,
                    )
            case _:
                pass
        return True

    async def _check_local_data(self):  # MARK: CHECK LOCAL DATA
        for key, client in self._configuration["clients"].items():
            client_port = client["port"]
            client_address = client["address"]
            event = await self._event(
                destination=key,
                destination_address=client_address,
                destination_port=client_port,
                event_type="CMD_GET_STATE",
                data={},
                to_be_processed=False,
            )
            self._add_to_processing(event)

    def _clear_before_shutdown(self):
        __logger = self._message_logger  # Zapisz referencję jeśli potrzebna
        # Ustaw na None aby inne wątki nie próbowały używać
        self._message_logger = None
