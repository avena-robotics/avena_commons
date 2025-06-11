"""
Unit tests for the sequence module from avena_commons.sequence.sequence.

This module tests the sequence functionality including:
- SequenceStepStatus class
- SequenceStatus class
- Sequence class with step management
- State transitions and event processing
- Integration with MessageLogger

All tests follow the avena_commons testing guidelines with proper
fixtures, comprehensive coverage, and clear test organization.
"""

import sys
from enum import Enum
from pathlib import Path
from unittest.mock import Mock, patch

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest
from pydantic import ValidationError

from avena_commons.sequence.sequence import Sequence, SequenceStatus, SequenceStepStatus
from avena_commons.sequence.step_state import StepState
from avena_commons.util.logger import MessageLogger


class TestSequenceEnum(Enum):
    """Test enum for sequence testing."""

    STEP_1 = 1
    STEP_2 = 2
    STEP_3 = 3
    STEP_4 = 4


class TestSimpleEnum(Enum):
    """Simple test enum with fewer steps."""

    START = 1
    MIDDLE = 2
    END = 3


class TestSequenceStepStatus:
    """Test cases for the SequenceStepStatus class."""

    def test_step_status_initialization_defaults(self):
        """Test SequenceStepStatus initialization with default values."""
        step_status = SequenceStepStatus(step_id=1)

        assert step_status.step_id == 1
        assert step_status.fsm_state == StepState.PREPARE
        assert step_status.retry_count == 0
        assert step_status.params == {}

    def test_step_status_initialization_custom_values(self):
        """Test SequenceStepStatus initialization with custom values."""
        params = {"key1": "value1", "key2": 42}
        step_status = SequenceStepStatus(
            step_id=5, fsm_state=StepState.EXECUTE, retry_count=3, params=params
        )

        assert step_status.step_id == 5
        assert step_status.fsm_state == StepState.EXECUTE
        assert step_status.retry_count == 3
        assert step_status.params == params

    def test_step_status_fsm_state_validation(self):
        """Test SequenceStepStatus fsm_state validation."""
        # Valid states
        for state in StepState:
            step_status = SequenceStepStatus(step_id=1, fsm_state=state)
            assert step_status.fsm_state == state

    def test_step_status_params_types(self):
        """Test SequenceStepStatus params can handle various types."""
        complex_params = {
            "string": "value",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "list": [1, 2, 3],
            "dict": {"nested": "value"},
        }

        step_status = SequenceStepStatus(step_id=1, params=complex_params)
        assert step_status.params == complex_params

    def test_step_status_model_dump(self):
        """Test SequenceStepStatus serialization."""
        step_status = SequenceStepStatus(
            step_id=2, fsm_state=StepState.DONE, retry_count=1, params={"test": "value"}
        )

        dumped = step_status.model_dump()
        expected = {
            "step_id": 2,
            "fsm_state": "DONE",
            "retry_count": 1,
            "params": {"test": "value"},
        }
        assert dumped == expected

    def test_step_status_model_validation(self):
        """Test SequenceStepStatus model validation."""
        # Test invalid step_id type
        with pytest.raises(ValidationError):
            SequenceStepStatus(step_id="invalid")

        # Test invalid retry_count type
        with pytest.raises(ValidationError):
            SequenceStepStatus(step_id=1, retry_count="invalid")


