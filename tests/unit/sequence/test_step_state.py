"""
Unit tests for the StepState enum from avena_commons.sequence.step_state.

This module tests the step state enum functionality including:
- Enum values and their string representations
- State transitions and comparisons
- Type checking and validation

All tests follow the avena_commons testing guidelines with proper
fixtures, comprehensive coverage, and clear test organization.
"""

import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))


from avena_commons.sequence.step_state import StepState


class TestStepState:
    """Test cases for the StepState enum."""

    def test_step_state_values(self):
        """Test that all StepState enum values are correctly defined."""
        assert StepState.PREPARE == "PREPARE"
        assert StepState.EXECUTE == "EXECUTE"
        assert StepState.DONE == "DONE"
        assert StepState.TEST_FAILED == "TEST_FAILED"
        assert StepState.ERROR == "ERROR"

    def test_step_state_inheritance(self):
        """Test that StepState inherits from both str and Enum."""
        assert isinstance(StepState.PREPARE, str)
        assert isinstance(StepState.PREPARE, StepState)

        # Test that it can be used as a string
        assert StepState.PREPARE + "_suffix" == "PREPARE_suffix"

        # Test that it has enum properties
        assert hasattr(StepState.PREPARE, "name")
        assert hasattr(StepState.PREPARE, "value")

    def test_step_state_name_and_value(self):
        """Test that name and value properties work correctly."""
        assert StepState.PREPARE.name == "PREPARE"
        assert StepState.PREPARE.value == "PREPARE"

        assert StepState.EXECUTE.name == "EXECUTE"
        assert StepState.EXECUTE.value == "EXECUTE"

        assert StepState.DONE.name == "DONE"
        assert StepState.DONE.value == "DONE"

        assert StepState.TEST_FAILED.name == "TEST_FAILED"
        assert StepState.TEST_FAILED.value == "TEST_FAILED"

        assert StepState.ERROR.name == "ERROR"
        assert StepState.ERROR.value == "ERROR"

    def test_step_state_equality(self):
        """Test equality comparisons with strings and other enums."""
        # Test equality with string values
        assert StepState.PREPARE == "PREPARE"
        assert StepState.EXECUTE == "EXECUTE"
        assert StepState.DONE == "DONE"
        assert StepState.TEST_FAILED == "TEST_FAILED"
        assert StepState.ERROR == "ERROR"

        # Test inequality
        assert StepState.PREPARE != "EXECUTE"
        assert StepState.PREPARE != StepState.EXECUTE

        # Test equality with same enum values
        assert StepState.PREPARE == StepState.PREPARE

    def test_step_state_string_representation(self):
        """Test string representation of StepState values."""
        assert str(StepState.PREPARE) == "PREPARE"
        assert str(StepState.EXECUTE) == "EXECUTE"
        assert str(StepState.DONE) == "DONE"
        assert str(StepState.TEST_FAILED) == "TEST_FAILED"
        assert str(StepState.ERROR) == "ERROR"

    def test_step_state_repr(self):
        """Test repr representation of StepState values."""
        assert repr(StepState.PREPARE) == "'PREPARE'"
        assert repr(StepState.EXECUTE) == "'EXECUTE'"
        assert repr(StepState.DONE) == "'DONE'"
        assert repr(StepState.TEST_FAILED) == "'TEST_FAILED'"
        assert repr(StepState.ERROR) == "'ERROR'"

    def test_step_state_iteration(self):
        """Test that all StepState values can be iterated."""
        all_states = list(StepState)
        expected_states = [
            StepState.PREPARE,
            StepState.EXECUTE,
            StepState.DONE,
            StepState.TEST_FAILED,
            StepState.ERROR,
        ]

        assert len(all_states) == 5
        for state in expected_states:
            assert state in all_states

    def test_step_state_membership(self):
        """Test membership testing with StepState values."""
        valid_states = ["PREPARE", "EXECUTE", "DONE", "TEST_FAILED", "ERROR"]

        for state_value in valid_states:
            # Test that string values exist in enum
            matching_states = [s for s in StepState if s.value == state_value]
            assert len(matching_states) == 1

        # Test invalid state
        invalid_states = ["INVALID", "RUNNING", "PENDING"]
        for invalid_state in invalid_states:
            matching_states = [s for s in StepState if s.value == invalid_state]
            assert len(matching_states) == 0

    def test_step_state_hash(self):
        """Test that StepState values are hashable and can be used in sets/dicts."""
        # Test that enum values can be used as dictionary keys
        state_dict = {
            StepState.PREPARE: "preparing",
            StepState.EXECUTE: "executing",
            StepState.DONE: "completed",
            StepState.TEST_FAILED: "test failed",
            StepState.ERROR: "error occurred",
        }

        assert state_dict[StepState.PREPARE] == "preparing"
        assert state_dict[StepState.EXECUTE] == "executing"
        assert state_dict[StepState.DONE] == "completed"
        assert state_dict[StepState.TEST_FAILED] == "test failed"
        assert state_dict[StepState.ERROR] == "error occurred"

        # Test that enum values can be used in sets
        state_set = {StepState.PREPARE, StepState.EXECUTE, StepState.DONE}
        assert len(state_set) == 3
        assert StepState.PREPARE in state_set
        assert StepState.ERROR not in state_set

    def test_step_state_comparison_with_strings(self):
        """Test comparison operations with string values."""
        # Test that enum values can be compared with strings for sorting
        states_with_strings = [
            ("PREPARE", StepState.PREPARE),
            ("EXECUTE", StepState.EXECUTE),
            ("DONE", StepState.DONE),
        ]

        for string_val, enum_val in states_with_strings:
            assert string_val == enum_val
            assert enum_val == string_val

    def test_step_state_json_serialization(self):
        """Test that StepState values can be serialized to JSON-compatible formats."""
        import json

        # Test direct serialization (should work since it's a string enum)
        for state in StepState:
            json_str = json.dumps(state)
            assert json_str == f'"{state.value}"'

            # Test deserialization
            deserialized = json.loads(json_str)
            assert deserialized == state.value
            assert deserialized == state

    def test_step_state_case_sensitivity(self):
        """Test case sensitivity of StepState values."""
        # StepState should be case sensitive
        assert StepState.PREPARE != "prepare"
        assert StepState.PREPARE != "Prepare"
        assert StepState.EXECUTE != "execute"
        assert StepState.DONE != "done"
        assert StepState.TEST_FAILED != "test_failed"
        assert StepState.ERROR != "error"

    def test_step_state_logical_progression(self):
        """Test logical progression of states in typical workflow."""
        # Define typical state progression
        typical_progression = [StepState.PREPARE, StepState.EXECUTE, StepState.DONE]

        error_states = [StepState.TEST_FAILED, StepState.ERROR]

        # Test that we have both success and error paths
        assert len(typical_progression) == 3
        assert len(error_states) == 2

        # Test that all defined states are accounted for
        all_defined = typical_progression + error_states
        assert len(all_defined) == len(list(StepState))


