"""
ExecuteScenarioAction - akcja uruchamiania scenariusza zagnieżdżonego.

Odpowiedzialność:
- Uruchamianie scenariuszy zagnieżdżonych z kontrolą przepływu
- Oczekiwanie na zakończenie zagnieżdżonego scenariusza
- Obsługa timeout i błędów zagnieżdżonych scenariuszy
- Analogiczna do send_command ale dla scenariuszy

Eksponuje:
- Klasa `ExecuteScenarioAction`
"""

import asyncio
from typing import Any, Dict

from avena_commons.util.logger import error, info, warning

from ..models.scenario_models import ScenarioContext
from .base_action import ActionExecutionError, BaseAction


class ExecuteScenarioAction(BaseAction):
    """
    Akcja uruchamiania scenariusza zagnieżdżonego.

    Analogiczna do send_command - uruchamia scenariusz zagnieżdżony
    i opcjonalnie czeka na jego zakończenie.

    Konfiguracja JSON:
    {
        "type": "execute_scenario",
        "scenario": "nazwa_scenariusza",
        "wait_for_completion": true,  // domyślnie true
        "timeout": "60s",  // opcjonalnie
        "on_failure": "continue",  // "continue" lub "fail"
        "description": "Uruchomienie scenariusza diagnostycznego"
    }
    """
    pass
    # TODO: Jeśli będzie potrzebne, trzeba dokończyć, zmienił się format kontekstu i akcja nie działa

    # async def execute(
    #     self, action_config: Dict[str, Any], context: ScenarioContext
    # ) -> Any:
    #     """
    #     Wykonuje uruchomienie scenariusza zagnieżdżonego.

    #     Args:
    #         action_config: Konfiguracja akcji z scenariusza
    #         context: Kontekst wykonania akcji

    #     Returns:
    #         str: ID wykonania zagnieżdżonego scenariusza

    #     Raises:
    #         ActionExecutionError: W przypadku błędu uruchomienia lub wykonania
    #     """
    #     scenario_name = action_config.get("scenario")
    #     if not scenario_name:
    #         raise ActionExecutionError(
    #             "execute_scenario",
    #             "Brak nazwy scenariusza (klucz: scenario) w konfiguracji",
    #         )

    #     # Rozwiąż zmienne szablonowe w nazwie scenariusza
    #     scenario_name = self._resolve_template_variables(scenario_name, context)

    #     wait_for_completion = action_config.get("wait_for_completion", True)
    #     timeout_str = action_config.get("timeout", "60s")
    #     on_failure = action_config.get("on_failure", "fail")  # "continue" lub "fail"

    #     info(
    #         f"🎯 Uruchamiam scenariusz zagnieżdżony: '{scenario_name}'",
    #         message_logger=context.message_logger,
    #     )

    #     # Sprawdź czy scenariusz istnieje
    #     available_scenarios = context.get("scenarios", {})
    #     if scenario_name not in available_scenarios:
    #         available_scenarios = list(available_scenarios.keys())
    #         raise ActionExecutionError(
    #             "execute_scenario",
    #             f"Scenariusz '{scenario_name}' nie istnieje. Dostępne: {available_scenarios}",
    #         )

    #     try:
    #         # Przygotuj dane triggera dla zagnieżdżonego scenariusza
    #         nested_trigger_data = {
    #             "source": "nested_scenario",
    #             "event_type": "NESTED_EXECUTION",
    #             "parent_scenario": context.scenario_name,
    #             "timestamp": asyncio.get_event_loop().time(),
    #         }

    #         # Jeśli nie czekamy na zakończenie, uruchom asynchronicznie
    #         if not wait_for_completion:
    #             # Uruchom scenariusz w tle bez czekania
    #             asyncio.create_task(
    #                 orchestrator.execute_scenario(scenario_name, nested_trigger_data)
    #             )
    #             info(
    #                 f"🚀 Uruchomiono scenariusz zagnieżdżony w tle: '{scenario_name}'",
    #                 message_logger=context.message_logger,
    #             )
    #             return f"async_{scenario_name}"

    #         # Uruchom scenariusz synchronicznie z timeout
    #         timeout_seconds = self._parse_timeout(timeout_str)

    #         info(
    #             f"🚀 Uruchamiam scenariusz zagnieżdżony synchronicznie: '{scenario_name}' (timeout: {timeout_seconds}s)",
    #             message_logger=context.message_logger,
    #         )

    #         try:
    #             # Uruchom scenariusz z timeout
    #             result = await asyncio.wait_for(
    #                 orchestrator.execute_scenario(scenario_name, nested_trigger_data),
    #                 timeout=timeout_seconds,
    #             )

    #             # result jest bool - True oznacza sukces, False błąd
    #             if result:
    #                 info(
    #                     f"✅ Scenariusz zagnieżdżony zakończony pomyślnie: '{scenario_name}'",
    #                     message_logger=context.message_logger,
    #                 )
    #                 return scenario_name
    #             else:
    #                 error(
    #                     f"❌ Scenariusz zagnieżdżony zakończony błędem: '{scenario_name}'",
    #                     message_logger=context.message_logger,
    #                 )

    #                 if on_failure == "continue":
    #                     warning(
    #                         f"⚠️ Kontynuuję mimo błędu zagnieżdżonego scenariusza (on_failure=continue)",
    #                         message_logger=context.message_logger,
    #                     )
    #                     return scenario_name
    #                 else:
    #                     raise ActionExecutionError(
    #                         "execute_scenario",
    #                         f"Scenariusz zagnieżdżony '{scenario_name}' zakończony błędem",
    #                     )

    #         except asyncio.TimeoutError:
    #             error(
    #                 f"⏰ Timeout oczekiwania na scenariusz: '{scenario_name}' ({timeout_seconds}s)",
    #                 message_logger=context.message_logger,
    #             )

    #             if on_failure == "continue":
    #                 warning(
    #                     f"⚠️ Kontynuuję mimo timeout (on_failure=continue)",
    #                     message_logger=context.message_logger,
    #                 )
    #                 return scenario_name
    #             else:
    #                 raise ActionExecutionError(
    #                     "execute_scenario",
    #                     f"Timeout oczekiwania na scenariusz '{scenario_name}' ({timeout_seconds}s)",
    #                 )

    #     except ActionExecutionError:
    #         # Przepuść błędy ActionExecutionError
    #         raise
    #     except Exception as e:
    #         error(
    #             f"💥 Nieoczekiwany błąd podczas uruchamiania scenariusza '{scenario_name}': {e}",
    #             message_logger=context.message_logger,
    #         )
    #         raise ActionExecutionError(
    #             "execute_scenario",
    #             f"Nieoczekiwany błąd podczas uruchamiania scenariusza '{scenario_name}': {str(e)}",
    #         )
