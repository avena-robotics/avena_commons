#!/usr/bin/env python3
"""
Przykład uruchomienia scenariusza startowego dla Orchestratora
"""

import asyncio
import os
import sys

# Dodaj ścieżkę do modułów
sys.path.append(os.path.join(os.path.dirname(__file__), "avena_commons/src"))

from avena_commons.orchestrator.orchestrator import Orchestrator
from avena_commons.util.logger import MessageLogger


async def test_startup_scenario():
    """Test scenariusza startowego"""

    # Utwórz logger
    logger = MessageLogger(name="orchestrator_test")

    # Utwórz Orchestrator
    orchestrator = Orchestrator(
        name="orchestrator",
        port=8000,
        address="127.0.0.1",
        message_logger=logger,
        debug=True,
    )

    try:
        print("=== Uruchamianie Orchestratora ===")

        # Ręczne przejście do stanu RUN (w normalnym przypadku byłby to start())
        orchestrator._change_fsm_state(orchestrator.EventListenerState.INITIALIZED)

        print(f"Dostępne scenariusze: {list(orchestrator._scenarios.keys())}")

        # Wykonaj scenariusz startowy
        scenario_name = "Scenariusz startowy systemu - STOPPED do RUN"

        if scenario_name in orchestrator._scenarios:
            print(f"\n=== Wykonywanie scenariusza: {scenario_name} ===")
            success = await orchestrator.execute_scenario(scenario_name)

            if success:
                print("✓ Scenariusz zakończony pomyślnie!")
            else:
                print("✗ Scenariusz zakończony z błędem!")
        else:
            print(f"Scenariusz '{scenario_name}' nie został znaleziony!")
            print(f"Dostępne: {list(orchestrator._scenarios.keys())}")

    except KeyboardInterrupt:
        print("\nZatrzymywanie...")
    except Exception as e:
        print(f"Błąd: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Zamknij Orchestrator jeśli został utworzony
        if "orchestrator" in locals():
            orchestrator.shutdown()


def main():
    """Główna funkcja"""
    print("Testowanie scenariusza startowego Orchestratora")
    print("=" * 50)

    # Uruchom test
    asyncio.run(test_startup_scenario())


if __name__ == "__main__":
    main()
