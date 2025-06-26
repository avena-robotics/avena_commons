import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from avena_commons.event_listener import Event, EventListener
from avena_commons.orchestrator.orchestrator import Orchestrator
from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger, debug


class TestOrchestrator(Orchestrator):
    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        message_logger=None,
        debug=False,
    ):
        self.check_local_data_frequency = 1
        super().__init__(
            name=name,
            address=address,
            port=port,
            do_not_load_state=True,
            message_logger=message_logger,
        )
        self.start()

    async def _analyze_event(self, event: Event) -> bool:
        match event.event_type:
            case "health_check":
                pass
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
                event_type="health_check",
                data={},
                to_be_processed=False,
            )
            self._add_to_processing(event)

    def _clear_before_shutdown(self):
        __logger = self._message_logger  # Zapisz referencję jeśli potrzebna
        # Ustaw na None aby inne wątki nie próbowały używać
        self._message_logger = None


if __name__ == "__main__":
    temp_path = os.path.abspath("temp")
    message_logger = MessageLogger(
        filename=f"{temp_path}/test_orchestrator.log",
        period=LoggerPolicyPeriod.LAST_15_MINUTES,
    )
    # message_logger = None
    port = 9500
    try:
        app = TestOrchestrator(
            name=f"test_orchestrator",
            address="127.0.0.1",
            port=port,
            message_logger=message_logger,
            debug=True,
        )

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
    finally:
        try:
            # supervisor.cleanup()
            pass
        except NameError:
            pass
