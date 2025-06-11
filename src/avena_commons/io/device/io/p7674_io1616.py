from avena_commons.util.logger import MessageLogger

from ..io_utils import init_device_di, init_device_do
from .p7674 import P7674


class P7674_IO1616(P7674):
    def __init__(
        self,
        device_name: str,
        bus,
        address,
        message_logger: MessageLogger | None = None,
        debug=True,
    ):
        super().__init__(
            device_name=device_name,
            bus=bus,
            address=address,
            message_logger=message_logger,
            debug=debug,
            offset=1,
        )


init_device_di(P7674_IO1616, first_index=1, count=16)
init_device_do(P7674_IO1616, first_index=1, count=16)
