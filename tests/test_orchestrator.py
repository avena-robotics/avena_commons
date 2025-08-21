import os

from avena_commons.orchestrator.orchestrator import Orchestrator
from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger


class TestOrchestrator(Orchestrator):
    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        message_logger=None,
    ):
        self.check_local_data_frequency = 1
        self._default_configuration["clients"] = {}
        super().__init__(
            name=name,
            address=address,
            port=port,
            message_logger=message_logger,
        )
        # Nie uruchamiamy start() tutaj - będzie w async metodzie


if __name__ == "__main__":
    # asyncio.run(main())
    temp_path = os.path.abspath("temp")

    # Utwórz katalog temp jeśli nie istnieje
    os.makedirs(temp_path, exist_ok=True)

    message_logger = MessageLogger(
        filename=f"{temp_path}/test_orchestrator.log",
        period=LoggerPolicyPeriod.LAST_15_MINUTES,
    )
    # message_logger = None
    port = 9500

    app = TestOrchestrator(
        name="test_orchestrator",
        address="127.0.0.1",
        port=port,
        message_logger=message_logger,
    )
    app.start()
