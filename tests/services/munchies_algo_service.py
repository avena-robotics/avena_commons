"""
Testowa usługa MunchiesAlgo - symuluje główną logikę biznesową systemu.
"""

import asyncio
import random
from typing import Optional

from base_test_service import BaseTestService

from avena_commons.util.logger import MessageLogger, info


class MunchiesAlgoService(BaseTestService):
    """
    Testowa usługa MunchiesAlgo symulująca główną logikę biznesową.

    Port: 8004
    Grupa: main_logic

    Symuluje:
    - Algorytm planowania zadań
    - Zarządzanie kolejką zamówień
    - Optymalizację ścieżek robotów
    - Monitorowanie wydajności systemu
    """

    def __init__(
        self,
        address: str = "127.0.0.1",
        port: int = 8004,
        message_logger: Optional[MessageLogger] = None,
    ):
        """
        Inicjalizuje usługę MunchiesAlgo.

        Args:
            address: Adres IP serwera
            port: Port serwera (domyślnie 8004)
            message_logger: Logger wiadomości
        """
        super().__init__(
            name="munchies_algo",
            port=port,
            address=address,
            message_logger=message_logger,
            initialization_time=4.0,  # Logika biznesowa potrzebuje najwięcej czasu
            shutdown_time=2.5,
        )

        # Symulowany stan systemu biznesowego
        self._business_state = {
            "orders_queue": [],
            "active_orders": [],
            "completed_orders": 0,
            "optimization_algorithm": "idle",
            "performance_metrics": {
                "throughput": 0,
                "efficiency": 0.0,
                "avg_completion_time": 0.0,
            },
            "connected_supervisors": [],
            "system_capacity": 100,  # procent maksymalnej wydajności
        }

        self._order_counter = 0
        self._algorithm_cycles = 0

    async def on_initializing(self):
        """Symuluje inicjalizację głównej logiki biznesowej."""
        info(
            f"{self._service_name}: Rozpoczynam inicjalizację głównej logiki biznesowej...",
            message_logger=self._message_logger,
        )

        # Symuluj ładowanie algorytmów
        info(
            f"{self._service_name}: Ładowanie algorytmów planowania...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(1.0)

        # Symuluj inicjalizację bazy danych
        info(
            f"{self._service_name}: Połączenie z bazą danych zamówień...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(1.0)

        # Symuluj ładowanie konfiguracji
        info(
            f"{self._service_name}: Ładowanie konfiguracji produkcji...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(0.5)

        # Symuluj test komunikacji z supervisorami
        info(
            f"{self._service_name}: Test komunikacji z supervisorami...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(1.0)
        self._business_state["connected_supervisors"] = ["supervisor_1", "supervisor_2"]

        # Symuluj inicjalizację systemu monitoringu
        info(
            f"{self._service_name}: Inicjalizacja systemu monitoringu wydajności...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(0.5)

        # Wywołaj bazową implementację (automatyczne przejście do INITIALIZED)
        await super().on_initializing()

    async def _simulate_work(self):
        """Symuluje pracę głównej logiki biznesowej w stanie STARTED."""
        self._algorithm_cycles += 1

        # Symuluj otrzymywanie nowych zamówień
        if random.random() < 0.3:  # 30% szansy na nowe zamówienie
            await self._generate_new_order()

        # Symuluj przetwarzanie kolejki zamówień
        if self._business_state["orders_queue"]:
            await self._process_orders_queue()

        # Symuluj optymalizację ścieżek
        if self._algorithm_cycles % 5 == 0:  # Co 5 cykli
            await self._run_path_optimization()

        # Symuluj aktualizację metryk wydajności
        if self._algorithm_cycles % 10 == 0:  # Co 10 cykli
            await self._update_performance_metrics()

        # Krótkie opóźnienie między cyklami algorytmu
        await asyncio.sleep(0.5)

    async def _generate_new_order(self):
        """Symuluje otrzymanie nowego zamówienia."""
        self._order_counter += 1

        new_order = {
            "id": f"ORD_{self._order_counter:04d}",
            "items": [
                f"item_{random.randint(1, 10)}" for _ in range(random.randint(1, 5))
            ],
            "priority": random.choice(["low", "normal", "high", "urgent"]),
            "estimated_time": random.randint(30, 300),  # sekundy
            "created_at": self._algorithm_cycles,
        }

        self._business_state["orders_queue"].append(new_order)

        info(
            f"{self._service_name}: Nowe zamówienie {new_order['id']} ({new_order['priority']}) - kolejka: {len(self._business_state['orders_queue'])}",
            message_logger=self._message_logger,
        )

    async def _process_orders_queue(self):
        """Symuluje przetwarzanie kolejki zamówień."""
        # Sortuj zamówienia według priorytetu
        priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
        self._business_state["orders_queue"].sort(
            key=lambda x: priority_order.get(x["priority"], 4)
        )

        # Przenieś zamówienia do aktywnej kolejki jeśli jest miejsce
        max_active = 3  # Maksymalnie 3 aktywne zamówienia
        while (
            len(self._business_state["active_orders"]) < max_active
            and self._business_state["orders_queue"]
        ):
            order = self._business_state["orders_queue"].pop(0)
            order["started_at"] = self._algorithm_cycles
            self._business_state["active_orders"].append(order)

            info(
                f"{self._service_name}: Rozpoczęto przetwarzanie zamówienia {order['id']}",
                message_logger=self._message_logger,
            )

        # Symuluj postęp aktywnych zamówień
        completed_orders = []
        for order in self._business_state["active_orders"]:
            progress = self._algorithm_cycles - order["started_at"]
            if progress >= order["estimated_time"] / 10:  # Przyspieszony dla symulacji
                completed_orders.append(order)

        # Usuń ukończone zamówienia
        for order in completed_orders:
            self._business_state["active_orders"].remove(order)
            self._business_state["completed_orders"] += 1

            info(
                f"{self._service_name}: Ukończono zamówienie {order['id']} - łącznie: {self._business_state['completed_orders']}",
                message_logger=self._message_logger,
            )

    async def _run_path_optimization(self):
        """Symuluje algorytm optymalizacji ścieżek."""
        if self._business_state["active_orders"]:
            self._business_state["optimization_algorithm"] = "running"

            info(
                f"{self._service_name}: Uruchamiam optymalizację ścieżek dla {len(self._business_state['active_orders'])} zamówień...",
                message_logger=self._message_logger,
            )

            # Symuluj czas obliczeń optymalizacji
            await asyncio.sleep(0.2)

            self._business_state["optimization_algorithm"] = "idle"

            # Symuluj poprawę wydajności po optymalizacji
            current_efficiency = self._business_state["performance_metrics"][
                "efficiency"
            ]
            optimization_boost = random.uniform(0.95, 1.05)  # ±5% zmiana
            new_efficiency = min(100.0, current_efficiency * optimization_boost)
            self._business_state["performance_metrics"]["efficiency"] = new_efficiency

    async def _update_performance_metrics(self):
        """Symuluje aktualizację metryk wydajności systemu."""
        metrics = self._business_state["performance_metrics"]

        # Symuluj throughput (zamówień na minutę)
        if self._algorithm_cycles > 0:
            metrics["throughput"] = (
                self._business_state["completed_orders"] * 60
            ) / self._algorithm_cycles

        # Symuluj efficiency (0-100%)
        active_ratio = len(self._business_state["active_orders"]) / 3  # Max 3 aktywne
        queue_penalty = min(
            len(self._business_state["orders_queue"]) * 0.1, 0.5
        )  # Kara za długą kolejkę
        metrics["efficiency"] = max(0, (active_ratio * 100) - (queue_penalty * 100))

        # Symuluj średni czas ukończenia
        if self._business_state["completed_orders"] > 0:
            metrics["avg_completion_time"] = random.uniform(45, 120)  # 45-120 sekund

        info(
            f"{self._service_name}: Metryki - throughput: {metrics['throughput']:.1f}/min, efficiency: {metrics['efficiency']:.1f}%",
            message_logger=self._message_logger,
        )

    async def on_stopping(self):
        """Symuluje graceful shutdown głównej logiki biznesowej."""
        info(
            f"{self._service_name}: Rozpoczynam bezpieczne zatrzymanie logiki biznesowej...",
            message_logger=self._message_logger,
        )

        # Zatrzymaj przyjmowanie nowych zamówień
        info(
            f"{self._service_name}: Zatrzymuję przyjmowanie nowych zamówień...",
            message_logger=self._message_logger,
        )
        await asyncio.sleep(0.5)

        # Dokończ aktywne zamówienia
        if self._business_state["active_orders"]:
            info(
                f"{self._service_name}: Kończę przetwarzanie {len(self._business_state['active_orders'])} aktywnych zamówień...",
                message_logger=self._message_logger,
            )

            # Symuluj szybkie kończenie aktywnych zamówień
            while self._business_state["active_orders"]:
                order = self._business_state["active_orders"].pop(0)
                self._business_state["completed_orders"] += 1
                info(
                    f"{self._service_name}: Ekspresowo ukończono zamówienie {order['id']}",
                    message_logger=self._message_logger,
                )
                await asyncio.sleep(0.2)

        # Zapisz stan kolejki dla późniejszego wznowienia
        pending_orders = len(self._business_state["orders_queue"])
        if pending_orders > 0:
            info(
                f"{self._service_name}: Zapisuję {pending_orders} oczekujących zamówień dla późniejszego wznowienia...",
                message_logger=self._message_logger,
            )
            await asyncio.sleep(0.5)

        # Rozłącz z supervisorami
        info(
            f"{self._service_name}: Rozłączanie z supervisorami...",
            message_logger=self._message_logger,
        )
        self._business_state["connected_supervisors"] = []
        await asyncio.sleep(0.5)

        info(
            f"{self._service_name}: Logika biznesowa bezpiecznie zatrzymana. Ukończono łącznie: {self._business_state['completed_orders']} zamówień",
            message_logger=self._message_logger,
        )

        # Wywołaj bazową implementację
        await super().on_stopping()

    def get_service_info(self) -> dict:
        """Zwraca informacje o usłudze MunchiesAlgo."""
        base_info = super().get_service_info()
        base_info.update({
            "group": "main_logic",
            "business_state": self._business_state,
            "algorithm_cycles": self._algorithm_cycles,
            "order_counter": self._order_counter,
        })
        return base_info


def main():
    """Uruchamia testową usługę MunchiesAlgo."""
    import os
    import sys

    # Dodaj ścieżkę do modułów avena_commons
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    sys.path.insert(0, os.path.join(project_root, "src"))

    from avena_commons.util.logger import MessageLogger

    # Utwórz logger
    logger = MessageLogger(filename="temp/munchies_algo_service.log", debug=True)

    # Utwórz i uruchom usługę
    service = MunchiesAlgoService(message_logger=logger)

    try:
        info(
            "Uruchamianie testowej usługi MunchiesAlgo na porcie 8004...",
            message_logger=logger,
        )
        service.start()
    except KeyboardInterrupt:
        info(
            "Otrzymano sygnał przerwania - zatrzymywanie MunchiesAlgo...",
            message_logger=logger,
        )
        service.shutdown()


if __name__ == "__main__":
    main()
