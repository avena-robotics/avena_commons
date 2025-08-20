"""
Testowa usługa Supervisor - symuluje komponenty nadzorujące roboty.
"""

import asyncio
import random
from typing import Optional

from base_test_service import BaseTestService

from avena_commons.util.logger import MessageLogger, info, warning


class SupervisorService(BaseTestService):
    """
    Testowa usługa Supervisor symulująca komponenty nadzorujące roboty.

    Porty: 8002 (supervisor_1), 8003 (supervisor_2)
    Grupa: supervisors

    Symuluje:
    - Kontrolę robotów przemysłowych
    - Monitoring pozycji i statusu
    - Wykonywanie zadań ruchu
    - Bezpieczne zatrzymanie w pozycji domowej
    """

    def __init__(
        self,
        supervisor_id: int = 1,
        address: str = "127.0.0.1",
        message_logger: Optional[MessageLogger] = None,
    ):
        """
        Inicjalizuje usługę Supervisor.

        Args:
            supervisor_id: ID supervisora (1 lub 2)
            address: Adres IP serwera
            message_logger: Logger wiadomości
        """
        self._supervisor_id = supervisor_id
        port = 8001 + supervisor_id  # 8002 dla supervisor_1, 8003 dla supervisor_2

        super().__init__(
            name=f"supervisor_{supervisor_id}",
            port=port,
            address=address,
            message_logger=message_logger,
            initialization_time=2.5,  # Supervisory potrzebują średnio dużo czasu
            shutdown_time=3.0,  # Więcej czasu na bezpieczne zatrzymanie robotów
        )

        # Symulowany stan robota
        self._robot_state = {
            "connection": "disconnected",
            "position": {"x": 0, "y": 0, "z": 0, "rx": 0, "ry": 0, "rz": 0},
            "home_position": {"x": 300, "y": 0, "z": 400, "rx": 0, "ry": 0, "rz": 180},
            "target_position": None,
            "is_moving": False,
            "speed": 50,  # procent maksymalnej prędkości
            "payload": 0,  # kg
            "status": "idle",
            "safety_limits": True,
            "emergency_stop": False,
        }

        self._tasks_completed = 0
        self._movement_simulation_active = False

    async def on_initializing(self):
        """Symuluje inicjalizację supervisora robota."""
        info(
            f"{self._service_name}: Rozpoczynam inicjalizację supervisora robota {self._supervisor_id}...",
            message_logger=self._message_logger,
        )

        # Symuluj podłączenie do robota
        info(
            f"{self._service_name}: Łączenie z robotem przemysłowym...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(1.0)
        self._robot_state["connection"] = "connected"

        # Symuluj kalibrację
        info(
            f"{self._service_name}: Wykonuję kalibrację osi robota...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(1.0)

        # Symuluj test bezpieczeństwa
        info(
            f"{self._service_name}: Test systemów bezpieczeństwa...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(0.5)

        # Wywołaj bazową implementację (automatyczne przejście do INITIALIZED)
        await super().on_initializing()

    async def on_starting(self):
        """Przejście INITIALIZED → STARTED z włączeniem symulacji ruchu."""
        info(
            f"{self._service_name}: Włączam napędy robota i systemy kontroli...",
            message_logger=self._message_logger,
        )

        # Włącz symulację ruchu
        self._movement_simulation_active = True

        # Wywołaj bazową implementację
        await super().on_starting()

    async def _simulate_work(self):
        """Symuluje pracę supervisora w stanie STARTED."""
        # Symuluj wykonywanie zadań robotycznych
        if random.random() < 0.1:  # 10% szansy na nowe zadanie
            await self._simulate_robot_task()

        # Symuluj monitoring robota
        if self._movement_simulation_active:
            await self._simulate_robot_movement()

        # Krótkie opóźnienie
        await asyncio.sleep(0.2)

    async def _simulate_robot_task(self):
        """Symuluje wykonanie zadania robotycznego."""
        if (
            not self._robot_state["is_moving"]
            and not self._robot_state["emergency_stop"]
        ):
            # Generuj losową pozycję docelową
            target = {
                "x": random.randint(-500, 500),
                "y": random.randint(-300, 300),
                "z": random.randint(50, 600),
                "rx": random.randint(-180, 180),
                "ry": random.randint(-90, 90),
                "rz": random.randint(-180, 180),
            }

            self._robot_state["target_position"] = target
            self._robot_state["is_moving"] = True
            self._robot_state["status"] = "moving_to_target"

            info(
                f"{self._service_name}: Robot rozpoczyna ruch do pozycji {target}",
                message_logger=self._message_logger,
            )

    async def _simulate_robot_movement(self):
        """Symuluje płynny ruch robota do pozycji docelowej."""
        if self._robot_state["is_moving"] and self._robot_state["target_position"]:
            current = self._robot_state["position"]
            target = self._robot_state["target_position"]

            # Oblicz różnicę i ruch krokowy
            step_size = 0.1  # Procent ruchu na krok
            moved = False

            for axis in ["x", "y", "z", "rx", "ry", "rz"]:
                diff = target[axis] - current[axis]
                if abs(diff) > 1:  # Tolerancja 1 jednostka
                    current[axis] += diff * step_size
                    moved = True

            # Sprawdź czy robot dotarł do celu
            if not moved:
                self._robot_state["is_moving"] = False
                self._robot_state["target_position"] = None
                self._robot_state["status"] = "idle"
                self._tasks_completed += 1

                info(
                    f"{self._service_name}: Robot dotarł do pozycji docelowej. Zadania wykonane: {self._tasks_completed}",
                    message_logger=self._message_logger,
                )

    async def on_stopping(self):
        """Symuluje graceful shutdown supervisora z bezpiecznym zatrzymaniem robota."""
        info(
            f"{self._service_name}: Rozpoczynam bezpieczne zatrzymanie robota {self._supervisor_id}...",
            message_logger=self._message_logger,
        )

        # Zatrzymaj przyjmowanie nowych zadań
        self._movement_simulation_active = False

        # Przerwij aktualny ruch i jedź do pozycji domowej
        if self._robot_state["is_moving"]:
            warning(
                f"{self._service_name}: Przerywam aktualny ruch robota...",
                message_logger=self._message_logger,
            )
            self._robot_state["is_moving"] = False
            await asyncio.sleep(0.5)

        # Jedź do pozycji domowej
        info(
            f"{self._service_name}: Robot wraca do pozycji domowej...",
            message_logger=self._message_logger,
        )
        self._robot_state["target_position"] = self._robot_state["home_position"].copy()
        self._robot_state["is_moving"] = True
        self._robot_state["status"] = "returning_home"

        # Symuluj powrót do domu (szybszy niż normalny ruch)
        while self._robot_state["is_moving"]:
            current = self._robot_state["position"]
            target = self._robot_state["target_position"]
            step_size = 0.3  # Szybszy powrót
            moved = False

            for axis in ["x", "y", "z", "rx", "ry", "rz"]:
                diff = target[axis] - current[axis]
                if abs(diff) > 1:
                    current[axis] += diff * step_size
                    moved = True

            if not moved:
                self._robot_state["is_moving"] = False
                self._robot_state["status"] = "at_home"
                break

            await asyncio.sleep(0.1)

        info(
            f"{self._service_name}: Robot w pozycji domowej - wyłączam napędy...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(1.0)

        # Rozłącz robota
        info(
            f"{self._service_name}: Rozłączanie robota...",
            message_logger=self._message_logger,
        )
        self._robot_state["connection"] = "disconnected"
        self._robot_state["status"] = "disconnected"

        # Wywołaj bazową implementację
        await super().on_stopping()

    def get_service_info(self) -> dict:
        """Zwraca informacje o usłudze Supervisor."""
        base_info = super().get_service_info()
        base_info.update({
            "group": "supervisors",
            "supervisor_id": self._supervisor_id,
            "robot_state": self._robot_state,
            "tasks_completed": self._tasks_completed,
        })
        return base_info


def main():
    """Uruchamia testową usługę Supervisor."""
    import os
    import sys

    # Dodaj ścieżkę do modułów avena_commons
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    sys.path.insert(0, os.path.join(project_root, "src"))

    from avena_commons.util.logger import MessageLogger

    # Sprawdź argumenty wiersza poleceń dla ID supervisora
    supervisor_id = 1
    if len(sys.argv) > 1:
        try:
            supervisor_id = int(sys.argv[1])
        except ValueError:
            print("Użycie: python supervisor_service.py [1|2]")
            sys.exit(1)

    if supervisor_id not in [1, 2]:
        print("ID supervisora musi być 1 lub 2")
        sys.exit(1)

    # Utwórz logger
    logger = MessageLogger(
        filename=f"temp/supervisor_{supervisor_id}_service.log", debug=True
    )

    # Utwórz i uruchom usługę
    service = SupervisorService(supervisor_id=supervisor_id, message_logger=logger)

    try:
        port = 8001 + supervisor_id
        info(
            f"Uruchamianie testowej usługi Supervisor {supervisor_id} na porcie {port}...",
            message_logger=logger,
        )
        service.start()
    except KeyboardInterrupt:
        info(
            f"Otrzymano sygnał przerwania - zatrzymywanie supervisora {supervisor_id}...",
            message_logger=logger,
        )
        service.shutdown()


if __name__ == "__main__":
    main()