class TestSequenceStatus:
    """Test cases for the SequenceStatus class."""

    def test_sequence_status_initialization_with_enum_class(self):
        """Test SequenceStatus initialization with enum class."""
        steps = {
            1: SequenceStepStatus(step_id=1),
            2: SequenceStepStatus(step_id=2),
            3: SequenceStepStatus(step_id=3),
        }

        status = SequenceStatus(
            sequence_enum=TestSequenceEnum, current_step=1, steps=steps
        )

        assert status.sequence_enum == "TestSequenceEnum"
        assert status.current_step == 1
        assert status.steps == steps
        assert status.finished is False

    def test_sequence_status_initialization_with_string(self):
        """Test SequenceStatus initialization with string enum name."""
        steps = {1: SequenceStepStatus(step_id=1)}

        status = SequenceStatus(sequence_enum="MySequence", current_step=1, steps=steps)

        assert status.sequence_enum == "MySequence"
        assert status.current_step == 1
        assert status.steps == steps

    def test_sequence_status_enum_validator_invalid_type(self):
        """Test SequenceStatus enum validator with invalid types."""
        steps = {1: SequenceStepStatus(step_id=1)}

        with pytest.raises(ValidationError):
            SequenceStatus(
                sequence_enum=123,  # Invalid type
                current_step=1,
                steps=steps,
            )

    def test_sequence_status_is_finished_method(self):
        """Test SequenceStatus is_finished method."""
        steps = {1: SequenceStepStatus(step_id=1)}

        # Test not finished
        status = SequenceStatus(
            sequence_enum="Test", current_step=1, steps=steps, finished=False
        )
        assert status.is_finished() is False

        # Test finished
        status.finished = True
        assert status.is_finished() is True

    def test_sequence_status_get_current_step_status_normal(self):
        """Test get_current_step_status with normal step."""
        step_1 = SequenceStepStatus(step_id=1, fsm_state=StepState.EXECUTE)
        step_2 = SequenceStepStatus(step_id=2, fsm_state=StepState.PREPARE)
        steps = {1: step_1, 2: step_2}

        status = SequenceStatus(sequence_enum="Test", current_step=1, steps=steps)

        current = status.get_current_step_status
        assert current == step_1
        assert current.step_id == 1
        assert current.fsm_state == StepState.EXECUTE

    def test_sequence_status_get_current_step_status_finished(self):
        """Test get_current_step_status when sequence is finished (step 0)."""
        steps = {1: SequenceStepStatus(step_id=1)}

        status = SequenceStatus(
            sequence_enum="Test",
            current_step=0,  # 0 indicates finished
            steps=steps,
        )

        current = status.get_current_step_status
        assert current.step_id == 0
        assert current.fsm_state == StepState.DONE

    def test_sequence_status_model_dump(self):
        """Test SequenceStatus serialization."""
        steps = {
            1: SequenceStepStatus(step_id=1, fsm_state=StepState.EXECUTE),
            2: SequenceStepStatus(step_id=2, fsm_state=StepState.PREPARE),
        }

        status = SequenceStatus(
            sequence_enum=TestSequenceEnum, current_step=1, steps=steps, finished=True
        )

        dumped = status.model_dump()
        assert dumped["sequence_enum"] == "TestSequenceEnum"
        assert dumped["current_step"] == 1
        assert dumped["finished"] is True
        assert "steps" in dumped
        assert len(dumped["steps"]) == 2


