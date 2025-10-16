"""
Testy jednostkowe dla EvaluateConditionAction.

Sprawdza implementację akcji warunkowej evaluate_condition,
która wykonuje różne akcje w zależności od wyniku ewaluacji warunków.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from avena_commons.orchestrator.actions import (
    ActionContext,
    ActionExecutionError,
    EvaluateConditionAction,
)
from avena_commons.util.logger import MessageLogger


class TestEvaluateConditionAction(unittest.TestCase):
    """Testy dla EvaluateConditionAction."""

    def setUp(self):
        """Przygotowanie środowiska testowego."""
        self.action = EvaluateConditionAction()
        self.mock_logger = MagicMock(spec=MessageLogger)
        self.mock_orchestrator = MagicMock()
        self.mock_orchestrator._state = {
            "client1": {"fsm_state": "RUNNING", "error": False},
            "client2": {"fsm_state": "IDLE", "error": False},
        }

        self.context = ActionContext(
            orchestrator=self.mock_orchestrator,
            message_logger=self.mock_logger,
            trigger_data={"source": "test", "transaction_id": "123"},
            scenario_name="test_scenario",
        )

    async def test_config_validation_success(self):
        """Test poprawnej walidacji konfiguracji."""
        action_config = {
            "conditions": [
                {"type": "client_state", "client": "client1", "state": "RUNNING"}
            ],
            "true_actions": [
                {"type": "log_event", "level": "info", "message": "Success"}
            ],
        }

        # Nie powinno rzucić wyjątku
        self.action._validate_config(action_config)

    def test_config_validation_missing_conditions(self):
        """Test walidacji przy braku warunków."""
        action_config = {
            "true_actions": [
                {"type": "log_event", "level": "info", "message": "Success"}
            ],
        }

        with self.assertRaises(ActionExecutionError) as cm:
            self.action._validate_config(action_config)

        self.assertIn("conditions", str(cm.exception))

    def test_config_validation_empty_conditions(self):
        """Test walidacji przy pustej liście warunków."""
        action_config = {
            "conditions": [],
            "true_actions": [
                {"type": "log_event", "level": "info", "message": "Success"}
            ],
        }

        with self.assertRaises(ActionExecutionError) as cm:
            self.action._validate_config(action_config)

        self.assertIn("niepustą listą", str(cm.exception))

    def test_config_validation_invalid_condition_structure(self):
        """Test walidacji przy nieprawidłowej strukturze warunku."""
        action_config = {
            "conditions": ["invalid_condition"],  # Powinien być dict
            "true_actions": [
                {"type": "log_event", "level": "info", "message": "Success"}
            ],
        }

        with self.assertRaises(ActionExecutionError) as cm:
            self.action._validate_config(action_config)

        self.assertIn("słownikiem", str(cm.exception))

    def test_config_validation_condition_missing_type(self):
        """Test walidacji przy braku typu w warunku."""
        action_config = {
            "conditions": [
                {"client": "client1", "state": "RUNNING"}  # Brak 'type'
            ],
            "true_actions": [
                {"type": "log_event", "level": "info", "message": "Success"}
            ],
        }

        with self.assertRaises(ActionExecutionError) as cm:
            self.action._validate_config(action_config)

        self.assertIn("pole 'type'", str(cm.exception))

    def test_config_validation_no_actions(self):
        """Test walidacji przy braku akcji."""
        action_config = {
            "conditions": [
                {"type": "client_state", "client": "client1", "state": "RUNNING"}
            ],
        }

        with self.assertRaises(ActionExecutionError) as cm:
            self.action._validate_config(action_config)

        self.assertIn("true_actions' lub 'false_actions", str(cm.exception))

    def test_config_validation_invalid_actions_structure(self):
        """Test walidacji przy nieprawidłowej strukturze akcji."""
        action_config = {
            "conditions": [
                {"type": "client_state", "client": "client1", "state": "RUNNING"}
            ],
            "true_actions": "invalid_actions",  # Powinno być listą
        }

        with self.assertRaises(ActionExecutionError) as cm:
            self.action._validate_config(action_config)

        self.assertIn("listą", str(cm.exception))

    def test_config_validation_action_missing_type(self):
        """Test walidacji przy braku typu w akcji."""
        action_config = {
            "conditions": [
                {"type": "client_state", "client": "client1", "state": "RUNNING"}
            ],
            "true_actions": [
                {"level": "info", "message": "Success"}  # Brak 'type'
            ],
        }

        with self.assertRaises(ActionExecutionError) as cm:
            self.action._validate_config(action_config)

        self.assertIn("pole 'type'", str(cm.exception))

    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ConditionFactory"
    )
    async def test_evaluate_single_condition_true(self, mock_factory):
        """Test ewaluacji pojedynczego warunku (prawda)."""
        # Mock condition
        mock_condition = AsyncMock()
        mock_condition.evaluate.return_value = True
        mock_factory.create_condition.return_value = mock_condition

        conditions = [{"type": "client_state", "client": "client1", "state": "RUNNING"}]

        result = await self.action._evaluate_conditions(conditions, self.context)

        self.assertTrue(result)
        mock_factory.create_condition.assert_called_once()
        mock_condition.evaluate.assert_called_once()

    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ConditionFactory"
    )
    async def test_evaluate_single_condition_false(self, mock_factory):
        """Test ewaluacji pojedynczego warunku (fałsz)."""
        # Mock condition
        mock_condition = AsyncMock()
        mock_condition.evaluate.return_value = False
        mock_factory.create_condition.return_value = mock_condition

        conditions = [{"type": "client_state", "client": "client1", "state": "STOPPED"}]

        result = await self.action._evaluate_conditions(conditions, self.context)

        self.assertFalse(result)
        mock_factory.create_condition.assert_called_once()
        mock_condition.evaluate.assert_called_once()

    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ConditionFactory"
    )
    async def test_evaluate_multiple_conditions_and(self, mock_factory):
        """Test ewaluacji wielu warunków (logika AND)."""
        # Mock condition
        mock_condition = AsyncMock()
        mock_condition.evaluate.return_value = True
        mock_factory.create_condition.return_value = mock_condition

        conditions = [
            {"type": "client_state", "client": "client1", "state": "RUNNING"},
            {"type": "client_state", "client": "client2", "state": "IDLE"},
        ]

        result = await self.action._evaluate_conditions(conditions, self.context)

        self.assertTrue(result)
        mock_factory.create_condition.assert_called_once()
        # Sprawdź że została utworzona logika AND
        call_args = mock_factory.create_condition.call_args[0][0]
        self.assertIn("and", call_args)
        self.assertEqual(len(call_args["and"]["conditions"]), 2)

    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ActionExecutor"
    )
    async def test_execute_actions_success(self, mock_executor_class):
        """Test pomyślnego wykonania akcji."""
        # Mock executor
        mock_executor = AsyncMock()
        mock_executor.execute_action.return_value = {"status": "success"}
        mock_executor_class.return_value = mock_executor

        actions = [
            {"type": "log_event", "level": "info", "message": "Test1"},
            {"type": "log_event", "level": "info", "message": "Test2"},
        ]

        results = await self.action._execute_actions(actions, self.context)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["status"], "success")
        self.assertEqual(results[1]["status"], "success")
        self.assertEqual(mock_executor.execute_action.call_count, 2)

    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ActionExecutor"
    )
    async def test_execute_actions_failure(self, mock_executor_class):
        """Test błędu podczas wykonania akcji."""
        # Mock executor z błędem
        mock_executor = AsyncMock()
        mock_executor.execute_action.side_effect = Exception("Test error")
        mock_executor_class.return_value = mock_executor

        actions = [
            {"type": "log_event", "level": "info", "message": "Test"},
        ]

        with self.assertRaises(ActionExecutionError) as cm:
            await self.action._execute_actions(actions, self.context)

        self.assertIn("Test error", str(cm.exception))

    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ConditionFactory"
    )
    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ActionExecutor"
    )
    async def test_full_execute_true_condition(self, mock_executor_class, mock_factory):
        """Test pełnego wykonania z warunkiem prawdą."""
        # Mock condition (prawda)
        mock_condition = AsyncMock()
        mock_condition.evaluate.return_value = True
        mock_factory.create_condition.return_value = mock_condition

        # Mock executor
        mock_executor = AsyncMock()
        mock_executor.execute_action.return_value = {"status": "success"}
        mock_executor_class.return_value = mock_executor

        action_config = {
            "conditions": [
                {"type": "client_state", "client": "client1", "state": "RUNNING"}
            ],
            "true_actions": [
                {"type": "log_event", "level": "info", "message": "Success"}
            ],
            "false_actions": [
                {"type": "log_event", "level": "error", "message": "Failure"}
            ],
        }

        result = await self.action.execute(action_config, self.context)

        # Sprawdź wynik
        self.assertTrue(result["condition_result"])
        self.assertEqual(result["executed_branch"], "true_actions")
        self.assertEqual(result["executed_actions_count"], 1)

        # Sprawdź że wykonana została tylko true_actions
        mock_executor.execute_action.assert_called_once()
        call_args = mock_executor.execute_action.call_args[0][0]
        self.assertEqual(call_args["message"], "Success")

    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ConditionFactory"
    )
    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ActionExecutor"
    )
    async def test_full_execute_false_condition(
        self, mock_executor_class, mock_factory
    ):
        """Test pełnego wykonania z warunkiem fałsz."""
        # Mock condition (fałsz)
        mock_condition = AsyncMock()
        mock_condition.evaluate.return_value = False
        mock_factory.create_condition.return_value = mock_condition

        # Mock executor
        mock_executor = AsyncMock()
        mock_executor.execute_action.return_value = {"status": "success"}
        mock_executor_class.return_value = mock_executor

        action_config = {
            "conditions": [
                {"type": "client_state", "client": "client1", "state": "STOPPED"}
            ],
            "true_actions": [
                {"type": "log_event", "level": "info", "message": "Success"}
            ],
            "false_actions": [
                {"type": "log_event", "level": "error", "message": "Failure"}
            ],
        }

        result = await self.action.execute(action_config, self.context)

        # Sprawdź wynik
        self.assertFalse(result["condition_result"])
        self.assertEqual(result["executed_branch"], "false_actions")
        self.assertEqual(result["executed_actions_count"], 1)

        # Sprawdź że wykonana została tylko false_actions
        mock_executor.execute_action.assert_called_once()
        call_args = mock_executor.execute_action.call_args[0][0]
        self.assertEqual(call_args["message"], "Failure")

    @patch(
        "avena_commons.orchestrator.actions.evaluate_condition_action.ConditionFactory"
    )
    async def test_full_execute_no_actions_for_branch(self, mock_factory):
        """Test wykonania gdy brak akcji dla danej gałęzi."""
        # Mock condition (prawda)
        mock_condition = AsyncMock()
        mock_condition.evaluate.return_value = True
        mock_factory.create_condition.return_value = mock_condition

        action_config = {
            "conditions": [
                {"type": "client_state", "client": "client1", "state": "RUNNING"}
            ],
            "false_actions": [  # Tylko false_actions, brak true_actions
                {"type": "log_event", "level": "error", "message": "Failure"}
            ],
        }

        result = await self.action.execute(action_config, self.context)

        # Sprawdź wynik
        self.assertTrue(result["condition_result"])
        self.assertEqual(result["executed_branch"], "true_actions")
        self.assertEqual(result["executed_actions_count"], 0)  # Brak akcji do wykonania


if __name__ == "__main__":
    unittest.main()
