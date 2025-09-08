"""
ResumeScenarioAction - akcja wznawiania scenariusza.

Odpowiedzialność:
- Wznawianie zatrzymanego scenariusza
- Analogiczna do send_command ale dla kontroli przepływu scenariuszy
- Obsługa błędów i walidacja stanu

Eksponuje:
- Klasa `ResumeScenarioAction`
"""

from typing import Any, Dict

from avena_commons.util.logger import error, info, warning

from .base_action import ActionContext, ActionExecutionError, BaseAction


class ResumeScenarioAction(BaseAction):
    """
    Akcja wznawiania scenariusza.
    
    Analogiczna do send_command - wznawia zatrzymany scenariusz
    i kontynuuje jego wykonanie.
    
    Konfiguracja JSON:
    {
        "type": "resume_scenario",
        "execution_id": "{{ paused_execution_id }}",  // ID do wznowienia
        "description": "Wznowienie po zatwierdzeniu użytkownika"
    }
    """

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Any:
        """
        Wykonuje wznowienie scenariusza.

        Args:
            action_config: Konfiguracja akcji z scenariusza
            context: Kontekst wykonania akcji

        Returns:
            str: ID wznowionego wykonania

        Raises:
            ActionExecutionError: W przypadku błędu wznowienia
        """
        execution_id = action_config.get("execution_id")
        if not execution_id:
            raise ActionExecutionError(
                "resume_scenario",
                "Brak ID wykonania (klucz: execution_id) w konfiguracji"
            )
        
        # Rozwiąż zmienne szablonowe
        execution_id = self._resolve_template_variables(execution_id, context)

        info(
            f"▶️ Wznawiamy scenariusz: {execution_id}",
            message_logger=context.message_logger
        )

        # Pobierz execution_manager z orchestratora
        orchestrator = context.orchestrator
        execution_manager = getattr(orchestrator, '_execution_manager', None)
        if not execution_manager:
            raise ActionExecutionError(
                "resume_scenario",
                "ScenarioExecutionManager nie jest dostępny w orchestratorze"
            )

        try:
            # Wznów scenariusz
            success = await execution_manager.resume_execution(execution_id)
            
            if success:
                info(
                    f"✅ Scenariusz wznowiony pomyślnie: {execution_id}",
                    message_logger=context.message_logger
                )
                return execution_id
            else:
                # execution_manager już zalogował szczegóły błędu
                raise ActionExecutionError(
                    "resume_scenario",
                    f"Nie udało się wznowić scenariusza: {execution_id}"
                )

        except ActionExecutionError:
            # Przepuść błędy ActionExecutionError
            raise
        except Exception as e:
            error(
                f"💥 Nieoczekiwany błąd podczas wznawiania scenariusza {execution_id}: {e}",
                message_logger=context.message_logger
            )
            raise ActionExecutionError(
                "resume_scenario",
                f"Nieoczekiwany błąd podczas wznawiania scenariusza {execution_id}: {str(e)}"
            )
