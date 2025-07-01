import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from avena_commons.event_listener import Event, EventListener
from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger, debug


class TestServer(EventListener):
    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        clients: int,
        payload: int,
        message_logger=None,
        message_logger_queues=None,
        debug=False,
        # use_http_session=True,
        # use_parallel_send=True,
    ):
        self.payload = payload
        self.check_local_data_frequency = 1
        super().__init__(
            name=name,
            address=address,
            port=port,
            do_not_load_state=True,
            message_logger=message_logger,
            # use_http_session=use_http_session,
            # use_parallel_send=use_parallel_send,
        )
        self.clients = clients
        self.message_logger_queues = message_logger_queues
        self.start()

    async def _analyze_event(self, event: Event) -> bool:
        self._find_and_remove_processing_event(event=event)
        return True

    async def _check_local_data(self):  # MARK: CHECK LOCAL DATA
        for client in range(1, self.clients + 1):
            client_port = self._EventListener__port + client
            for i in range(self.payload):
                event = await self._event(
                    destination=f"test_client_{client_port}",
                    destination_address=self._EventListener__address,
                    destination_port=client_port,
                    event_type=f"test_from_{self._EventListener__port}",
                    data={"message": f"test {i}"},
                    to_be_processed=True,
                )
                self._add_to_processing(event)
        debug(
            f"incommming = {self.size_of_incomming_events_queue()}, processing = {self.size_of_processing_events_queue()}, to_send = {self.size_of_events_to_send_queue()}, [{self.sended_events}, {self.received_events}, {self.sended_events - self.received_events}]",
            message_logger=self._message_logger,
        )
        pass

    def _clear_before_shutdown(self):
        __logger = self._message_logger  # Zapisz referencję jeśli potrzebna
        # Ustaw na None aby inne wątki nie próbowały używać
        self._message_logger = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="supervisor server")
    parser.add_argument(
        "-c",
        "--clients",
        type=int,
        default=3,
        help="test clients number (default: 3)",
    )
    parser.add_argument(
        "-p",
        "--payload",
        type=int,
        default=3,
        help="payload size (default: 3)",
    )
    args = parser.parse_args()

    temp_path = os.path.abspath("temp")
    message_logger = MessageLogger(
        filename=f"{temp_path}/test_server.log",
        period=LoggerPolicyPeriod.LAST_15_MINUTES,
    )
    port = 9200
    try:
        app = TestServer(
            name=f"test_server_{port}",
            address="127.0.0.1",
            port=port,
            message_logger=message_logger,
            debug=True,
            clients=args.clients,
            payload=args.payload,
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