class TestSequence:
    """Test cases for the Sequence class."""

    def test_sequence_initialization_new_style(self):
        """Test Sequence initialization with new style (enum_class parameter)."""
        sequence = Sequence(
            produkt_id=123,
            enum_class=TestSequenceEnum,
            initial_step=1,
            parametry={"test": "value"},
        )

        assert sequence.produkt_id == 123
        assert sequence.sequence_enum == "TestSequenceEnum"
        assert sequence.status.current_step == 1
        assert sequence.parametry == {"test": "value"}

        # Check that steps were created for all enum values
        expected_steps = {1, 2, 3, 4}  # Values from TestSequenceEnum
        assert set(sequence.status.steps.keys()) == expected_steps

        # Check that all steps start in PREPARE state
        for step_status in sequence.status.steps.values():
            assert step_status.fsm_state == StepState.PREPARE

    def test_sequence_initialization_old_style(self):
        """Test Sequence initialization with old style (backward compatibility)."""
        steps = {1: SequenceStepStatus(step_id=1), 2: SequenceStepStatus(step_id=2)}
        status = SequenceStatus(
            sequence_enum="TestSequence", current_step=1, steps=steps
        )

        with patch("builtins.globals", return_value={"TestSequence": TestSequenceEnum}):
            sequence = Sequence(
                produkt_id=456,
                sequence_enum="TestSequence",
                status=status,
                parametry={"old": "style"},
            )

        assert sequence.produkt_id == 456
        assert sequence.sequence_enum == "TestSequence"
        assert sequence.parametry == {"old": "style"}

    def test_sequence_initialization_missing_enum_class(self):
        """Test Sequence initialization error when enum_class is missing."""
        with pytest.raises(ValueError, match="Parametr 'enum_class' jest wymagany"):
            Sequence(produkt_id=123)

    def test_sequence_process_event_success(self):
        """Test process_event with success result."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        mock_logger = Mock(spec=MessageLogger)

        # Set current step to EXECUTE state
        current_step = sequence.status.get_current_step_status
        current_step.fsm_state = StepState.EXECUTE

        with patch.object(sequence, "_log_state_change") as mock_log:
            sequence.process_event(123, "success", mock_logger)

        assert current_step.fsm_state == StepState.DONE
        mock_log.assert_called_once_with(StepState.DONE, mock_logger)

    def test_sequence_process_event_failure(self):
        """Test process_event with failure result."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        current_step = sequence.status.get_current_step_status

        with patch.object(sequence, "_log_state_change") as mock_log:
            sequence.process_event(123, "failure")

        assert current_step.fsm_state == StepState.ERROR
        mock_log.assert_called_once_with(StepState.ERROR, None)

    def test_sequence_process_event_test_failed(self):
        """Test process_event with test_failed result."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        current_step = sequence.status.get_current_step_status

        with patch.object(sequence, "_log_state_change") as mock_log:
            sequence.process_event(123, "test_failed")

        assert current_step.fsm_state == StepState.TEST_FAILED
        mock_log.assert_called_once_with(StepState.TEST_FAILED, None)

    def test_sequence_process_event_wrong_product_id(self):
        """Test process_event with wrong product ID."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        mock_logger = Mock(spec=MessageLogger)

        with patch("avena_commons.sequence.sequence.error") as mock_error:
            sequence.process_event(456, "success", mock_logger)  # Wrong ID

        mock_error.assert_called_once()
        call_args = mock_error.call_args[0][0]
        assert "Produkt ID mismatch" in call_args
        assert "Expected 123, got 456" in call_args

    def test_sequence_run_step(self):
        """Test run_step method."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        mock_logger = Mock(spec=MessageLogger)

        # Ensure current step is in PREPARE state
        current_step = sequence.status.get_current_step_status
        assert current_step.fsm_state == StepState.PREPARE

        with patch.object(sequence, "_do_execute") as mock_execute:
            sequence.run_step(mock_logger)

        mock_execute.assert_called_once_with(current_step, mock_logger)

    def test_sequence_run_step_not_in_prepare(self):
        """Test run_step when step is not in PREPARE state."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)

        # Set step to EXECUTE state
        current_step = sequence.status.get_current_step_status
        current_step.fsm_state = StepState.EXECUTE

        with patch.object(sequence, "_do_execute") as mock_execute:
            sequence.run_step()

        # Should not call _do_execute
        mock_execute.assert_not_called()

    def test_sequence_rerun_step(self):
        """Test rerun_step method."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        mock_logger = Mock(spec=MessageLogger)

        current_step = sequence.status.get_current_step_status
        initial_retry_count = current_step.retry_count

        with patch.object(sequence, "_do_prepare") as mock_prepare:
            sequence.rerun_step(mock_logger)

        assert current_step.retry_count == initial_retry_count + 1
        mock_prepare.assert_called_once_with(current_step, mock_logger)

    def test_sequence_error_step(self):
        """Test error_step method."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        mock_logger = Mock(spec=MessageLogger)

        current_step = sequence.status.get_current_step_status

        with patch.object(sequence, "_do_error") as mock_error:
            sequence.error_step(mock_logger)

        mock_error.assert_called_once_with(current_step, mock_logger)

    def test_sequence_done_step(self):
        """Test done_step method."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        mock_logger = Mock(spec=MessageLogger)

        current_step = sequence.status.get_current_step_status

        with patch.object(sequence, "_do_done") as mock_done:
            sequence.done_step(mock_logger)

        mock_done.assert_called_once_with(current_step, mock_logger)

    def test_sequence_next_step_normal(self):
        """Test next_step method with normal progression."""
        sequence = Sequence(produkt_id=123, enum_class=TestSimpleEnum)  # 3 steps
        mock_logger = Mock(spec=MessageLogger)

        # Start at step 1, should advance to step 2
        assert sequence.status.current_step == 1

        with patch.object(sequence, "_do_prepare") as mock_prepare:
            sequence.next_step(mock_logger)

        assert sequence.status.current_step == 2
        assert sequence.status.finished is False
        mock_prepare.assert_called_once_with(sequence.status.steps[2], mock_logger)

    def test_sequence_next_step_finish(self):
        """Test next_step method when reaching end of sequence."""
        sequence = Sequence(produkt_id=123, enum_class=TestSimpleEnum)  # 3 steps

        # Move to last step
        sequence.status.current_step = 3

        sequence.next_step()

        # Should finish sequence since we were at the last step
        assert sequence.status.finished is True

    def test_sequence_go_to_step(self):
        """Test go_to_step method."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        mock_logger = Mock(spec=MessageLogger)

        with patch.object(sequence, "_do_prepare") as mock_prepare:
            sequence.go_to_step(3, mock_logger)

        assert sequence.status.current_step == 3
        mock_prepare.assert_called_once_with(sequence.status.steps[3], mock_logger)

    def test_sequence_end(self):
        """Test end method."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        mock_logger = Mock(spec=MessageLogger)

        with patch("avena_commons.sequence.sequence.info") as mock_info:
            sequence.end(mock_logger)

        assert sequence.status.finished is True
        assert sequence.status.current_step == 0
        mock_info.assert_called_once()
        call_args = mock_info.call_args[0][0]
        assert "Sekwencja" in call_args
        assert "zakonczona" in call_args

    def test_sequence_private_methods(self):
        """Test private state change methods."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        step_status = sequence.status.get_current_step_status
        mock_logger = Mock(spec=MessageLogger)

        # Test _do_prepare
        with patch.object(sequence, "_log_state_change") as mock_log:
            sequence._do_prepare(step_status, mock_logger)
        assert step_status.fsm_state == StepState.PREPARE
        mock_log.assert_called_once_with(StepState.PREPARE, mock_logger)

        # Test _do_execute
        mock_log.reset_mock()
        with patch.object(sequence, "_log_state_change") as mock_log:
            sequence._do_execute(step_status, mock_logger)
        assert step_status.fsm_state == StepState.EXECUTE
        mock_log.assert_called_once_with(StepState.EXECUTE, mock_logger)

        # Test _do_done
        mock_log.reset_mock()
        with patch.object(sequence, "_log_state_change") as mock_log:
            sequence._do_done(step_status, mock_logger)
        assert step_status.fsm_state == StepState.DONE
        mock_log.assert_called_once_with(StepState.DONE, mock_logger)

    def test_sequence_get_step_name(self):
        """Test _get_step_name method."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)

        # Test with valid step IDs
        assert sequence._get_step_name(1) == "STEP_1"
        assert sequence._get_step_name(2) == "STEP_2"
        assert sequence._get_step_name(3) == "STEP_3"
        assert sequence._get_step_name(4) == "STEP_4"

        # Test with invalid step ID
        assert sequence._get_step_name(999) == "STEP_999"

    def test_sequence_get_step_name_no_enum(self):
        """Test _get_step_name when enum class is not available."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)

        # Remove the private enum class attribute
        delattr(sequence, "_Sequence__enum_class")

        # Should return generic name
        assert sequence._get_step_name(1) == "STEP_1"

    def test_sequence_log_state_change(self):
        """Test _log_state_change method."""
        sequence = Sequence(produkt_id=123, enum_class=TestSequenceEnum)
        sequence.status.current_step = 2
        mock_logger = Mock(spec=MessageLogger)

        with patch("avena_commons.sequence.sequence.info") as mock_info:
            sequence._log_state_change(StepState.EXECUTE, mock_logger)

        mock_info.assert_called_once()
        call_args = mock_info.call_args[0][0]
        assert "TestSequenceEnum.STEP_2.EXECUTE" in call_args
        assert "produkt_id=123" in call_args


