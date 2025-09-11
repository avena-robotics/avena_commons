"""
AI-generated code: Akcja warunkowego wykonywania akcji na podstawie spełnienia warunków.

Implementuje logikę if-then-else dla scenariuszy, gdzie na podstawie
sprawdzenia warunków wykonywana jest odpowiednia lista akcji.
"""

from typing import Any, Dict, List

from avena_commons.util.logger import debug, error, info

from ..factories.condition_factory import ConditionFactory
from .base_action import ActionContext, ActionExecutionError, BaseAction


class EvaluateConditionAction(BaseAction):
    """
    Akcja warunkowego wykonywania akcji.

    Sprawdza warunki i w zależności od wyniku wykonuje odpowiednie akcje.
    Obsługuje zarówno pojedyncze warunki jak i złożone konstrukcje logiczne.

    Args:
        conditions: Warunki do sprawdzenia w jednym z formatów:
                   - Słownik jak w trigger: {"client_state": {"any_service_in_state": ["FAULT"]}}
                   - Lista obiektów: [{"type": "database_list", "component": "...", ...}]
        true_actions: Lista akcji do wykonania gdy warunki są spełnione (opcjonalne)
        false_actions: Lista akcji do wykonania gdy warunki nie są spełnione (opcjonalne)

    Returns:
        Dict zawierający wynik ewaluacji warunków i wyniki wykonanych akcji.

    Raises:
        ActionExecutionError: Gdy konfiguracja jest nieprawidłowa lub wystąpi błąd wykonania.
    """

    def __init__(self):
        """Inicjalizuje akcję evaluate_condition."""
        pass

    async def execute(
        self, action_config: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Wykonuje ewaluację warunków i odpowiednie akcje.

        Args:
            action_config: Konfiguracja akcji zawierająca conditions, true_actions, false_actions
            context: Kontekst wykonania akcji

        Returns:
            Dict z wynikami ewaluacji i wykonanych akcji

        Raises:
            ActionExecutionError: W przypadku błędu konfiguracji lub wykonania
        """
        try:
            # Walidacja konfiguracji
            self._validate_config(action_config)

            # Pobierz konfigurację
            conditions = action_config["conditions"]
            true_actions = action_config.get("true_actions", [])
            false_actions = action_config.get("false_actions", [])

            debug(
                f"🔍 Ewaluacja warunków: {len(conditions)} warunków, "
                f"{len(true_actions)} true_actions, {len(false_actions)} false_actions",
                message_logger=context.message_logger,
            )

            # Ewaluuj warunki
            condition_result, condition_data = await self._evaluate_conditions(conditions, context)
            context.trigger_data.update(condition_data)
            
            info(
                f"📊 Wynik ewaluacji warunków: {condition_result}",
                message_logger=context.message_logger,
            )

            # Wykonaj odpowiednie akcje
            executed_actions = []
            actions_to_execute = true_actions if condition_result else false_actions
            action_branch = "true_actions" if condition_result else "false_actions"

            if actions_to_execute:
                info(
                    f"🎯 Wykonywanie {len(actions_to_execute)} akcji z {action_branch}",
                    message_logger=context.message_logger,
                )

                executed_actions = await self._execute_actions(
                    actions_to_execute, context
                )
            else:
                info(
                    f"⏭️ Brak akcji do wykonania w {action_branch}",
                    message_logger=context.message_logger,
                )

            return context

        except ActionExecutionError:
            raise
        except Exception as e:
            error(
                f"❌ Nieoczekiwany błąd w evaluate_condition: {e}",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(
                "evaluate_condition", f"Nieoczekiwany błąd: {str(e)}", e
            )

    def _validate_config(self, action_config: Dict[str, Any]) -> None:
        """
        Waliduje konfigurację akcji evaluate_condition.

        Args:
            action_config: Konfiguracja do walidacji

        Raises:
            ActionExecutionError: Gdy konfiguracja jest nieprawidłowa
        """
        if "conditions" not in action_config:
            raise ActionExecutionError(
                "evaluate_condition", "Brak wymaganego pola 'conditions'"
            )

        conditions = action_config["conditions"]

        # Obsługuj oba formaty: słownik (jak w trigger) lub lista
        if isinstance(conditions, dict):
            # Format jak w trigger: {"client_state": {...}}
            if len(conditions) == 0:
                raise ActionExecutionError(
                    "evaluate_condition",
                    "Pole 'conditions' nie może być pustym słownikiem",
                )
        elif isinstance(conditions, list):
            # Format z listą: [{"type": "...", ...}]
            if len(conditions) == 0:
                raise ActionExecutionError(
                    "evaluate_condition", "Pole 'conditions' musi być niepustą listą"
                )

            # Sprawdź że każdy warunek ma odpowiednią strukturę
            for i, condition in enumerate(conditions):
                if not isinstance(condition, dict):
                    raise ActionExecutionError(
                        "evaluate_condition",
                        f"Warunek {i} musi być słownikiem, otrzymano: {type(condition)}",
                    )

                if "type" not in condition:
                    raise ActionExecutionError(
                        "evaluate_condition", f"Warunek {i} musi zawierać pole 'type'"
                    )
        else:
            raise ActionExecutionError(
                "evaluate_condition",
                f"Pole 'conditions' musi być słownikiem lub listą, otrzymano: {type(conditions)}",
            )

        # Sprawdź że przynajmniej jedna z akcji jest zdefiniowana
        true_actions = action_config.get("true_actions", [])
        false_actions = action_config.get("false_actions", [])

        if not true_actions and not false_actions:
            raise ActionExecutionError(
                "evaluate_condition",
                "Należy zdefiniować przynajmniej 'true_actions' lub 'false_actions'",
            )

        # Waliduj strukturę akcji
        for actions_list, name in [
            (true_actions, "true_actions"),
            (false_actions, "false_actions"),
        ]:
            if actions_list and not isinstance(actions_list, list):
                raise ActionExecutionError(
                    "evaluate_condition", f"Pole '{name}' musi być listą"
                )

            for i, action in enumerate(actions_list):
                if not isinstance(action, dict):
                    raise ActionExecutionError(
                        "evaluate_condition", f"Akcja {i} w {name} musi być słownikiem"
                    )

                if "type" not in action:
                    raise ActionExecutionError(
                        "evaluate_condition",
                        f"Akcja {i} w {name} musi zawierać pole 'type'",
                    )

    async def _evaluate_conditions(self, conditions, context: ActionContext) -> bool:
        """
        Ewaluuje warunki używając factory pattern.

        Args:
            conditions: Konfiguracja warunków do sprawdzenia (słownik jak w trigger lub lista)
            context: Kontekst wykonania

        Returns:
            True jeśli warunki są spełnione, False w przeciwnym razie

        Raises:
            ActionExecutionError: W przypadku błędu ewaluacji warunków
        """
        try:
            # Przygotuj kontekst dla warunków (podobnie jak w orchestrator.py)
            orchestrator = context.orchestrator
            condition_context = {
                "clients": getattr(orchestrator, "_state", {}).copy(),
                "components": getattr(
                    orchestrator, "_components", {}
                ),  # Dodaj komponenty!
                "trigger_data": context.trigger_data or {},
            }

            # Konwertuj format listy na format słownika jeśli potrzeba
            if isinstance(conditions, list):
                # Format z listy: [{"type": "database_list", ...}]
                # Konwertuj na format słownika dla ConditionFactory
                if len(conditions) == 1:
                    # Pojedynczy warunek - użyj go bezpośrednio
                    condition_item = conditions[0].copy()  # Utwórz kopię
                    condition_type = condition_item.pop("type")  # Usuń 'type' z kopii
                    condition_config = {condition_type: condition_item}
                else:
                    # Wiele warunków - zawrap w AND
                    converted_conditions = []
                    for condition_item in conditions:
                        condition_item_copy = condition_item.copy()
                        condition_type = condition_item_copy.pop("type")
                        converted_conditions.append({
                            condition_type: condition_item_copy
                        })

                    condition_config = {"and": {"conditions": converted_conditions}}
            else:
                # Format słownika (jak w trigger) - użyj bezpośrednio
                condition_config = conditions

            debug(
                f"🔍 Konfiguracja warunków po konwersji: {condition_config}",
                message_logger=context.message_logger,
            )

            # Użyj factory do utworzenia i ewaluacji warunków
            condition = ConditionFactory.create_condition(
                condition_config, context.message_logger
            )
            result = await condition.evaluate(condition_context)
            result_data = condition.context['trigger_data']
            
            debug(f"Action Evaluate Condition result_data: {result_data}", message_logger=context.message_logger)

            debug(
                f"🔍 Ewaluacja warunków: {result}",
                message_logger=context.message_logger,
            )
            return result, result_data

        except Exception as e:
            error(
                f"❌ Błąd ewaluacji warunków: {e}",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(
                "evaluate_condition", f"Błąd ewaluacji warunków: {str(e)}", e
            )

    async def _execute_actions(
        self, actions: List[Dict[str, Any]], context: ActionContext
    ) -> List[Dict[str, Any]]:
        """
        Wykonuje listę akcji sekwencyjnie.

        Args:
            actions: Lista akcji do wykonania
            context: Kontekst wykonania

        Returns:
            Lista wyników wykonanych akcji

        Raises:
            ActionExecutionError: W przypadku błędu wykonania akcji
        """
        # Użyj ActionExecutor z orkiestratora zamiast tworzyć nową instancję
        # Dzięki temu mamy dostęp do wszystkich zarejestrowanych akcji (systemowych + użytkownika)
        action_executor = context.orchestrator._action_executor

        results = []

        for i, action_config in enumerate(actions):
            try:
                debug(
                    f"🎬 Wykonywanie akcji {i + 1}/{len(actions)}: {action_config.get('type')}",
                    message_logger=context.message_logger,
                )

                result = await action_executor.execute_action(action_config, context)

                results.append({
                    "action_index": i,
                    "action_type": action_config.get("type"),
                    "status": "success",
                    "result": result,
                })

                debug(
                    f"✅ Akcja {i + 1}/{len(actions)} zakończona pomyślnie",
                    message_logger=context.message_logger,
                )

            except Exception as e:
                error(
                    f"❌ Błąd wykonania akcji {i + 1}/{len(actions)} ({action_config.get('type')}): {e}",
                    message_logger=context.message_logger,
                )

                results.append({
                    "action_index": i,
                    "action_type": action_config.get("type"),
                    "status": "error",
                    "error": str(e),
                })

                # W przypadku błędu, przerwij wykonywanie następnych akcji
                raise ActionExecutionError(
                    "evaluate_condition",
                    f"Błąd wykonania akcji {i + 1} ({action_config.get('type')}): {str(e)}",
                    e,
                )

        return results
