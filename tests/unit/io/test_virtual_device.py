"""
Unit tests for VirtualDevice class.

This module contains comprehensive tests for the VirtualDevice abstract base class,
including all methods, exception handling scenarios, and edge cases to achieve 100% coverage.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
# from threading import Lock
from enum import Enum
# import threading

from avena_commons.io.virtual_device.virtual_device import (
    VirtualDevice,
    VirtualDeviceState,
)
from avena_commons.event_listener import Event, Result


class CustomTestDeviceState(Enum):
    """Test enum for testing VirtualDevice state handling."""

    CUSTOM_STATE = 42
    ANOTHER_STATE = 99


class ConcreteVirtualDevice(VirtualDevice):
    """Concrete implementation of VirtualDevice for testing purposes."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._test_state = kwargs.get("initial_state", VirtualDeviceState.UNINITIALIZED)
        self._tick_called = False
        self._get_state_should_raise = False
        self._instant_execute_should_raise = False

    def get_current_state(self):
        """Return current state, optionally raising exception for testing."""
        if self._get_state_should_raise:
            raise RuntimeError("Test exception in get_current_state")
        return self._test_state

    def set_test_state(self, state):
        """Helper method to set test state."""
        self._test_state = state

    def _instant_execute_event(self, event: Event) -> Event:
        """Implementation of abstract method for testing."""
        if self._instant_execute_should_raise:
            raise RuntimeError("Test exception in _instant_execute_event")
        event.result = Result(result="instant_success")
        return event

    def tick(self):
        """Implementation of abstract method for testing."""
        self._tick_called = True

    def was_tick_called(self):
        """Check if tick was called."""
        return self._tick_called