class TestSequenceIntegration:
    """Integration tests for the Sequence class."""

    def test_sequence_full_workflow(self):
        """Test complete sequence workflow from start to finish."""
        sequence = Sequence(
            produkt_id=42, enum_class=TestSimpleEnum, parametry={"workflow": "test"}
        )

        mock_logger = Mock(spec=MessageLogger)

        # Initial state
        assert sequence.status.current_step == 1
        assert sequence.status.get_current_step_status.fsm_state == StepState.PREPARE
        assert sequence.status.finished is False

        # Step 1: PREPARE -> EXECUTE -> DONE
        sequence.run_step(mock_logger)
        assert sequence.status.get_current_step_status.fsm_state == StepState.EXECUTE

        sequence.process_event(42, "success", mock_logger)
        assert sequence.status.get_current_step_status.fsm_state == StepState.DONE

        # Move to step 2
        sequence.next_step(mock_logger)
        assert sequence.status.current_step == 2
        assert sequence.status.get_current_step_status.fsm_state == StepState.PREPARE

        # Step 2: Test failure and retry
        sequence.run_step(mock_logger)
        sequence.process_event(42, "test_failed", mock_logger)
        assert (
            sequence.status.get_current_step_status.fsm_state == StepState.TEST_FAILED
        )

        # Retry step 2
        sequence.rerun_step(mock_logger)
        assert sequence.status.get_current_step_status.retry_count == 1
        assert sequence.status.get_current_step_status.fsm_state == StepState.PREPARE

        # Complete step 2 successfully
        sequence.run_step(mock_logger)
        sequence.process_event(42, "success", mock_logger)

        # Move to step 3 (final step)
        sequence.next_step(mock_logger)
        assert sequence.status.current_step == 3

        # Complete final step
        sequence.run_step(mock_logger)
        sequence.process_event(42, "success", mock_logger)

        # End sequence
        sequence.end(mock_logger)
        assert sequence.status.finished is True
        assert sequence.status.current_step == 0

    def test_sequence_error_handling_workflow(self):
        """Test sequence workflow with error handling."""
        sequence = Sequence(produkt_id=123, enum_class=TestSimpleEnum)

        # Start step and encounter error
        sequence.run_step()
        sequence.process_event(123, "failure")

        current_step = sequence.status.get_current_step_status
        assert current_step.fsm_state == StepState.ERROR

        # Can explicitly set error state
        sequence.error_step()

        # Can jump to different step after error
        sequence.go_to_step(3)
        assert sequence.status.current_step == 3

    def test_sequence_serialization_workflow(self):
        """Test sequence serialization and state persistence."""
        # Create and modify sequence
        sequence = Sequence(
            produkt_id=999,
            enum_class=TestSequenceEnum,
            initial_step=2,
            parametry={"serialization": "test"},
        )

        # Modify some state
        sequence.status.steps[2].fsm_state = StepState.EXECUTE
        sequence.status.steps[2].retry_count = 2
        sequence.status.steps[2].params = {"custom": "data"}

        # Serialize
        serialized = sequence.model_dump()

        # Verify serialized data
        assert serialized["produkt_id"] == 999
        assert serialized["sequence_enum"] == "TestSequenceEnum"
        assert serialized["parametry"]["serialization"] == "test"
        assert serialized["status"]["current_step"] == 2
        assert serialized["status"]["steps"]["2"]["fsm_state"] == "EXECUTE"
        assert serialized["status"]["steps"]["2"]["retry_count"] == 2
        assert serialized["status"]["steps"]["2"]["params"]["custom"] == "data"

    def test_sequence_with_complex_enum(self):
        """Test sequence with more complex enum scenarios."""

        class ComplexEnum(Enum):
            INIT = 1
            VALIDATE = 2
            PROCESS = 3
            VERIFY = 4
            CLEANUP = 5
            FINALIZE = 6

        sequence = Sequence(produkt_id=777, enum_class=ComplexEnum)

        # Verify all steps were created
        assert len(sequence.status.steps) == 6
        expected_steps = {1, 2, 3, 4, 5, 6}
        assert set(sequence.status.steps.keys()) == expected_steps

        # Test jumping around in sequence
        sequence.go_to_step(4)  # VERIFY
        assert sequence.status.current_step == 4
        assert sequence._get_step_name(4) == "VERIFY"

        sequence.go_to_step(1)  # Back to INIT
        assert sequence.status.current_step == 1
        assert sequence._get_step_name(1) == "INIT"

    def test_sequence_edge_cases(self):
        """Test sequence edge cases and boundary conditions."""
        sequence = Sequence(produkt_id=0, enum_class=TestSimpleEnum)  # Zero product ID

        # Test with zero/negative product IDs in events
        sequence.process_event(0, "success")  # Should work

        # Test with mismatched product ID
        with patch("avena_commons.sequence.sequence.error") as mock_error:
            sequence.process_event(-1, "success")
            mock_error.assert_called_once()

        # Test next_step at boundary
        sequence.status.current_step = 3  # Last step
        sequence.next_step()
        assert sequence.status.finished is True

        # Test get_current_step_status when finished
        current = sequence.status.get_current_step_status
        assert current.step_id == 0
        assert current.fsm_state == StepState.DONE