class TestStepStateIntegration:
    """Integration tests for StepState enum."""

    def test_step_state_with_pydantic_models(self):
        """Test StepState integration with Pydantic models."""
        from pydantic import BaseModel

        class TestModel(BaseModel):
            current_state: StepState
            previous_state: StepState = StepState.PREPARE

        # Test model creation with enum values
        model = TestModel(current_state=StepState.EXECUTE)
        assert model.current_state == StepState.EXECUTE
        assert model.previous_state == StepState.PREPARE

        # Test model creation with string values
        model2 = TestModel(current_state="DONE", previous_state="ERROR")
        assert model2.current_state == StepState.DONE
        assert model2.previous_state == StepState.ERROR

        # Test model serialization
        model_dict = model.model_dump()
        assert model_dict["current_state"] == "EXECUTE"
        assert model_dict["previous_state"] == "PREPARE"

    def test_step_state_state_machine_simulation(self):
        """Test StepState in a simulated state machine context."""

        class SimpleStateMachine:
            def __init__(self):
                self.current_state = StepState.PREPARE
                self.state_history = [StepState.PREPARE]

            def transition_to(self, new_state: StepState):
                if self._is_valid_transition(self.current_state, new_state):
                    self.current_state = new_state
                    self.state_history.append(new_state)
                    return True
                return False

            def _is_valid_transition(
                self, from_state: StepState, to_state: StepState
            ) -> bool:
                valid_transitions = {
                    StepState.PREPARE: [StepState.EXECUTE, StepState.ERROR],
                    StepState.EXECUTE: [
                        StepState.DONE,
                        StepState.TEST_FAILED,
                        StepState.ERROR,
                    ],
                    StepState.DONE: [],  # Terminal state
                    StepState.TEST_FAILED: [
                        StepState.PREPARE,
                        StepState.ERROR,
                    ],  # Can retry
                    StepState.ERROR: [],  # Terminal state
                }
                return to_state in valid_transitions.get(from_state, [])

        # Test state machine with valid transitions
        sm = SimpleStateMachine()
        assert sm.current_state == StepState.PREPARE

        # Valid transition: PREPARE -> EXECUTE
        assert sm.transition_to(StepState.EXECUTE) is True
        assert sm.current_state == StepState.EXECUTE

        # Valid transition: EXECUTE -> DONE
        assert sm.transition_to(StepState.DONE) is True
        assert sm.current_state == StepState.DONE

        # Invalid transition: DONE -> EXECUTE (done is terminal)
        assert sm.transition_to(StepState.EXECUTE) is False
        assert sm.current_state == StepState.DONE  # Should remain unchanged

        # Test error path
        sm2 = SimpleStateMachine()
        assert sm2.transition_to(StepState.EXECUTE) is True
        assert sm2.transition_to(StepState.TEST_FAILED) is True
        assert (
            sm2.transition_to(StepState.PREPARE) is True
        )  # Can retry after test failure

    def test_step_state_with_database_simulation(self):
        """Test StepState enum in database-like storage scenarios."""
        # Simulate storing/retrieving from database
        database_records = []

        def save_step_status(step_id: int, state: StepState):
            # Simulate saving to database (stored as string)
            database_records.append({"step_id": step_id, "state": str(state)})

        def load_step_status(step_id: int) -> StepState:
            # Simulate loading from database and converting back to enum
            for record in database_records:
                if record["step_id"] == step_id:
                    return StepState(record["state"])
            raise ValueError(f"Step {step_id} not found")

        # Test saving and loading
        save_step_status(1, StepState.PREPARE)
        save_step_status(2, StepState.EXECUTE)
        save_step_status(3, StepState.DONE)

        assert load_step_status(1) == StepState.PREPARE
        assert load_step_status(2) == StepState.EXECUTE
        assert load_step_status(3) == StepState.DONE

        # Test that loaded values are proper enum instances
        loaded_state = load_step_status(1)
        assert isinstance(loaded_state, StepState)
        assert loaded_state.name == "PREPARE"
        assert loaded_state.value == "PREPARE"
