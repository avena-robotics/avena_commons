import os

from avena_commons.orchestrator.orchestrator import Orchestrator
from avena_commons.util.logger import LoggerPolicyPeriod, MessageLogger, debug


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

    # async def start_with_autonomous_mode(self):
    #     """Uruchamia orchestrator i tryb autonomiczny."""
    #     print("🚀 Uruchamiam test orchestrator...")

    #     # Uruchom podstawowy orchestrator
    #     self.start()
    #     print("✅ Orchestrator uruchomiony")

    #     # Sprawdź scenariusze autonomiczne
    #     status = self.get_autonomous_status()
    #     autonomous_count = len(status["scenarios"])

    #     if autonomous_count > 0:
    #         print(f"🤖 Znaleziono {autonomous_count} scenariuszy autonomicznych:")
    #         for name, scenario_status in status["scenarios"].items():
    #             print(f"   • {name} (priorytet: {scenario_status['priority']})")
    #             conditions = scenario_status["conditions"]
    #             if conditions["any_component_in_state"]:
    #                 print(
    #                     f"     ✅ Uruchamiany gdy: {conditions['any_component_in_state']}"
    #                 )
    #             if conditions["no_component_in_state"]:
    #                 print(f"     ❌ Ale nie gdy: {conditions['no_component_in_state']}")

    #         # Uruchom tryb autonomiczny
    #         print("🎯 Uruchamiam tryb autonomiczny...")
    #         await self.start_autonomous_mode()
    #         print("✅ Tryb autonomiczny aktywny!")

    #         # Symuluj przykładowe stany dla demonstracji
    #         print("🧪 Symulacja stanów komponentów dla demonstracji:")
    #         await self.simulate_component_state("io", "RUN")
    #         await self.simulate_component_state("supervisor_1", "RUN")
    #         await self.simulate_component_state("supervisor_2", "RUN")
    #         await self.simulate_component_state("munchies_algo", "RUN")
    #         print("   Wszystkie komponenty w stanie RUN")

    #         print(
    #             f"📊 System monitoruje co {status['monitor_interval_seconds']} sekund"
    #         )
    #         print("💡 Przykłady testowania autonomicznego systemu:")
    #         print(
    #             "   • Ustaw komponent w STOPPED: await orchestrator.simulate_component_state('io', 'STOPPED')"
    #         )
    #         print(
    #             "   • Sprawdź historię: orchestrator.get_autonomous_status()['execution_history']"
    #         )
    #         print(
    #             "   • System automatycznie uruchomi scenariusz gdy warunki będą spełnione!"
    #         )
    #     else:
    #         print(
    #             "⚠️ Brak scenariuszy autonomicznych - tryb autonomiczny nie zostanie uruchomiony"
    #         )

    #     return self

    # async def run_interactive_demo(self):
    #     """Uruchamia interaktywną demonstrację systemu autonomicznego."""
    #     print("\n🎭 INTERAKTYWNA DEMONSTRACJA SYSTEMU AUTONOMICZNEGO")
    #     print("=" * 60)

    #     # Krok 1: Wszystkie w RUN
    #     print("\n1️⃣ KROK 1: Wszystkie komponenty w stanie RUN")
    #     await self.simulate_component_state("io", "RUN")
    #     await self.simulate_component_state("supervisor_1", "RUN")
    #     await self.simulate_component_state("supervisor_2", "RUN")
    #     await self.simulate_component_state("munchies_algo", "RUN")

    #     print("   Stan systemu:")
    #     for comp_name, comp_data in self._state.items():
    #         state = comp_data.get("fsm_state", "UNKNOWN")
    #         print(f"     🟢 {comp_name}: {state}")

    #     print("   ⏳ Czekam 6 sekund - scenariusz NIE powinien się uruchomić...")
    #     await asyncio.sleep(6)

    #     history = self.get_autonomous_status()["execution_history"]
    #     print(f"   📊 Historia wykonań: {len(history)} (powinno być 0)")

    #     # Krok 2: Jeden w STOPPED
    #     print("\n2️⃣ KROK 2: Ustawiam komponent 'io' w stan STOPPED")
    #     await self.simulate_component_state("io", "STOPPED")

    #     print("   Stan systemu po zmianie:")
    #     for comp_name, comp_data in self._state.items():
    #         state = comp_data.get("fsm_state", "UNKNOWN")
    #         emoji = "🔴" if state == "STOPPED" else "🟢" if state == "RUN" else "⚪"
    #         print(f"     {emoji} {comp_name}: {state}")

    #     print("   ⏳ Czekam 8 sekund - scenariusz POWINIEN się uruchomić...")
    #     await asyncio.sleep(8)

    #     history_after = self.get_autonomous_status()["execution_history"]
    #     print(f"   📊 Historia wykonań: {len(history_after)}")

    #     if len(history_after) > len(history):
    #         latest = history_after[-1]
    #         print(f"   🎉 SUKCES! Scenariusz uruchomiony autonomicznie:")
    #         print(f"      📝 Nazwa: {latest['scenario_name']}")
    #         print(f"      ⏰ Czas: {latest['execution_time']}")
    #         print(f"      ✅ Sukces: {latest['success']}")
    #     else:
    #         print("   ⚠️ Scenariusz nie został uruchomiony")

    #     # Krok 3: Dodaj ERROR
    #     print("\n3️⃣ KROK 3: Dodaję komponent w stanie ERROR")
    #     await self.simulate_component_state("supervisor_1", "ERROR")
    #     await self.simulate_component_state("supervisor_2", "STOPPED")  # Więcej STOPPED

    #     print("   Stan systemu po zmianie:")
    #     for comp_name, comp_data in self._state.items():
    #         state = comp_data.get("fsm_state", "UNKNOWN")
    #         emoji = (
    #             "🔴"
    #             if state == "STOPPED"
    #             else "🟢"
    #             if state == "RUN"
    #             else "❌"
    #             if state == "ERROR"
    #             else "⚪"
    #         )
    #         print(f"     {emoji} {comp_name}: {state}")

    #     print(
    #         "   ⏳ Czekam 8 sekund - scenariusz NIE powinien się uruchomić (ERROR blokuje)..."
    #     )
    #     await asyncio.sleep(8)

    #     history_final = self.get_autonomous_status()["execution_history"]
    #     if len(history_final) == len(history_after):
    #         print(
    #             "   ✅ Poprawnie! Scenariusz nie uruchomił się z powodu komponentu w ERROR"
    #         )
    #     else:
    #         print("   ⚠️ Nieoczekiwanie - scenariusz uruchomił się mimo ERROR")

    #     print("\n🎯 DEMONSTRACJA ZAKOŃCZONA")
    #     print("=" * 60)
    #     print("✅ System autonomiczny działa zgodnie z oczekiwaniami!")


