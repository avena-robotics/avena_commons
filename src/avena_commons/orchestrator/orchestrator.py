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


class Orchestrator(EventListener):
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
