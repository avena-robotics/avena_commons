"""
PauseScenarioAction - akcja zatrzymywania scenariusza.

Odpowiedzialność:
- Zatrzymywanie bieżącego lub określonego scenariusza
- Analogiczna do send_command ale dla kontroli przepływu scenariuszy
- Obsługa błędów i walidacja stanu

Eksponuje:
- Klasa `PauseScenarioAction`
"""

from typing import Any, Dict

from avena_commons.util.logger import error, info, warning

from .base_action import ActionContext, ActionExecutionError, BaseAction


class PauseScenarioAction(BaseAction):
    """
    Akcja zatrzymywania scenariusza.
    
    Analogiczna do send_command - zatrzymuje scenariusz
    i pozwala na późniejsze wznowienie.
    
    Konfiguracja JSON:
    {
        "type": "pause_scenario",
        "execution_id": "current",  // "current" lub konkretne ID
        "description": "Zatrzymanie dla interwencji użytkownika"
    }
    """

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Any:
        """
        Wykonuje zatrzymanie scenariusza.

        Args:
            action_config: Konfiguracja akcji z scenariusza
            context: Kontekst wykonania akcji

        Returns:
            str: ID zatrzymanego wykonania

        Raises:
            ActionExecutionError: W przypadku błędu zatrzymania
        """
        execution_id = action_config.get("execution_id", "current")
        
        # Rozwiąż zmienne szablonowe
        execution_id = self._resolve_template_variables(execution_id, context)

        info(
            f"⏸️ Zatrzymuję scenariusz: {execution_id}",
            message_logger=context.message_logger
        )

        # Pobierz execution_manager z orchestratora
        orchestrator = context.orchestrator
        execution_manager = getattr(orchestrator, '_execution_manager', None)
        if not execution_manager:
            raise ActionExecutionError(
                "pause_scenario",
                "ScenarioExecutionManager nie jest dostępny w orchestratorze"
            )

        try:
            # Obsłuż specjalną wartość "current"
            if execution_id == "current":
                current_execution_id = getattr(context, 'execution_id', None)
                if not current_execution_id:
                    raise ActionExecutionError(
                        "pause_scenario",
                        "Nie można określić ID bieżącego wykonania (brak execution_id w kontekście)"
                    )
                execution_id = current_execution_id

            # Zatrzymaj scenariusz
            success = await execution_manager.pause_execution(execution_id)
            
            if success:
                info(
                    f"✅ Scenariusz zatrzymany pomyślnie: {execution_id}",
                    message_logger=context.message_logger
                )
                return execution_id
            else:
                # execution_manager już zalogował szczegóły błędu
                raise ActionExecutionError(
                    "pause_scenario",
                    f"Nie udało się zatrzymać scenariusza: {execution_id}"
                )

        except ActionExecutionError:
            # Przepuść błędy ActionExecutionError
            raise
        except Exception as e:
            error(
                f"💥 Nieoczekiwany błąd podczas zatrzymywania scenariusza {execution_id}: {e}",
                message_logger=context.message_logger
            )
            raise ActionExecutionError(
                "pause_scenario",
                f"Nieoczekiwany błąd podczas zatrzymywania scenariusza {execution_id}: {str(e)}"
            )
