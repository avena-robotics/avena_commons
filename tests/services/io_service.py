"""
Testowa usługa IO - symuluje warstwę I/O systemu.
"""

import asyncio
import os
import sys
from typing import Optional

sys.path.append(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src")
)
from base_test_service import BaseTestService

from avena_commons.util.logger import MessageLogger, info


class IoService(BaseTestService):
    """
    Testowa usługa IO symulująca warstwę I/O systemu.

    Port: 8001
    Grupa: base_io

    Symuluje:
    - Inicjalizację połączeń z urządzeniami
    - Podstawowe operacje I/O
    - Monitoring stanu sprzętu
    """

    def __init__(
        self,
        address: str = "127.0.0.1",
        port: int = 8001,
        message_logger: Optional[MessageLogger] = None,
    ):
        """
        Inicjalizuje usługę IO.

        Args:
            address: Adres IP serwera
            port: Port serwera (domyślnie 8001)
            message_logger: Logger wiadomości
        """
        super().__init__(
            name="io",
            port=port,
            address=address,
            message_logger=message_logger,
            initialization_time=3.0,  # IO potrzebuje więcej czasu na inicjalizację
            shutdown_time=2.0,
        )

        # Symulowane urządzenia I/O
        self._devices = {
            "sensor_1": {"status": "disconnected", "value": 0},
            "sensor_2": {"status": "disconnected", "value": 0},
            "actuator_1": {"status": "disconnected", "position": 0},
            "relay_bank": {"status": "disconnected", "state": [False] * 8},
        }

        self._io_operations_count = 0

    async def on_initializing(self):
        """Symuluje inicjalizację warstwy I/O."""
        info(
            f"{self._service_name}: Rozpoczynam inicjalizację warstwy I/O...",
            message_logger=self._message_logger,
        )

        # Symuluj podłączanie do urządzeń
        for device_name in self._devices:
            info(
                f"{self._service_name}: Łączenie z urządzeniem {device_name}...",
                message_logger=self._message_logger,
            )
            # await asyncio.sleep(0.5)  # Symulacja czasu połączenia
            self._devices[device_name]["status"] = "connected"

        # Wywołaj bazową implementację (automatyczne przejście do INITIALIZED)
        await super().on_initializing()

    async def check_local_data(self):
        """Symuluje pracę warstwy I/O w stanie STARTED."""
        # Symuluj cykliczne operacje I/O
        self._io_operations_count += 1

        # Co 10 operacji loguj status
        if self._io_operations_count % 10 == 0:
            info(
                f"{self._service_name}: Wykonano {self._io_operations_count} operacji I/O",
                message_logger=self._message_logger,
            )

        # Symuluj czytanie sensorów
        self._devices["sensor_1"]["value"] = self._io_operations_count % 100
        self._devices["sensor_2"]["value"] = (self._io_operations_count % 50) * 2

        # Krótkie opóźnienie między operacjami
        # await asyncio.sleep(0.1)

    async def on_stopping(self):
        """Symuluje graceful shutdown warstwy I/O."""
        info(
            f"{self._service_name}: Rozłączanie urządzeń I/O...",
            message_logger=self._message_logger,
        )

        # Symuluj bezpieczne rozłączenie urządzeń
        for device_name in self._devices:
            info(
                f"{self._service_name}: Rozłączanie urządzenia {device_name}...",
                message_logger=self._message_logger,
            )
            self._devices[device_name]["status"] = "disconnected"
            await asyncio.sleep(0.3)

        info(
            f"{self._service_name}: Wszystkie urządzenia I/O bezpiecznie rozłączone",
            message_logger=self._message_logger,
        )

        # Wywołaj bazową implementację
        await super().on_stopping()

    def get_service_info(self) -> dict:
        """Zwraca informacje o usłudze IO."""
        base_info = super().get_service_info()
        base_info.update({
            "group": "base_io",
            "devices": self._devices,
            "io_operations_count": self._io_operations_count,
        })
        return base_info


def main():
    """Uruchamia testową usługę IO."""
    import os
    import sys

    # Dodaj ścieżkę do modułów avena_commons
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    sys.path.insert(0, os.path.join(project_root, "src"))

    # Utwórz logger
    logger = MessageLogger(filename="temp/test_io_service.log", debug=True)

    # Utwórz i uruchom usługę
    service = IoService(message_logger=logger)

    try:
        info("Uruchamianie testowej usługi IO na porcie 8001...", message_logger=logger)
        service.start()
    except KeyboardInterrupt:
        info(
            "Otrzymano sygnał przerwania - zatrzymywanie usługi...",
            message_logger=logger,
        )
        service.shutdown()


if __name__ == "__main__":
    main()
