#!/usr/bin/env python3
"""
Test pełnego scenariusza startowego z rzeczywistymi testowymi usługami.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

import aiohttp

# Dodaj ścieżkę do modułów avena_commons
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from avena_commons.util.logger import MessageLogger


class ScenarioTester:
    """Klasa do testowania scenariuszy Orchestratora z rzeczywistymi usługami."""

    def __init__(self):
        self.services = {
            "orchestrator": {"address": "127.0.0.1", "port": 8000},
            "io": {"address": "127.0.0.1", "port": 8001},
            "supervisor_1": {"address": "127.0.0.1", "port": 8002},
            "supervisor_2": {"address": "127.0.0.1", "port": 8003},
            "munchies_algo": {"address": "127.0.0.1", "port": 8004},
        }

        # Utwórz logger
        self.logger = MessageLogger(filename="scenario_test.log", debug=True)

    async def check_service_status(self, service_name: str) -> dict:
        """
        Sprawdza status pojedynczej usługi.

        Args:
            service_name: Nazwa usługi

        Returns:
            Słownik ze statusem usługi
        """
        service_config = self.services.get(service_name)
        if not service_config:
            return {"status": "unknown", "error": "Service not configured"}

        url = f"http://{service_config['address']}:{service_config['port']}/event"

        # Przygotuj event CMD_GET_STATE
        event_data = {
            "source": "scenario_tester",
            "source_address": "127.0.0.1",
            "source_port": 9999,
            "destination": service_name,
            "destination_address": service_config["address"],
            "destination_port": service_config["port"],
            "event_type": "CMD_GET_STATE",
            "data": {},
            "to_be_processed": True,
            "maximum_processing_time": 10.0,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, json=event_data, timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        return {"status": "online", "data": result}
                    else:
                        return {"status": "error", "error": f"HTTP {response.status}"}

        except aiohttp.ClientConnectorError:
            return {"status": "offline", "error": "Connection refused"}
        except asyncio.TimeoutError:
            return {"status": "timeout", "error": "Request timeout"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def check_all_services(self) -> dict:
        """
        Sprawdza status wszystkich usług.

        Returns:
            Słownik ze statusami wszystkich usług
        """
        print("🔍 Sprawdzanie statusu wszystkich usług...")

        results = {}
        for service_name in self.services:
            status = await self.check_service_status(service_name)
            results[service_name] = status

            if status["status"] == "online":
                fsm_state = "UNKNOWN"
                if "data" in status and isinstance(status["data"], dict):
                    fsm_state = status["data"].get("fsm_state", "UNKNOWN")
                print(f"   ✅ {service_name:<15} - ONLINE  (stan: {fsm_state})")
            elif status["status"] == "offline":
                print(f"   ❌ {service_name:<15} - OFFLINE")
            else:
                print(
                    f"   ⚠️  {service_name:<15} - {status['status'].upper()} ({status.get('error', 'Unknown error')})"
                )

        return results

    async def trigger_startup_scenario(self) -> bool:
        """
        Uruchamia scenariusz startowy przez Orchestrator.

        Returns:
            True jeśli scenariusz wykonał się pomyślnie
        """
        print("\n🚀 Uruchamianie scenariusza startowego...")

        orchestrator_config = self.services["orchestrator"]
        url = f"http://{orchestrator_config['address']}:{orchestrator_config['port']}/event"

        # Przygotuj event EXECUTE_SCENARIO
        event_data = {
            "source": "scenario_tester",
            "source_address": "127.0.0.1",
            "source_port": 9999,
            "destination": "orchestrator",
            "destination_address": orchestrator_config["address"],
            "destination_port": orchestrator_config["port"],
            "event_type": "EXECUTE_SCENARIO",
            "data": {"scenario_name": "Scenariusz startowy systemu - STOPPED do RUN"},
            "to_be_processed": True,
            "maximum_processing_time": 180.0,  # 3 minuty na scenariusz
        }

        try:
            async with aiohttp.ClientSession() as session:
                print(f"   📤 Wysyłanie żądania wykonania scenariusza...")

                async with session.post(
                    url, json=event_data, timeout=aiohttp.ClientTimeout(total=200)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"   ✅ Scenariusz wysłany pomyślnie")
                        print(f"   📋 Odpowiedź: {json.dumps(result, indent=2)}")
                        return True
                    else:
                        error_text = await response.text()
                        print(f"   ❌ Błąd HTTP {response.status}: {error_text}")
                        return False

        except aiohttp.ClientConnectorError:
            print(f"   ❌ Nie można połączyć się z Orchestratorem!")
            return False
        except asyncio.TimeoutError:
            print(f"   ⏱️  Timeout wykonania scenariusza (może trwać dłużej)")
            return False
        except Exception as e:
            print(f"   ❌ Błąd: {e}")
            return False

    async def monitor_scenario_progress(self, duration: int = 60) -> dict:
        """
        Monitoruje postęp scenariusza przez określony czas.

        Args:
            duration: Czas monitorowania w sekundach

        Returns:
            Końcowy status wszystkich usług
        """
        print(f"\n📊 Monitorowanie postępu scenariusza przez {duration} sekund...")

        start_time = time.time()
        check_interval = 5  # Sprawdzaj co 5 sekund

        last_states = {}

        while time.time() - start_time < duration:
            print(
                f"\n   🕐 {int(time.time() - start_time)}s - Sprawdzanie statusu usług..."
            )

            current_states = {}
            all_services_ready = True

            # Sprawdź tylko usługi komponenty (nie Orchestrator)
            for service_name in ["io", "supervisor_1", "supervisor_2", "munchies_algo"]:
                status = await self.check_service_status(service_name)

                if status["status"] == "online" and "data" in status:
                    fsm_state = status["data"].get("fsm_state", "UNKNOWN")
                    current_states[service_name] = fsm_state

                    # Sprawdź czy stan się zmienił
                    if (
                        service_name in last_states
                        and last_states[service_name] != fsm_state
                    ):
                        print(
                            f"   🔄 {service_name}: {last_states[service_name]} → {fsm_state}"
                        )
                    elif service_name not in last_states:
                        print(f"   📍 {service_name}: {fsm_state}")

                    # Sprawdź czy wszystkie usługi są w stanie RUN/STARTED
                    if fsm_state not in ["RUN", "STARTED"]:
                        all_services_ready = False
                else:
                    current_states[service_name] = "OFFLINE"
                    all_services_ready = False
                    print(f"   ❌ {service_name}: OFFLINE")

            last_states = current_states

            # Jeśli wszystkie usługi są w stanie RUN/STARTED, scenario zakończone pomyślnie
            if all_services_ready:
                print(f"\n   🎉 Wszystkie usługi osiągnęły stan operacyjny!")
                break

            # Czekaj przed następnym sprawdzeniem
            await asyncio.sleep(check_interval)

        return last_states

    async def run_full_test(self):
        """Uruchamia pełny test scenariusza."""
        print("=" * 80)
        print("🧪 TEST PEŁNEGO SCENARIUSZA STARTOWEGO")
        print("=" * 80)

        # Sprawdź status początkowy
        initial_status = await self.check_all_services()

        # Sprawdź czy wszystkie usługi są dostępne
        offline_services = [
            name
            for name, status in initial_status.items()
            if status["status"] == "offline"
        ]
        if offline_services:
            print(f"\n❌ Następujące usługi są niedostępne: {offline_services}")
            print("   Upewnij się, że wszystkie usługi są uruchomione!")
            print("   Użyj: python tests/services/run_all_services.py")
            return False

        # Sprawdź czy Orchestrator jest dostępny
        if initial_status["orchestrator"]["status"] != "online":
            print(f"\n❌ Orchestrator jest niedostępny!")
            print("   Uruchom Orchestrator przed testem")
            return False

        print(f"\n✅ Wszystkie usługi są dostępne - można rozpocząć test")

        # Uruchom scenariusz startowy
        if not await self.trigger_startup_scenario():
            print(f"\n❌ Nie udało się uruchomić scenariusza")
            return False

        # Monitoruj postęp
        final_states = await self.monitor_scenario_progress(duration=120)  # 2 minuty

        # Podsumowanie
        print("\n" + "=" * 80)
        print("📈 PODSUMOWANIE TESTU")
        print("=" * 80)

        success_count = 0
        for service_name, state in final_states.items():
            if state in ["RUN", "STARTED"]:
                print(f"   ✅ {service_name:<15} - {state} (SUCCESS)")
                success_count += 1
            else:
                print(f"   ❌ {service_name:<15} - {state} (FAILED)")

        if success_count == len(final_states):
            print(f"\n🎉 TEST ZAKOŃCZONY SUKCESEM!")
            print(
                f"   Wszystkie {success_count}/{len(final_states)} usług osiągnęły stan operacyjny"
            )
            return True
        else:
            print(f"\n⚠️  TEST CZĘŚCIOWO UDANY")
            print(
                f"   {success_count}/{len(final_states)} usług osiągnęło stan operacyjny"
            )
            return False


async def main():
    """Główna funkcja testu."""
    tester = ScenarioTester()

    try:
        success = await tester.run_full_test()
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print(f"\n🛑 Test przerwany przez użytkownika")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Nieoczekiwany błąd testu: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("🧪 Uruchamianie testu pełnego scenariusza...")
    asyncio.run(main())
