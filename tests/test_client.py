import argparse
import asyncio
import logging
import os
import signal
import sys
import threading
import time
from multiprocessing import Event, Process, Queue

import uvicorn

# Konfiguracja logowania
# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# logger = logging.getLogger(__name__)

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from avena_commons.event_listener import (
    Event,
    EventListener,
    EventListenerState,
    Result,
)
from avena_commons.util.logger import (
    LoggerPolicyPeriod,
    MessageLogger,
    debug,
    error,
    info,
    warning,
)


class TestClient(EventListener):
    def __init__(
        self,
        name: str,
        port: int,
        address: str,
        message_logger=None,
        debug=False,
    ):
        super().__init__(
            name=name,
            address=address,
            port=port,
            do_not_load_state=True,
            message_logger=message_logger,
        )
        self._is_running = False
        self.message_logger = message_logger
        self._server_thread = None

    async def _analyze_event(self, event: Event) -> bool:
        try:
            debug(
                f"Analyzing event: {event.event_type}",
                message_logger=self.message_logger,
            )
            event.result = Result(result="success")
            await self._reply(event)
            return True
        except Exception as e:
            error(
                f"Błąd podczas analizy eventu: {e}", message_logger=self.message_logger
            )
            return False

    async def _check_local_data(self):
        pass

    def _run_server_in_thread(self):
        """Uruchamia serwer uvicorn w osobnym wątku wewnątrz procesu."""
        info(
            f"Server thread started for port {self._EventListener__port}",
            message_logger=self.message_logger,
        )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            if hasattr(self, "server") and self.server:
                info(
                    f"Running self.server.serve() in server thread for port {self._EventListener__port}",
                    message_logger=self.message_logger,
                )
                loop.run_until_complete(self.server.serve())
            else:
                error(
                    f"Server object (self.server) not found in server thread for port {self._EventListener__port}",
                    message_logger=self.message_logger,
                )

        except asyncio.exceptions.CancelledError:
            info(
                f"Server on port {self._EventListener__port} stopped by cancellation.",
                message_logger=self.message_logger,
            )
        except Exception as e:
            error(
                f"Error in server thread on port {self._EventListener__port}: {e}",
                message_logger=self.message_logger,
            )
        finally:
            info(
                f"Server thread for port {self._EventListener__port} finishing loop.",
                message_logger=self.message_logger,
            )
            loop.close()
            asyncio.set_event_loop(None)

    def start(self):
        """Starts the client logic (including base logic) and the server in this process."""
        if self._is_running:
            warning(
                f"Klient na porcie {self._EventListener__port} już działa.",
                message_logger=self.message_logger,
            )
            return

        self._is_running = True
        info(
            f"TestClient.start() called for port {self._EventListener__port}",
            message_logger=self.message_logger,
        )

        try:
            info(
                f"Calling super().start() for port {self._EventListener__port}",
                message_logger=self.message_logger,
            )
            super().start()

            if hasattr(self, "server") and self.server:
                info(
                    f"Starting uvicorn server thread for port {self._EventListener__port}",
                    message_logger=self.message_logger,
                )
                self._server_thread = threading.Thread(
                    target=self._run_server_in_thread,
                    name=f"ServerThread-{self._EventListener__port}",
                    daemon=True,
                )
                self._server_thread.start()
                info(
                    f"Uvicorn server thread started for port {self._EventListener__port}",
                    message_logger=self.message_logger,
                )
            else:
                error(
                    f"Server object (self.server) not found after calling super().start() for port {self._EventListener__port}. Cannot start server thread.",
                    message_logger=self.message_logger,
                )

        except Exception as e:
            error(
                f"Error during TestClient.start() for port {self._EventListener__port}: {e}",
                message_logger=self.message_logger,
            )
            self._is_running = False

    def shutdown(self):
        """Zamyka klienta i jego serwer."""
        if not self._is_running:
            return

        info(
            f"Zamykanie klienta na porcie {self._EventListener__port}",
            message_logger=self.message_logger,
        )

        if hasattr(self, "server") and self.server:
            info(
                f"Signaling uvicorn server shutdown for port {self._EventListener__port}",
                message_logger=self.message_logger,
            )
            try:
                self.server.shutdown()

                if self._server_thread and self._server_thread.is_alive():
                    self._server_thread.join(timeout=1.0)

            except Exception as e:
                error(
                    f"Error while signaling server shutdown for port {self._EventListener__port}: {e}",
                    message_logger=self.message_logger,
                )

        try:
            info(
                f"Calling super().shutdown() for port {self._EventListener__port}",
                message_logger=self.message_logger,
            )
            super().shutdown()
        except Exception as e:
            error(
                f"Error during super().shutdown() for port {self._EventListener__port}: {e}",
                message_logger=self.message_logger,
            )

        self._is_running = False


