"""
Unit tests for the IoSignal and IoAction models.

This module tests the I/O type models including:
- IoSignal model validation and serialization
- IoAction model validation and serialization
- Data conversion and edge cases

All tests follow the avena_commons testing guidelines with proper
fixtures, comprehensive coverage, and clear test organization.
"""

import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest

from avena_commons.event_listener.types.io import IoAction, IoSignal


class TestIoSignal:
    """Test cases for the IoSignal model."""

    @pytest.fixture
    def basic_io_signal_data(self):
        """Fixture providing basic IoSignal data."""
        return {"device_type": "tor_pieca", "device_id": 1, "signal_name": "in", "signal_value": True}

    def test_io_signal_creation_basic(self, basic_io_signal_data):
        """Test creating an IoSignal with basic parameters."""
        signal = IoSignal(**basic_io_signal_data)

        assert signal.device_type == "tor_pieca"
        assert signal.device_id == 1
        assert signal.signal_name == "in"
        assert signal.signal_value is True

    def test_io_signal_creation_with_int_value(self):
        """Test creating an IoSignal with integer value."""
        signal = IoSignal(device_type="sensor_temp", device_id=5, signal_name="temperature", signal_value=25)

        assert signal.device_type == "sensor_temp"
        assert signal.device_id == 5
        assert signal.signal_name == "temperature"
        assert signal.signal_value == 25
        assert isinstance(signal.signal_value, int)

    def test_io_signal_creation_with_bool_value(self):
        """Test creating an IoSignal with boolean value."""
        signal = IoSignal(device_type="door_sensor", device_id=2, signal_name="is_open", signal_value=False)

        assert signal.device_type == "door_sensor"
        assert signal.device_id == 2
        assert signal.signal_name == "is_open"
        assert signal.signal_value is False
        assert isinstance(signal.signal_value, bool)

    def test_io_signal_to_dict(self, basic_io_signal_data):
        """Test IoSignal.to_dict() method."""
        signal = IoSignal(**basic_io_signal_data)
        signal_dict = signal.to_dict()

        assert isinstance(signal_dict, dict)
        assert signal_dict["device_type"] == "tor_pieca"
        assert signal_dict["device_id"] == 1
        assert signal_dict["signal_name"] == "in"
        assert signal_dict["signal_value"] is True

    def test_io_signal_from_dict(self, basic_io_signal_data):
        """Test IoSignal.from_dict() class method."""
        signal = IoSignal.from_dict(basic_io_signal_data)

        assert isinstance(signal, IoSignal)
        assert signal.device_type == basic_io_signal_data["device_type"]
        assert signal.device_id == basic_io_signal_data["device_id"]
        assert signal.signal_name == basic_io_signal_data["signal_name"]
        assert signal.signal_value == basic_io_signal_data["signal_value"]

    def test_io_signal_round_trip_conversion(self, basic_io_signal_data):
        """Test round-trip conversion from dict to IoSignal and back."""
        original_signal = IoSignal(**basic_io_signal_data)
        signal_dict = original_signal.to_dict()
        reconstructed_signal = IoSignal.from_dict(signal_dict)

        assert original_signal.device_type == reconstructed_signal.device_type
        assert original_signal.device_id == reconstructed_signal.device_id
        assert original_signal.signal_name == reconstructed_signal.signal_name
        assert original_signal.signal_value == reconstructed_signal.signal_value

    @pytest.mark.parametrize(
        "signal_value,expected_type",
        [
            (True, bool),
            (False, bool),
            (0, int),
            (1, int),
            (100, int),
            (-5, int),
        ],
    )
    def test_io_signal_value_types(self, signal_value, expected_type):
        """Test IoSignal with different value types."""
        signal = IoSignal(device_type="test_device", device_id=1, signal_name="test_signal", signal_value=signal_value)

        assert signal.signal_value == signal_value
        assert isinstance(signal.signal_value, expected_type)

    def test_io_signal_model_validation(self):
        """Test that IoSignal validates required fields."""
        # Missing required fields should raise ValidationError
        with pytest.raises(ValueError):
            IoSignal()  # Missing all required fields

    def test_io_signal_serialization_compatibility(self):
        """Test IoSignal serialization compatibility with Pydantic."""
        signal = IoSignal(device_type="test_device", device_id=1, signal_name="test_signal", signal_value=True)

        # Test model_dump method (Pydantic v2)
        dumped = signal.model_dump()
        assert isinstance(dumped, dict)
        assert dumped == signal.to_dict()

    def test_io_signal_edge_cases(self):
        """Test IoSignal with edge case values."""
        # Test with zero device_id
        signal = IoSignal(device_type="edge_device", device_id=0, signal_name="zero_signal", signal_value=False)
        assert signal.device_id == 0

        # Test with negative signal value
        signal = IoSignal(device_type="edge_device", device_id=1, signal_name="negative_signal", signal_value=-100)
        assert signal.signal_value == -100

        # Test with empty string device_type
        signal = IoSignal(device_type="", device_id=1, signal_name="empty_type", signal_value=True)
        assert signal.device_type == ""


