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

from avena_commons.util.logger import debug, error, info, warning

from .base_action import ActionContext, ActionExecutionError, BaseAction


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

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Any:
        """
        Wykonuje uruchomienie scenariusza zagnieżdżonego.

        Args:
            action_config: Konfiguracja akcji z scenariusza
            context: Kontekst wykonania akcji

        Returns:
            str: ID wykonania zagnieżdżonego scenariusza

        Raises:
            ActionExecutionError: W przypadku błędu uruchomienia lub wykonania
        """
        scenario_name = action_config.get("scenario")
        if not scenario_name:
            raise ActionExecutionError(
                "execute_scenario",
                "Brak nazwy scenariusza (klucz: scenario) w konfiguracji"
            )

        # Rozwiąż zmienne szablonowe w nazwie scenariusza
        scenario_name = self._resolve_template_variables(scenario_name, context)

        wait_for_completion = action_config.get("wait_for_completion", True)
        timeout_str = action_config.get("timeout", "60s")
        on_failure = action_config.get("on_failure", "fail")  # "continue" lub "fail"

        info(
            f"🎯 Uruchamiam scenariusz zagnieżdżony: '{scenario_name}'",
            message_logger=context.message_logger
        )

        # Sprawdź czy scenariusz istnieje
        orchestrator = context.orchestrator
        if scenario_name not in orchestrator._scenarios:
            available_scenarios = list(orchestrator._scenarios.keys())
            raise ActionExecutionError(
                "execute_scenario",
                f"Scenariusz '{scenario_name}' nie istnieje. Dostępne: {available_scenarios}"
            )

        try:
            # Pobierz execution_manager z orchestratora
            execution_manager = getattr(orchestrator, '_execution_manager', None)
            if not execution_manager:
                raise ActionExecutionError(
                    "execute_scenario",
                    "ScenarioExecutionManager nie jest dostępny w orchestratorze"
                )

            # Pobierz ID bieżącego wykonania z kontekstu
            current_execution_id = getattr(context, 'execution_id', None)

            # Przygotuj dane triggera dla zagnieżdżonego scenariusza
            nested_trigger_data = {
                "source": "nested_scenario",
                "event_type": "NESTED_EXECUTION",
                "parent_scenario": context.scenario_name,
                "parent_execution_id": current_execution_id,
                "timestamp": asyncio.get_event_loop().time()
            }

            # Uruchom scenariusz zagnieżdżony
            nested_execution_id = await orchestrator.execute_scenario_with_control(
                scenario_name=scenario_name,
                trigger_data=nested_trigger_data,
                parent_execution_id=current_execution_id
            )

            info(
                f"🚀 Uruchomiono scenariusz zagnieżdżony: {nested_execution_id}",
                message_logger=context.message_logger
            )

            # Jeśli nie czekamy na zakończenie, zwróć ID i zakończ
            if not wait_for_completion:
                info(
                    f"⏭️ Nie czekam na zakończenie scenariusza: {nested_execution_id}",
                    message_logger=context.message_logger
                )
                return nested_execution_id

            # Czekaj na zakończenie z timeout
            timeout_seconds = self._parse_timeout(timeout_str)
            
            info(
                f"⏳ Oczekuję na zakończenie scenariusza: {nested_execution_id} (timeout: {timeout_seconds}s)",
                message_logger=context.message_logger
            )

            try:
                # Czekaj na zakończenie zagnieżdżonego scenariusza
                await asyncio.wait_for(
                    self._wait_for_scenario_completion(execution_manager, nested_execution_id),
                    timeout=timeout_seconds
                )

                # Sprawdź wynik
                status = execution_manager.get_execution_status(nested_execution_id)
                if not status:
                    raise ActionExecutionError(
                        "execute_scenario",
                        f"Nie można pobrać statusu scenariusza: {nested_execution_id}"
                    )

                if status["state"] == "COMPLETED":
                    info(
                        f"✅ Scenariusz zagnieżdżony zakończony pomyślnie: {nested_execution_id}",
                        message_logger=context.message_logger
                    )
                    return nested_execution_id
                elif status["state"] == "FAILED":
                    error_msg = status.get("error_message", "Nieznany błąd")
                    error(
                        f"❌ Scenariusz zagnieżdżony zakończony błędem: {nested_execution_id} - {error_msg}",
                        message_logger=context.message_logger
                    )
                    
                    if on_failure == "continue":
                        warning(
                            f"⚠️ Kontynuuję mimo błędu zagnieżdżonego scenariusza (on_failure=continue)",
                            message_logger=context.message_logger
                        )
                        return nested_execution_id
                    else:
                        raise ActionExecutionError(
                            "execute_scenario",
                            f"Scenariusz zagnieżdżony '{scenario_name}' zakończony błędem: {error_msg}"
                        )
                else:
                    raise ActionExecutionError(
                        "execute_scenario",
                        f"Scenariusz zagnieżdżony w nieoczekiwanym stanie: {status['state']}"
                    )

            except asyncio.TimeoutError:
                error(
                    f"⏰ Timeout oczekiwania na scenariusz: {nested_execution_id} ({timeout_seconds}s)",
                    message_logger=context.message_logger
                )
                
                if on_failure == "continue":
                    warning(
                        f"⚠️ Kontynuuję mimo timeout (on_failure=continue)",
                        message_logger=context.message_logger
                    )
                    return nested_execution_id
                else:
                    raise ActionExecutionError(
                        "execute_scenario",
                        f"Timeout oczekiwania na scenariusz '{scenario_name}' ({timeout_seconds}s)"
                    )

        except ActionExecutionError:
            # Przepuść błędy ActionExecutionError
            raise
        except Exception as e:
            error(
                f"💥 Nieoczekiwany błąd podczas uruchamiania scenariusza '{scenario_name}': {e}",
                message_logger=context.message_logger
            )
            raise ActionExecutionError(
                "execute_scenario",
                f"Nieoczekiwany błąd podczas uruchamiania scenariusza '{scenario_name}': {str(e)}"
            )

    async def _wait_for_scenario_completion(self, execution_manager, execution_id: str) -> None:
        """
        Oczekuje na zakończenie scenariusza.

        Args:
            execution_manager: ScenarioExecutionManager
            execution_id: ID wykonania do oczekiwania

        Raises:
            ActionExecutionError: Jeśli scenariusz nie istnieje
        """
        while True:
            status = execution_manager.get_execution_status(execution_id)
            
            if not status:
                raise ActionExecutionError(
                    "execute_scenario",
                    f"Scenariusz {execution_id} nie istnieje lub został usunięty"
                )

            state = status["state"]
            if state in ["COMPLETED", "FAILED", "CANCELLED"]:
                break

            # Czekaj krótko przed kolejnym sprawdzeniem
            await asyncio.sleep(0.5)