# async def main():
#     """Główna funkcja asynchroniczna."""
#     temp_path = os.path.abspath("temp")

#     # Utwórz katalog temp jeśli nie istnieje
#     os.makedirs(temp_path, exist_ok=True)

#     message_logger = MessageLogger(
#         filename=f"{temp_path}/test_orchestrator.log",
#         period=LoggerPolicyPeriod.LAST_15_MINUTES,
#     )
#     # message_logger = None
#     port = 9500

#     try:
#         print("🎯 AUTONOMICZNY TEST ORCHESTRATOR")
#         print("=" * 50)

#         app = TestOrchestrator(
#             name="autonomous_test_orchestrator",
#             address="127.0.0.1",
#             port=port,
#             message_logger=message_logger,
#             debug=True,
#         )

#         # Uruchom z trybem autonomicznym
#         # await app.start_with_autonomous_mode()
#         app.start()

#         # print("\n🎯 ORCHESTRATOR GOTOWY")
#         # print("=" * 50)
#         # print("📡 Orchestrator endpoint: http://127.0.0.1:9500")
#         # print("🔄 Monitoring autonomiczny: AKTYWNY")

#         # Wybór trybu
#         # print("\n🎭 Dostępne tryby:")
#         # print("   [1] Interaktywna demonstracja (automatyczna)")
#         # print("   [2] Tryb ciągły (Ctrl+C aby zatrzymać)")

#         # choice = input("\nWybierz tryb (1/2): ").strip()

#         # if choice == "1":
#         #     await app.run_interactive_demo()
#         # else:
#         print("\n⌨️  Tryb ciągły - naciśnij Ctrl+C aby zatrzymać")
#         print(
#             "💡 System będzie monitorować stany i uruchamiać scenariusze autonomicznie"
#         )

#         try:
#             while True:
#                 await asyncio.sleep(1)
#         except KeyboardInterrupt:
#             pass

#     except KeyboardInterrupt:
#         print("\n⏹️ Zatrzymywanie przez użytkownika...")
#         if "app" in locals():
#             app.stop_autonomous_mode()
#     except Exception as e:
#         print(f"❌ Błąd: {e}", file=sys.stderr)
#         import traceback

#         traceback.print_exc()
#     finally:
#         print("🔚 Test orchestrator zatrzymany")


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