class TestIoAction:
    """Test cases for the IoAction model."""

    @pytest.fixture
    def basic_io_action_data(self):
        """Fixture providing basic IoAction data."""
        return {"device_type": "tor_pieca", "device_id": 1, "subdevice_id": 2}

    def test_io_action_creation_basic(self, basic_io_action_data):
        """Test creating an IoAction with basic parameters."""
        action = IoAction(**basic_io_action_data)

        assert action.device_type == "tor_pieca"
        assert action.device_id == 1
        assert action.subdevice_id == 2

    def test_io_action_creation_minimal(self):
        """Test creating an IoAction with minimal parameters."""
        action = IoAction(device_type="minimal_device")

        assert action.device_type == "minimal_device"
        assert action.device_id is None
        assert action.subdevice_id is None

    def test_io_action_creation_with_device_id_only(self):
        """Test creating an IoAction with device_id but no subdevice_id."""
        action = IoAction(device_type="single_device", device_id=5)

        assert action.device_type == "single_device"
        assert action.device_id == 5
        assert action.subdevice_id is None

    def test_io_action_creation_with_subdevice_id_only(self):
        """Test creating an IoAction with subdevice_id but no device_id."""
        action = IoAction(device_type="sub_only_device", subdevice_id=3)

        assert action.device_type == "sub_only_device"
        assert action.device_id is None
        assert action.subdevice_id == 3

    def test_io_action_to_dict(self, basic_io_action_data):
        """Test IoAction.to_dict() method."""
        action = IoAction(**basic_io_action_data)
        action_dict = action.to_dict()

        assert isinstance(action_dict, dict)
        assert action_dict["device_type"] == "tor_pieca"
        assert action_dict["device_id"] == 1
        assert action_dict["subdevice_id"] == 2

    def test_io_action_to_dict_with_none_values(self):
        """Test IoAction.to_dict() method with None values."""
        action = IoAction(device_type="none_device")
        action_dict = action.to_dict()

        assert action_dict["device_type"] == "none_device"
        assert action_dict["device_id"] is None
        assert action_dict["subdevice_id"] is None

    def test_io_action_from_dict(self, basic_io_action_data):
        """Test IoAction.from_dict() class method."""
        action = IoAction.from_dict(basic_io_action_data)

        assert isinstance(action, IoAction)
        assert action.device_type == basic_io_action_data["device_type"]
        assert action.device_id == basic_io_action_data["device_id"]
        assert action.subdevice_id == basic_io_action_data["subdevice_id"]

    def test_io_action_from_dict_with_missing_optional_fields(self):
        """Test IoAction.from_dict() with missing optional fields."""
        minimal_data = {"device_type": "minimal_device"}
        action = IoAction.from_dict(minimal_data)

        assert action.device_type == "minimal_device"
        assert action.device_id is None
        assert action.subdevice_id is None

    def test_io_action_round_trip_conversion(self, basic_io_action_data):
        """Test round-trip conversion from dict to IoAction and back."""
        original_action = IoAction(**basic_io_action_data)
        action_dict = original_action.to_dict()
        reconstructed_action = IoAction.from_dict(action_dict)

        assert original_action.device_type == reconstructed_action.device_type
        assert original_action.device_id == reconstructed_action.device_id
        assert original_action.subdevice_id == reconstructed_action.subdevice_id

    @pytest.mark.parametrize(
        "device_id,subdevice_id",
        [
            (None, None),
            (0, None),
            (None, 0),
            (0, 0),
            (1, None),
            (None, 1),
            (100, 200),
            (-1, -2),  # Test negative IDs
        ],
    )
    def test_io_action_id_combinations(self, device_id, subdevice_id):
        """Test IoAction with various device_id and subdevice_id combinations."""
        action = IoAction(device_type="test_device", device_id=device_id, subdevice_id=subdevice_id)

        assert action.device_id == device_id
        assert action.subdevice_id == subdevice_id

    def test_io_action_model_validation(self):
        """Test that IoAction validates required fields."""
        # Missing device_type should raise ValidationError
        with pytest.raises(ValueError):
            IoAction()

    def test_io_action_serialization_compatibility(self):
        """Test IoAction serialization compatibility with Pydantic."""
        action = IoAction(device_type="test_device", device_id=1, subdevice_id=2)

        # Test model_dump method (Pydantic v2)
        dumped = action.model_dump()
        assert isinstance(dumped, dict)
        assert dumped == action.to_dict()

    def test_io_action_edge_cases(self):
        """Test IoAction with edge case values."""
        # Test with empty string device_type
        action = IoAction(device_type="")
        assert action.device_type == ""

        # Test with very large device IDs
        action = IoAction(device_type="large_id_device", device_id=999999, subdevice_id=999999)
        assert action.device_id == 999999
        assert action.subdevice_id == 999999