# def create_clients(
#     number_of_clients: int,
#     base_port: int = 9000,
#     message_logger=None,
# ):
#     """Tworzy instancje klientów."""
#     info(
#         f"Tworzenie {number_of_clients} instancji klientów, port bazowy: {base_port}",
#         message_logger=message_logger,
#     )
#     clients = []
#     for i in range(1, number_of_clients + 1):
#         client_number = i + 1
#         port = base_port + client_number
#         message_logger_client = MessageLogger(
#             filename=f"temp/test_client_{port}.log",
#             period=LoggerPolicyPeriod.LAST_15_MINUTES,
#         )
#         client = TestClient(
#             name=f"test_{port}",
#             port=port,
#             address="127.0.0.1",
#             message_logger=message_logger_client,
#             debug=True,
#         )
#         clients.append(client)
#         debug(
#             f"Utworzono instancję klienta {client_number} na porcie {port}",
#             message_logger=message_logger,
#         )
#     return clients


def shutdown_client(client):
    """Funkcja pomocnicza do zamykania instancji klienta."""
    info(
        f"Attempting shutdown for client instance {client.name} in main process (old handler)",
        message_logger=client.message_logger,
    )
    try:
        pass

    except Exception as e:
        error(
            f"Error during shutdown_client (old handler) for {client._EventListener__port}: {e}"
        )


def signal_handler_processes(signum, frame, main_logger):
    info(
        "Otrzymano sygnał zamknięcia w głównym procesie. Rozpoczynanie sekwencji zamykania procesów klientów...",
        message_logger=main_logger,
    )
    for proc in client_processes:
        if proc.is_alive():
            info(
                f"Terminowanie procesu {proc.name} (PID: {proc.pid})...",
                message_logger=main_logger,
            )
            try:
                proc.terminate()
            except Exception as e:
                error(
                    f"Error terminating process {proc.name} (PID: {proc.pid}): {e}",
                    message_logger=main_logger,
                )

    timeout = 5.0
    info(
        f"Oczekiwanie na zakończenie procesów (max {timeout}s)...",
        message_logger=main_logger,
    )
    for proc in client_processes:
        if proc.is_alive():
            proc.join(timeout=timeout)

        if proc.is_alive():
            error(
                f"Proces {proc.name} (PID: {proc.pid}) nie zakończył się po timeout, killowanie...",
                message_logger=main_logger,
            )
            try:
                proc.kill()
            except Exception as e:
                error(
                    f"Error killing process {proc.name} (PID: {proc.pid}): {e}",
                    message_logger=main_logger,
                )

    info("Wszystkie procesy klientów zakończone.", message_logger=main_logger)
    sys.exit(0)


def run_client_process(name, port, address, debug_mode):
    """Target function for client process."""
    process_logger = None
    try:
        temp_path = os.path.abspath("temp")
        os.makedirs(temp_path, exist_ok=True)

        info(
            f"Client process started for port {port} (PID: {os.getpid()}). Using process-specific logger.",
            message_logger=process_logger,
        )
        client_message_logger = MessageLogger(
            filename=f"temp/test_client_{port}.log",
            period=LoggerPolicyPeriod.LAST_15_MINUTES,
        )

        client = TestClient(
            name=name,
            port=port,
            address=address,
            message_logger=client_message_logger,
            debug=debug_mode,
        )

        client.start()
        info(
            f"Client {client.name} start method finished. Process {os.getpid()} is running main loop.",
            message_logger=process_logger,
        )

        while client._is_running:
            time.sleep(0.1)

        info(
            f"Client process for port {port} (PID: {os.getpid()}) finishing due to _is_running becoming False.",
            message_logger=process_logger,
        )

    except Exception as e:
        if process_logger:
            error(
                f"Error in client process for port {port} (PID: {os.getpid()}): {e}",
                message_logger=process_logger,
            )
        else:
            print(
                f"Error in client process for port {port} (PID: {os.getpid()}): {e}",
                file=sys.stderr,
            )
    finally:
        if process_logger:
            info(
                f"Client process {os.getpid()} finally block for port {port}.",
                message_logger=process_logger,
            )
            try:
                if "client" in locals():
                    if client._is_running:
                        info(
                            f"Client process {os.getpid()} attempting client.shutdown() in finally block for port {port}.",
                            message_logger=process_logger,
                        )
                        client.shutdown()
            except Exception as e:
                error(
                    f"Error during client shutdown in finally block for port {port} (PID: {os.getpid()}): {e}",
                    message_logger=process_logger,
                )
        else:
            print(
                f"Client process {os.getpid()} finally block for port {port} (logger not available).",
                file=sys.stderr,
            )


