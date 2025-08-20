#!/usr/bin/env python3
"""
Test nowego systemu akcji scenariuszy.
"""

import asyncio
import os
import sys

# Dodaj ścieżkę do modułów
sys.path.append(os.path.join(os.path.dirname(__file__), "avena_commons/src"))

from avena_commons.orchestrator.actions import ActionContext, ActionExecutionError, ActionExecutor
from avena_commons.util.logger import MessageLogger


async def test_action_system():
    """Test systemu akcji bez pełnego Orchestratora."""

    print("=== Test nowego systemu akcji ===")

    # Utwórz logger z właściwym konstruktorem
    logger = MessageLogger(filename="action_test.log", debug=True)

    # Utwórz ActionExecutor
    action_executor = ActionExecutor()

    # Sprawdź jakie akcje są zarejestrowane
    registered_actions = action_executor.get_registered_actions()
    print(f"Zarejestrowane akcje: {list(registered_actions.keys())}")

    # Mock Orchestrator (tylko potrzebne części)
    class MockOrchestrator:
        def __init__(self):
            self._configuration = {
                "components": {
                    "io": {"address": "127.0.0.1", "port": 8001, "group": "base_io"},
                    "supervisor_1": {"address": "127.0.0.1", "port": 8002, "group": "supervisors"},
                    "munchies_algo": {"address": "127.0.0.1", "port": 8004, "group": "main_logic"},
                }
            }
            self._state = {}

        async def _event(self, **kwargs):
            print(f"Mock: Wysyłanie wydarzenia: {kwargs}")
            return None

    mock_orchestrator = MockOrchestrator()

    # Utwórz kontekst
    context = ActionContext(orchestrator=mock_orchestrator, message_logger=logger, scenario_name="test_scenario")

    try:
        print("\n--- Test 1: log_event ---")
        await action_executor.execute_action({"type": "log_event", "level": "info", "message": "Test komunikatu info"}, context)

        await action_executor.execute_action({"type": "log_event", "level": "success", "message": "Test komunikatu success"}, context)

        print("\n--- Test 2: send_command do pojedynczego komponentu ---")
        await action_executor.execute_action({"type": "send_command", "component": "io", "command": "CMD_INITIALIZE"}, context)

        print("\n--- Test 3: send_command do grupy ---")
        await action_executor.execute_action({"type": "send_command", "group": "supervisors", "command": "CMD_INITIALIZE"}, context)

        print("\n--- Test 4: send_command do wszystkich (@all) ---")
        await action_executor.execute_action({"type": "send_command", "target": "@all", "command": "CMD_RUN"}, context)

        print("\n--- Test 5: wait_for_state (skipped - brak rzeczywistych komponentów) ---")
        print("Test wait_for_state pominięty - wymaga rzeczywistych komponentów")

        print("\n✓ Wszystkie testy zakończone pomyślnie!")

    except ActionExecutionError as e:
        print(f"✗ Błąd akcji: {e}")
    except Exception as e:
        print(f"✗ Nieoczekiwany błąd: {e}")
        import traceback

        traceback.print_exc()


def main():
    """Główna funkcja"""
    print("Test nowego systemu akcji scenariuszy")
    print("=" * 50)

    # Uruchom test
    asyncio.run(test_action_system())


if __name__ == "__main__":
    main()