class TestVirtualDevice:
    """Test suite for VirtualDevice class."""

    @pytest.fixture
    def mock_message_logger(self):
        """Mock message logger for testing."""
        return Mock()

    @pytest.fixture
    def default_kwargs(self, mock_message_logger):
        """Default kwargs for VirtualDevice initialization."""
        return {
            "device_name": "test_device",
            "devices": ["device1", "device2"],
            "methods": {"method1": Mock(), "method2": Mock()},
            "message_logger": mock_message_logger,
        }

    @pytest.fixture
    def virtual_device(self, default_kwargs):
        """Create a concrete VirtualDevice instance for testing."""
        return ConcreteVirtualDevice(**default_kwargs)

    def test_init_valid_kwargs(self, default_kwargs):
        """Test VirtualDevice initialization with valid kwargs."""
        device = ConcreteVirtualDevice(**default_kwargs)

        assert device.device_name == "test_device"
        assert device.devices == ["device1", "device2"]
        assert device.methods == default_kwargs["methods"]
        assert device._processing_events == {}
        assert device._finished_events == []
        assert hasattr(device._processing_events_lock, "acquire")
        assert hasattr(device._processing_events_lock, "release")
        assert hasattr(device._finished_events_lock, "acquire")
        assert hasattr(device._finished_events_lock, "release")
        assert device._state == VirtualDeviceState.UNINITIALIZED
        assert device._message_logger == default_kwargs["message_logger"]

    def test_init_minimal_kwargs(self, mock_message_logger):
        """Test VirtualDevice initialization with minimal required kwargs."""
        kwargs = {
            "device_name": "minimal_device",
            "devices": None,
            "methods": None,
            "message_logger": mock_message_logger,
        }
        device = ConcreteVirtualDevice(**kwargs)

        assert device.device_name == "minimal_device"
        assert device.devices is None
        assert device.methods is None

    @patch("avena_commons.io.virtual_device.virtual_device.debug")
    def test_set_state_success(self, mock_debug, virtual_device):
        """Test successful state change."""
        old_state = virtual_device._state
        new_state = VirtualDeviceState.WORKING

        virtual_device.set_state(new_state)

        assert virtual_device._state == new_state
        mock_debug.assert_called_once_with(
            f"{virtual_device.device_name} - State changed from {old_state} to {new_state}",
            message_logger=virtual_device._message_logger,
        )

    @patch("avena_commons.io.virtual_device.virtual_device.error")
    @patch("avena_commons.io.virtual_device.virtual_device.debug")
    def test_set_state_exception(self, mock_debug, mock_error, virtual_device):
        """Test set_state with exception during state change."""
        # Mock debug to raise exception
        mock_debug.side_effect = Exception("Test error")

        virtual_device.set_state(VirtualDeviceState.WORKING)

        mock_error.assert_called_once()
        call_args = mock_error.call_args[0][0]
        assert "Error setting state" in call_args
        assert "Test error" in call_args

    def test_get_current_state_success(self, virtual_device):
        """Test successful get_current_state call."""
        virtual_device.set_test_state(VirtualDeviceState.WORKING)

        state = virtual_device.get_current_state()
        assert state == VirtualDeviceState.WORKING

    def test_get_current_state_exception(self, virtual_device):
        """Test get_current_state raising exception."""
        virtual_device._get_state_should_raise = True

        with pytest.raises(RuntimeError, match="Test exception in get_current_state"):
            virtual_device.get_current_state()

    @patch("avena_commons.io.virtual_device.virtual_device.debug")
    def test_handle_check_state_event_success(self, mock_debug, virtual_device):
        """Test successful handling of check_fsm_state event."""
        virtual_device.set_test_state(VirtualDeviceState.WORKING)
        event = Event(event_type="check_fsm_state", to_be_processed=False)

        result_event = virtual_device._handle_check_state_event(event)

        assert result_event.data["device_name"] == "test_device"
        assert result_event.data["state"] == VirtualDeviceState.WORKING.value
        assert result_event.data["state_name"] == VirtualDeviceState.WORKING.name
        mock_debug.assert_called_once()

    @patch("avena_commons.io.virtual_device.virtual_device.debug")
    def test_handle_check_state_event_none_data(self, mock_debug, virtual_device):
        """Test handling check_fsm_state event with None data."""
        virtual_device.set_test_state(VirtualDeviceState.WORKING)
        event = Event(event_type="check_fsm_state", to_be_processed=False)
        event.data = None

        result_event = virtual_device._handle_check_state_event(event)

        assert result_event.data is not None
        assert result_event.data["device_name"] == "test_device"
        assert result_event.data["state"] == VirtualDeviceState.WORKING.value
        assert result_event.data["state_name"] == VirtualDeviceState.WORKING.name

    @patch("avena_commons.io.virtual_device.virtual_device.debug")
    def test_handle_check_state_event_custom_enum(self, mock_debug, virtual_device):
        """Test handling check_fsm_state event with custom enum state."""
        virtual_device.set_test_state(CustomTestDeviceState.CUSTOM_STATE)
        event = Event(event_type="check_fsm_state", to_be_processed=False)

        result_event = virtual_device._handle_check_state_event(event)

        assert result_event.data["state"] == CustomTestDeviceState.CUSTOM_STATE.value
        assert (
            result_event.data["state_name"] == CustomTestDeviceState.CUSTOM_STATE.name
        )

    @patch("avena_commons.io.virtual_device.virtual_device.debug")
    def test_handle_check_state_event_non_enum_state(self, mock_debug, virtual_device):
        """Test handling check_fsm_state event with non-enum state."""
        virtual_device.set_test_state("custom_string_state")
        event = Event(event_type="check_fsm_state", to_be_processed=False)

        result_event = virtual_device._handle_check_state_event(event)

        assert result_event.data["state"] == "custom_string_state"
        assert result_event.data["state_name"] == "custom_string_state"

    @patch("avena_commons.io.virtual_device.virtual_device.error")
    def test_handle_check_state_event_exception(self, mock_error, virtual_device):
        """Test handling check_fsm_state event with exception."""
        virtual_device._get_state_should_raise = True
        event = Event(event_type="check_fsm_state", to_be_processed=False)

        result_event = virtual_device._handle_check_state_event(event)

        assert result_event.result.result == "error"
        assert "Error getting device state" in result_event.result.error_message
        mock_error.assert_called_once()

    @patch("avena_commons.io.virtual_device.virtual_device.debug")
    def test_move_event_to_finished_success(self, mock_debug, virtual_device):
        """Test successful move event to finished."""
        event = Event(event_type="test_event", to_be_processed=True)
        virtual_device._processing_events["test_event"] = event

        result = virtual_device._move_event_to_finished(
            "test_event", "success", "Test message"
        )

        assert result is True
        assert "test_event" not in virtual_device._processing_events
        assert len(virtual_device._finished_events) == 1
        assert virtual_device._finished_events[0].result.result == "success"
        assert virtual_device._finished_events[0].result.error_message == "Test message"
        assert mock_debug.call_count == 2

    @patch("avena_commons.io.virtual_device.virtual_device.debug")
    def test_move_event_to_finished_no_message(self, mock_debug, virtual_device):
        """Test move event to finished without result message."""
        event = Event(event_type="test_event", to_be_processed=True)
        virtual_device._processing_events["test_event"] = event

        result = virtual_device._move_event_to_finished("test_event", "success")

        assert result is True
        assert virtual_device._finished_events[0].result.result == "success"
        assert (
            not hasattr(virtual_device._finished_events[0].result, "error_message")
            or virtual_device._finished_events[0].result.error_message is None
        )

    @patch("avena_commons.io.virtual_device.virtual_device.error")
    def test_move_event_to_finished_exception(self, mock_error, virtual_device):
        """Test move event to finished with exception."""
        # Event not in processing_events will cause KeyError
        result = virtual_device._move_event_to_finished("nonexistent_event", "success")

        assert result is False
        mock_error.assert_called_once()
        call_args = mock_error.call_args[0][0]
        assert "Error moving event to finished" in call_args

    @patch("avena_commons.io.virtual_device.virtual_device.MeasureTime")
    def test_execute_event_already_in_progress(self, mock_measure_time, virtual_device):
        """Test execute_event when event is already in progress."""
        event = Event(event_type="test_event", to_be_processed=True)
        virtual_device._processing_events["test_event"] = Mock()

        result = virtual_device.execute_event(event)

        assert result is not None
        assert result.result.result == "error"
        assert result.result.error_message == "Event already in progress"

    @patch("avena_commons.io.virtual_device.virtual_device.MeasureTime")
    def test_execute_event_to_be_processed(self, mock_measure_time, virtual_device):
        """Test execute_event with to_be_processed=True."""
        event = Event(event_type="test_event", to_be_processed=True)

        result = virtual_device.execute_event(event)

        assert result is None
        assert "test_event" in virtual_device._processing_events
        assert virtual_device._processing_events["test_event"] == event

    @patch("avena_commons.io.virtual_device.virtual_device.MeasureTime")
    def test_execute_event_check_fsm_state(self, mock_measure_time, virtual_device):
        """Test execute_event with check_fsm_state event."""
        virtual_device.set_test_state(VirtualDeviceState.WORKING)
        event = Event(event_type="device_check_fsm_state", to_be_processed=False)

        result = virtual_device.execute_event(event)

        assert result is not None
        assert result.result.result == "success"
        assert result.data["device_name"] == "test_device"
        assert result.data["state"] == VirtualDeviceState.WORKING.value

    @patch("avena_commons.io.virtual_device.virtual_device.MeasureTime")
    def test_execute_event_instant_execute(self, mock_measure_time, virtual_device):
        """Test execute_event with instant execution."""
        event = Event(event_type="test_event", to_be_processed=False)

        result = virtual_device.execute_event(event)

        assert result is not None
        assert result.result.result == "instant_success"

    def test_finished_events_empty(self, virtual_device):
        """Test finished_events when no events are finished."""
        result = virtual_device.finished_events()

        assert result == []
        assert virtual_device._finished_events == []

    def test_finished_events_with_events(self, virtual_device):
        """Test finished_events with some finished events."""
        event1 = Event(event_type="event1", to_be_processed=False)
        event2 = Event(event_type="event2", to_be_processed=False)
        virtual_device._finished_events = [event1, event2]

        result = virtual_device.finished_events()

        assert len(result) == 2
        assert event1 in result
        assert event2 in result
        assert virtual_device._finished_events == []  # Should be cleared

    def test_tick_called(self, virtual_device):
        """Test that tick method is called."""
        virtual_device.tick()

        assert virtual_device.was_tick_called() is True

    def test_str_success(self, virtual_device):
        """Test __str__ method with successful state retrieval."""
        virtual_device.set_test_state(VirtualDeviceState.WORKING)

        result = str(virtual_device)

        assert "VirtualDevice(name='test_device'" in result
        assert "state=WORKING" in result
        assert "connected_devices=2" in result

    def test_str_custom_enum(self, virtual_device):
        """Test __str__ method with custom enum state."""
        virtual_device.set_test_state(CustomTestDeviceState.CUSTOM_STATE)

        result = str(virtual_device)

        assert "state=CUSTOM_STATE" in result

    def test_str_non_enum_state(self, virtual_device):
        """Test __str__ method with non-enum state."""
        virtual_device.set_test_state("custom_string")

        result = str(virtual_device)

        assert "state=custom_string" in result

    def test_str_no_devices(self, mock_message_logger):
        """Test __str__ method with no devices."""
        kwargs = {
            "device_name": "no_devices",
            "devices": None,
            "methods": None,
            "message_logger": mock_message_logger,
        }
        device = ConcreteVirtualDevice(**kwargs)

        result = str(device)

        assert "connected_devices=0" in result

    def test_str_empty_devices(self, mock_message_logger):
        """Test __str__ method with empty devices list."""
        kwargs = {
            "device_name": "empty_devices",
            "devices": [],
            "methods": None,
            "message_logger": mock_message_logger,
        }
        device = ConcreteVirtualDevice(**kwargs)

        result = str(device)

        assert "connected_devices=0" in result

    def test_str_exception(self, virtual_device):
        """Test __str__ method with exception in get_current_state."""
        virtual_device._get_state_should_raise = True

        result = str(virtual_device)

        assert "VirtualDevice(name='test_device'" in result
        assert "state=ERROR" in result
        assert "Test exception in get_current_state" in result

    def test_repr_success(self, virtual_device):
        """Test __repr__ method with successful state retrieval."""
        virtual_device.set_test_state(VirtualDeviceState.WORKING)

        result = repr(virtual_device)

        assert "VirtualDevice(device_name='test_device'" in result
        assert "state=WORKING(2)" in result
        assert "devices=['device1', 'device2']" in result
        assert "methods=['method1', 'method2']" in result

    def test_repr_custom_enum(self, virtual_device):
        """Test __repr__ method with custom enum state."""
        virtual_device.set_test_state(CustomTestDeviceState.CUSTOM_STATE)

        result = repr(virtual_device)

        assert "state=CUSTOM_STATE(42)" in result

    def test_repr_non_enum_state(self, virtual_device):
        """Test __repr__ method with non-enum state."""
        virtual_device.set_test_state("custom_string")

        result = repr(virtual_device)

        assert "state=custom_string" in result

    def test_repr_no_methods(self, mock_message_logger):
        """Test __repr__ method with no methods."""
        kwargs = {
            "device_name": "no_methods",
            "devices": ["device1"],
            "methods": None,
            "message_logger": mock_message_logger,
        }
        device = ConcreteVirtualDevice(**kwargs)

        result = repr(device)

        assert "methods=[]" in result

    def test_repr_exception(self, virtual_device):
        """Test __repr__ method with exception in get_current_state."""
        virtual_device._get_state_should_raise = True

        result = repr(virtual_device)

        assert "VirtualDevice(device_name='test_device'" in result
        assert "Test exception in get_current_state" in result

    def test_to_dict_success(self, virtual_device):
        """Test to_dict method with successful state retrieval."""
        virtual_device.set_test_state(VirtualDeviceState.WORKING)

        result = virtual_device.to_dict()

        expected = {
            "name": "test_device",
            "connected_devices": ["device1", "device2"],
            "state": VirtualDeviceState.WORKING.value,
            "state_name": VirtualDeviceState.WORKING.name,
        }
        assert result == expected

    def test_to_dict_custom_enum(self, virtual_device):
        """Test to_dict method with custom enum state."""
        virtual_device.set_test_state(CustomTestDeviceState.CUSTOM_STATE)

        result = virtual_device.to_dict()

        assert result["state"] == CustomTestDeviceState.CUSTOM_STATE.value
        assert result["state_name"] == CustomTestDeviceState.CUSTOM_STATE.name

    def test_to_dict_non_enum_state(self, virtual_device):
        """Test to_dict method with non-enum state."""
        virtual_device.set_test_state("custom_string")

        result = virtual_device.to_dict()

        assert result["state"] == "custom_string"
        assert result["state_name"] == "custom_string"

    def test_to_dict_no_devices(self, mock_message_logger):
        """Test to_dict method with no devices."""
        kwargs = {
            "device_name": "no_devices",
            "devices": None,
            "methods": None,
            "message_logger": mock_message_logger,
        }
        device = ConcreteVirtualDevice(**kwargs)

        result = device.to_dict()

        assert result["connected_devices"] == []

    def test_to_dict_empty_devices(self, mock_message_logger):
        """Test to_dict method with empty devices list."""
        kwargs = {
            "device_name": "empty_devices",
            "devices": [],
            "methods": None,
            "message_logger": mock_message_logger,
        }
        device = ConcreteVirtualDevice(**kwargs)

        result = device.to_dict()

        assert result["connected_devices"] == []

    @patch("avena_commons.io.virtual_device.virtual_device.error")
    def test_to_dict_exception(self, mock_error, virtual_device):
        """Test to_dict method with exception in get_current_state."""
        virtual_device._get_state_should_raise = True

        result = virtual_device.to_dict()

        assert result["name"] == "test_device"
        assert result["connected_devices"] == ["device1", "device2"]
        assert result["state"] == "ERROR"
        assert result["state_name"] == "ERROR"
        assert "Test exception in get_current_state" in result["error"]
        mock_error.assert_called_once()

    def test_abstract_methods_not_implemented(self):
        """Test that abstract methods raise NotImplementedError when not implemented."""
        with pytest.raises(TypeError):
            # Cannot instantiate abstract class
            VirtualDevice(
                device_name="test", devices=[], methods={}, message_logger=Mock()
            )

    @patch("avena_commons.io.virtual_device.virtual_device.MeasureTime")
    def test_execute_event_measure_time_context(
        self, mock_measure_time_class, virtual_device
    ):
        """Test that execute_event uses MeasureTime context manager."""
        mock_measure_time = MagicMock()
        mock_measure_time_class.return_value = mock_measure_time
        event = Event(event_type="test_event", to_be_processed=False)

        virtual_device.execute_event(event)

        mock_measure_time_class.assert_called_once_with(
            label="test_device execute_event: test_event",
            max_execution_time=1.0,
            message_logger=virtual_device._message_logger,
        )
        mock_measure_time.__enter__.assert_called_once()
        mock_measure_time.__exit__.assert_called_once()

    def test_processing_events_lock_usage(self, virtual_device):
        """Test that processing events lock is used correctly."""
        event = Event(event_type="test_event", to_be_processed=True)

        # Test that the lock protects the processing_events dictionary
        # We can't directly patch the lock, but we can test the functionality
        virtual_device.execute_event(event)

        # Verify the event was added to processing_events (protected by lock)
        assert "test_event" in virtual_device._processing_events

        # Test that attempting to execute the same event again returns an error
        duplicate_event = Event(event_type="test_event", to_be_processed=True)
        result = virtual_device.execute_event(duplicate_event)

        assert result is not None
        assert result.result.result == "error"
        assert result.result.error_message == "Event already in progress"

    def test_finished_events_lock_usage(self, virtual_device):
        """Test that finished events lock is used correctly."""
        event1 = Event(event_type="test_event1", to_be_processed=False)
        event2 = Event(event_type="test_event2", to_be_processed=False)
        virtual_device._finished_events = [event1, event2]

        # Test that the lock protects the finished_events list
        # We can't directly patch the lock, but we can test the functionality
        result = virtual_device.finished_events()

        # Verify the events were returned and the list was cleared (protected by lock)
        assert len(result) == 2
        assert event1 in result
        assert event2 in result
        assert virtual_device._finished_events == []

        # Test that calling finished_events again returns empty list
        result2 = virtual_device.finished_events()
        assert result2 == []