if __name__ == "__main__":
    import multiprocessing

    if multiprocessing.get_start_method(allow_none=True) is None:
        multiprocessing.set_start_method("spawn", force=True)

    parser = argparse.ArgumentParser(description="test")
    parser.add_argument(
        "-c",
        "--clients",
        type=int,
        default=10,
        help="test clients number (default: 10)",
    )
    # parser.add_argument(
    #     "-s",
    #     "--session",
    #     action="store_false",
    #     help="use http session (default: False)",
    # )
    # parser.add_argument(
    #     "-p",
    #     "--parallel",
    #     action="store_false",
    #     help="use parallel send (default: False)",
    # )

    args = parser.parse_args()

    temp_path = os.path.abspath("temp")
    os.makedirs(temp_path, exist_ok=True)

    message_logger = MessageLogger(
        filename=f"{temp_path}/test_client.log",
        period=LoggerPolicyPeriod.LAST_15_MINUTES,
    )

    base_port = 9000

    client_processes = []

    clients_params = []
    for i in range(1, args.clients + 1):
        client_number = i + 1
        port = base_port + client_number
        clients_params.append({
            "name": f"test_{port}",
            "port": port,
            "address": "127.0.0.1",
            "debug_mode": True,
        })

    try:
        info(
            f"Uruchamianie programu testowego z {args.clients} klientami w oddzielnych procesach (główny proces PID: {os.getpid()})",
            message_logger=message_logger,
        )

        signal.signal(
            signal.SIGINT,
            lambda s, f: signal_handler_processes(s, f, message_logger),
        )
        signal.signal(
            signal.SIGTERM,
            lambda s, f: signal_handler_processes(s, f, message_logger),
        )

        info(
            f"Uruchamianie {len(clients_params)} procesów klientów...",
            message_logger=message_logger,
        )
        for client_params in clients_params:
            process = Process(
                target=run_client_process,
                args=(
                    client_params["name"],
                    client_params["port"],
                    client_params["address"],
                    client_params["debug_mode"],
                ),
                name=f"ClientProcess-{client_params['port']}",
            )
            client_processes.append(process)
            process.start()
            info(
                f"Proces klienta dla portu {client_params['port']} uruchomiony (PID: {process.pid}).",
                message_logger=message_logger,
            )
            time.sleep(0.5)

        info(
            "Wszyscy procesy klientów uruchomione. Oczekiwanie na sygnał zamknięcia (Ctrl+C)...",
            message_logger=message_logger,
        )
        while True:
            living_processes = []
            for proc in client_processes:
                if proc.is_alive():
                    living_processes.append(proc)
                else:
                    error(
                        f"Client process {proc.name} (PID: {proc.pid}) zakończył się nieoczekiwanie (Exit Code: {proc.exitcode}).",
                        message_logger=message_logger,
                    )

            client_processes = living_processes

            if not client_processes:
                info(
                    "Wszystkie procesy klientów zakończyły się, lub żaden nie został uruchomiony.",
                    message_logger=message_logger,
                )
                break

            time.sleep(1)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        error(
            f"Nieoczekiwany błąd w głównym wątku: {e}",
            message_logger=message_logger,
        )
        signal_handler_processes(signal.SIGTERM, None, message_logger)
    finally:
        info("Program zakończony.", message_logger=message_logger)