class TestIoModelsIntegration:
    """Integration tests for IoSignal and IoAction models."""

    def test_io_models_type_consistency(self):
        """Test that IoSignal and IoAction have consistent device_type usage."""
        device_type = "integrated_device"

        signal = IoSignal(device_type=device_type, device_id=1, signal_name="status", signal_value=True)

        action = IoAction(device_type=device_type, device_id=1)

        assert signal.device_type == action.device_type
        assert signal.device_id == action.device_id

    def test_io_models_serialization_consistency(self):
        """Test that both models serialize consistently."""
        signal = IoSignal(device_type="test_device", device_id=1, signal_name="test_signal", signal_value=True)

        action = IoAction(device_type="test_device", device_id=1)

        signal_dict = signal.to_dict()
        action_dict = action.to_dict()

        # Both should have consistent device_type and device_id
        assert signal_dict["device_type"] == action_dict["device_type"]
        assert signal_dict["device_id"] == action_dict["device_id"]

    def test_io_models_validation_consistency(self):
        """Test that both models have consistent validation behavior."""
        # Both should require device_type
        with pytest.raises(ValueError):
            IoSignal(device_id=1, signal_name="test", signal_value=True)

        with pytest.raises(ValueError):
            IoAction(device_id=1)

    @pytest.mark.parametrize(
        "device_type,device_id",
        [
            ("sensor", 1),
            ("actuator", 2),
            ("controller", 10),
            ("interface", 0),
        ],
    )
    def test_io_models_parametrized_creation(self, device_type, device_id):
        """Test creating both models with parametrized values."""
        signal = IoSignal(device_type=device_type, device_id=device_id, signal_name="test_signal", signal_value=True)

        action = IoAction(device_type=device_type, device_id=device_id)

        assert signal.device_type == device_type
        assert signal.device_id == device_id
        assert action.device_type == device_type
        assert action.device_id == device_id
