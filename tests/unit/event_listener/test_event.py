"""
Unit tests for the Event class and related models.

This module tests the core event system components including:
- Event model validation and serialization
- Result model for operation outcomes
- EventPriority enum functionality
- Event creation, manipulation, and data conversion

All tests follow the avena_commons testing guidelines with proper
fixtures, comprehensive coverage, and clear test organization.
"""

from datetime import datetime, timedelta
from typing import Optional

import pytest

from avena_commons.event_listener.event import Event, EventPriority, Result, ResultValue


class TestResult:
    """Test cases for the Result model."""

    def test_result_creation_empty(self):
        """Test creating an empty Result object."""
        result = Result()
        assert result.result is None
        assert result.error_code is None
        assert result.error_message is None

    def test_result_creation_with_success(self):
        """Test creating a successful Result object."""
        result = Result(result="success")
        assert result.result == "success"
        assert result.error_code is None
        assert result.error_message is None

    def test_result_creation_with_error(self):
        """Test creating an error Result object."""
        result = Result(result="failure", error_code=500, error_message="Internal server error")
        assert result.result == "failure"
        assert result.error_code == 500
        assert result.error_message == "Internal server error"

    def test_result_creation_with_all_fields(self):
        """Test creating a Result with all fields populated."""
        result = Result(result="test_failed", error_code=1, error_message="Test assertion failed")
        assert result.result == "test_failed"
        assert result.error_code == 1
        assert result.error_message == "Test assertion failed"

    def test_result_model_dump(self):
        """Test Result serialization to dictionary."""
        result = Result(result="success", error_code=0, error_message="Operation completed")
        dumped = result.model_dump()

        assert isinstance(dumped, dict)
        assert dumped["result"] == "success"
        assert dumped["error_code"] == 0
        assert dumped["error_message"] == "Operation completed"


class TestResultValue:
    """Test cases for the ResultValue enum."""

    def test_result_value_enum_values(self):
        """Test that all ResultValue enum values are correct."""
        assert ResultValue.SUCCESS.value == "success"
        assert ResultValue.FAILURE.value == "failure"
        assert ResultValue.TEST_FAILED.value == "test_failed"
        assert ResultValue.ERROR.value == "error"

    def test_result_value_enum_count(self):
        """Test that ResultValue enum has expected number of values."""
        assert len(ResultValue) == 4


class TestEventPriority:
    """Test cases for the EventPriority enum."""

    def test_event_priority_values(self):
        """Test that EventPriority enum values are correct."""
        assert EventPriority.LOW.value == 0
        assert EventPriority.MEDIUM.value == 1
        assert EventPriority.HIGH.value == 2

    def test_event_priority_ordering(self):
        """Test that EventPriority values maintain proper ordering."""
        assert EventPriority.LOW.value < EventPriority.MEDIUM.value
        assert EventPriority.MEDIUM.value < EventPriority.HIGH.value

    def test_event_priority_enum_count(self):
        """Test that EventPriority enum has expected number of values."""
        assert len(EventPriority) == 3


class TestEvent:
    """Test cases for the Event model."""

    @pytest.fixture
    def sample_event_data(self):
        """Fixture providing sample event data."""
        return {"temperature": 25.5, "humidity": 60.0, "location": "sensor_room_1"}

    @pytest.fixture
    def sample_result(self):
        """Fixture providing a sample Result object."""
        return Result(result="success", error_code=0, error_message="Operation completed successfully")

    @pytest.fixture
    def basic_event(self, sample_event_data):
        """Fixture providing a basic Event object."""
        return Event(
            source="test_sensor",
            source_address="192.168.1.100",
            source_port=8001,
            destination="test_controller",
            destination_address="192.168.1.200",
            destination_port=8002,
            event_type="measurement",
            data=sample_event_data,
        )

    def test_event_creation_minimal(self):
        """Test creating an Event with minimal parameters."""
        event = Event()

        assert event.source == "default"
        assert event.source_address == "127.0.0.1"
        assert event.source_port == 0
        assert event.destination == "default"
        assert event.destination_address == "127.0.0.1"
        assert event.destination_port == 0
        assert event.event_type == "default"
        assert event.data == {}
        assert event.priority == EventPriority.MEDIUM
        assert event.id is None
        assert event.result is None
        assert event.to_be_processed is False
        assert event.is_processing is False
        assert event.maximum_processing_time == 20
        assert isinstance(event.timestamp, datetime)

    def test_event_creation_with_all_parameters(self, sample_event_data, sample_result):
        """Test creating an Event with all parameters specified."""
        custom_timestamp = datetime.now() - timedelta(hours=1)

        event = Event(
            source="sensor_01",
            source_address="10.0.0.1",
            source_port=9001,
            destination="controller_main",
            destination_address="10.0.0.2",
            destination_port=9002,
            event_type="sensor_reading",
            data=sample_event_data,
            id=12345,
            to_be_processed=True,
            is_processing=False,
            result=sample_result,
            priority=EventPriority.HIGH,
            maximum_processing_time=30.5,
            timestamp=custom_timestamp,
        )

        assert event.source == "sensor_01"
        assert event.source_address == "10.0.0.1"
        assert event.source_port == 9001
        assert event.destination == "controller_main"
        assert event.destination_address == "10.0.0.2"
        assert event.destination_port == 9002
        assert event.event_type == "sensor_reading"
        assert event.data == sample_event_data
        assert event.id == 12345
        assert event.to_be_processed is True
        assert event.is_processing is False
        assert event.result == sample_result
        assert event.priority == EventPriority.HIGH
        assert event.maximum_processing_time == 30.5
        assert event.timestamp == custom_timestamp

    def test_event_timestamp_auto_generation(self):
        """Test that timestamp is automatically generated when not provided."""
        before_creation = datetime.now()
        event = Event()
        after_creation = datetime.now()

        assert before_creation <= event.timestamp <= after_creation

    def test_event_timestamp_custom(self):
        """Test that custom timestamp is properly set."""
        custom_timestamp = datetime(2023, 1, 1, 12, 0, 0)
        event = Event(timestamp=custom_timestamp)

        assert event.timestamp == custom_timestamp

    def test_event_to_dict_basic(self, basic_event):
        """Test Event.to_dict() method with basic event."""
        event_dict = basic_event.to_dict()

        assert isinstance(event_dict, dict)
        assert event_dict["source"] == "test_sensor"
        assert event_dict["source_address"] == "192.168.1.100"
        assert event_dict["source_port"] == 8001
        assert event_dict["destination"] == "test_controller"
        assert event_dict["destination_address"] == "192.168.1.200"
        assert event_dict["destination_port"] == 8002
        assert event_dict["event_type"] == "measurement"
        assert event_dict["priority"] == EventPriority.MEDIUM.value
        assert event_dict["data"] == basic_event.data
        assert event_dict["id"] is None
        assert event_dict["to_be_processed"] is False
        assert event_dict["is_processing"] is False
        assert event_dict["maximum_processing_time"] == 20
        assert event_dict["timestamp"] == str(basic_event.timestamp)
        assert event_dict["result"] is None

    def test_event_to_dict_with_result(self, basic_event, sample_result):
        """Test Event.to_dict() method with result included."""
        basic_event.result = sample_result
        event_dict = basic_event.to_dict()

        assert event_dict["result"] == sample_result.model_dump()

    def test_event_to_dict_with_id(self, basic_event):
        """Test Event.to_dict() method with ID included."""
        basic_event.id = 999
        event_dict = basic_event.to_dict()

        assert event_dict["id"] == 999

    def test_event_str_representation(self, basic_event):
        """Test Event.__str__() method."""
        str_repr = str(basic_event)

        assert "Event(" in str_repr
        assert "source=test_sensor" in str_repr
        assert "source_address=192.168.1.100" in str_repr
        assert "source_port=8001" in str_repr
        assert "destination=test_controller" in str_repr
        assert "destination_address=192.168.1.200" in str_repr
        assert "destination_port=8002" in str_repr
        assert "event_type=measurement" in str_repr
        assert "MPT=20.00" in str_repr

    def test_event_str_with_result(self, basic_event, sample_result):
        """Test Event.__str__() method with result."""
        basic_event.result = sample_result
        str_repr = str(basic_event)

        assert str(sample_result) in str_repr

    def test_event_priority_variations(self, sample_event_data):
        """Test Event creation with different priority levels."""
        for priority in EventPriority:
            event = Event(event_type="test", data=sample_event_data, priority=priority)
            assert event.priority == priority

    def test_event_data_immutability(self, basic_event):
        """Test that modifying original data dict doesn't affect event."""
        original_data = {"test": "value"}
        event = Event(data=original_data)

        # Modify original dict
        original_data["test"] = "modified"

        # Event should maintain its original data
        assert event.data != original_data

    def test_event_processing_flags(self):
        """Test event processing flag combinations."""
        # Test initial state
        event = Event()
        assert event.to_be_processed is False
        assert event.is_processing is False

        # Test setting processing flags
        event = Event(to_be_processed=True, is_processing=True)
        assert event.to_be_processed is True
        assert event.is_processing is True

    def test_event_maximum_processing_time_variations(self):
        """Test different maximum processing time values."""
        test_cases = [0.1, 1.0, 30.5, 60.0, 300.0]

        for mpt in test_cases:
            event = Event(maximum_processing_time=mpt)
            assert event.maximum_processing_time == mpt

    def test_event_data_types(self):
        """Test Event with various data types."""
        complex_data = {"string": "test", "integer": 42, "float": 3.14, "boolean": True, "list": [1, 2, 3], "dict": {"nested": "value"}, "null": None}

        event = Event(data=complex_data)
        assert event.data == complex_data

        # Test serialization preserves data types
        event_dict = event.to_dict()
        assert event_dict["data"] == complex_data

    def test_event_validation_errors(self):
        """Test Event validation with invalid data types."""
        # These should work fine as Pydantic handles type conversion
        event = Event(source_port="8001")  # String should convert to int
        assert event.source_port == 8001

        event = Event(destination_port="8002")
        assert event.destination_port == 8002

    @pytest.mark.parametrize("priority", list(EventPriority))
    def test_event_priority_serialization(self, priority):
        """Test that event priority is correctly serialized in to_dict()."""
        event = Event(priority=priority)
        event_dict = event.to_dict()

        assert event_dict["priority"] == priority.value
