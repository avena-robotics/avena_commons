"""
Unit tests for avena_commons.event_listener.types.kds module.

This module contains comprehensive tests for the KdsAction model, including:
- Model validation and field constraints
- Serialization and deserialization
- Edge cases and boundary conditions
- Type safety and error handling

Test Coverage:
- Basic model instantiation
- Field validation
- JSON serialization/deserialization
- Edge cases with None values
- Error handling for invalid inputs
"""

import pytest
from pydantic import ValidationError

from avena_commons.event_listener.types.kds import KdsAction


class TestKdsAction:
    """Test suite for KdsAction model."""

    def test_init_default_values(self):
        """Test KdsAction initialization with default values."""
        action = KdsAction()

        assert action.order_number is None
        assert action.pickup_number is None
        assert action.message is None

    def test_init_with_all_fields(self):
        """Test KdsAction initialization with all fields provided."""
        action = KdsAction(order_number=100, pickup_number=50, message="kds_order_number")

        assert action.order_number == 100
        assert action.pickup_number == 50
        assert action.message == "kds_order_number"

    def test_init_with_partial_fields(self):
        """Test KdsAction initialization with partial fields."""
        action = KdsAction(order_number=100)

        assert action.order_number == 100
        assert action.pickup_number is None
        assert action.message is None

    @pytest.mark.parametrize("order_number", [0, 1, 50, 100, 999, 10000])
    def test_order_number_valid_values(self, order_number):
        """Test KdsAction with various valid order numbers."""
        action = KdsAction(order_number=order_number)
        assert action.order_number == order_number

    @pytest.mark.parametrize("pickup_number", [0, 1, 25, 50, 100, 999])
    def test_pickup_number_valid_values(self, pickup_number):
        """Test KdsAction with various valid pickup numbers."""
        action = KdsAction(pickup_number=pickup_number)
        assert action.pickup_number == pickup_number

    @pytest.mark.parametrize(
        "message",
        [
            "kds_order_number",
            "test_message",
            "",
            "a" * 1000,  # long message
            "Special chars: !@#$%^&*()",
            "Unicode: 🚀🎉",
            "Numbers: 12345",
        ],
    )
    def test_message_valid_values(self, message):
        """Test KdsAction with various valid message values."""
        action = KdsAction(message=message)
        assert action.message == message

    def test_negative_order_number(self):
        """Test KdsAction with negative order number."""
        action = KdsAction(order_number=-1)
        assert action.order_number == -1

    def test_negative_pickup_number(self):
        """Test KdsAction with negative pickup number."""
        action = KdsAction(pickup_number=-5)
        assert action.pickup_number == -5

    def test_zero_values(self):
        """Test KdsAction with zero values."""
        action = KdsAction(order_number=0, pickup_number=0)

        assert action.order_number == 0
        assert action.pickup_number == 0

    def test_large_numbers(self):
        """Test KdsAction with large number values."""
        action = KdsAction(order_number=999999999, pickup_number=888888888)

        assert action.order_number == 999999999
        assert action.pickup_number == 888888888


class TestKdsActionSerialization:
    """Test suite for KdsAction serialization methods."""

    def test_to_dict_all_fields(self):
        """Test to_dict method with all fields populated."""
        action = KdsAction(order_number=100, pickup_number=50, message="test_message")

        result = action.to_dict()
        expected = {"order_number": 100, "pickup_number": 50, "message": "test_message"}

        assert result == expected
        assert isinstance(result, dict)

    def test_to_dict_default_values(self):
        """Test to_dict method with default (None) values."""
        action = KdsAction()

        result = action.to_dict()
        expected = {"order_number": None, "pickup_number": None, "message": None}

        assert result == expected

    def test_to_dict_partial_fields(self):
        """Test to_dict method with partial fields."""
        action = KdsAction(order_number=42, message="partial")

        result = action.to_dict()
        expected = {"order_number": 42, "pickup_number": None, "message": "partial"}

        assert result == expected

    def test_from_dict_all_fields(self):
        """Test from_dict method with all fields."""
        data = {"order_number": 123, "pickup_number": 456, "message": "from_dict_test"}

        action = KdsAction.from_dict(data)

        assert action.order_number == 123
        assert action.pickup_number == 456
        assert action.message == "from_dict_test"

    def test_from_dict_empty_dict(self):
        """Test from_dict method with empty dictionary."""
        data = {}

        action = KdsAction.from_dict(data)

        assert action.order_number is None
        assert action.pickup_number is None
        assert action.message is None

    def test_from_dict_partial_fields(self):
        """Test from_dict method with partial fields."""
        data = {"order_number": 99}

        action = KdsAction.from_dict(data)

        assert action.order_number == 99
        assert action.pickup_number is None
        assert action.message is None

    def test_from_dict_with_none_values(self):
        """Test from_dict method with explicit None values."""
        data = {"order_number": None, "pickup_number": None, "message": None}

        action = KdsAction.from_dict(data)

        assert action.order_number is None
        assert action.pickup_number is None
        assert action.message is None

    def test_serialization_round_trip(self):
        """Test complete serialization round trip."""
        original = KdsAction(order_number=777, pickup_number=888, message="round_trip_test")

        # Serialize to dict
        data = original.to_dict()

        # Deserialize back to object
        restored = KdsAction.from_dict(data)

        assert restored.order_number == original.order_number
        assert restored.pickup_number == original.pickup_number
        assert restored.message == original.message
        assert restored == original

    def test_serialization_round_trip_defaults(self):
        """Test serialization round trip with default values."""
        original = KdsAction()

        data = original.to_dict()
        restored = KdsAction.from_dict(data)

        assert restored == original


class TestKdsActionValidation:
    """Test suite for KdsAction validation and error handling."""

    def test_invalid_order_number_type(self):
        """Test KdsAction with invalid order_number type."""
        with pytest.raises(ValidationError) as exc_info:
            KdsAction(order_number="invalid")

        assert "Input should be a valid integer" in str(exc_info.value)

    def test_invalid_pickup_number_type(self):
        """Test KdsAction with invalid pickup_number type."""
        with pytest.raises(ValidationError) as exc_info:
            KdsAction(pickup_number=["invalid"])

        assert "Input should be a valid integer" in str(exc_info.value)

    def test_invalid_message_type(self):
        """Test KdsAction with invalid message type."""
        with pytest.raises(ValidationError) as exc_info:
            KdsAction(message=123)

        assert "Input should be a valid string" in str(exc_info.value)

    def test_from_dict_invalid_data_type(self):
        """Test from_dict with invalid data types."""
        with pytest.raises(ValidationError):
            KdsAction.from_dict({"order_number": "not_a_number"})

    def test_from_dict_extra_fields(self):
        """Test from_dict with extra fields (should be ignored)."""
        data = {"order_number": 100, "pickup_number": 50, "message": "test", "extra_field": "should_be_ignored"}

        action = KdsAction.from_dict(data)

        assert action.order_number == 100
        assert action.pickup_number == 50
        assert action.message == "test"
        # Extra field should not be present
        assert not hasattr(action, "extra_field")


class TestKdsActionEdgeCases:
    """Test suite for KdsAction edge cases and boundary conditions."""

    def test_float_conversion_to_int(self):
        """Test that float values with fractional parts raise validation errors."""
        with pytest.raises(ValidationError):
            KdsAction(order_number=100.7, pickup_number=50.2)

        # Test that whole number floats are accepted
        action = KdsAction(order_number=100.0, pickup_number=50.0)
        assert action.order_number == 100
        assert action.pickup_number == 50
        assert isinstance(action.order_number, int)
        assert isinstance(action.pickup_number, int)

    def test_string_number_conversion(self):
        """Test that string numbers are converted to int."""
        action = KdsAction(order_number="123", pickup_number="456")

        assert action.order_number == 123
        assert action.pickup_number == 456
        assert isinstance(action.order_number, int)
        assert isinstance(action.pickup_number, int)

    def test_empty_string_message(self):
        """Test KdsAction with empty string message."""
        action = KdsAction(message="")
        assert action.message == ""

    def test_whitespace_only_message(self):
        """Test KdsAction with whitespace-only message."""
        action = KdsAction(message="   ")
        assert action.message == "   "

    def test_very_long_message(self):
        """Test KdsAction with very long message."""
        long_message = "x" * 10000
        action = KdsAction(message=long_message)
        assert action.message == long_message
        assert len(action.message) == 10000

    def test_unicode_message(self):
        """Test KdsAction with Unicode characters in message."""
        unicode_message = "Test 🚀 message with émojis and spëcial chars"
        action = KdsAction(message=unicode_message)
        assert action.message == unicode_message

    def test_model_equality(self):
        """Test equality comparison between KdsAction instances."""
        action1 = KdsAction(order_number=100, pickup_number=50, message="test")
        action2 = KdsAction(order_number=100, pickup_number=50, message="test")
        action3 = KdsAction(order_number=200, pickup_number=50, message="test")

        assert action1 == action2
        assert action1 != action3

    def test_model_repr(self):
        """Test string representation of KdsAction."""
        action = KdsAction(order_number=100, pickup_number=50, message="test")
        repr_str = repr(action)

        assert "KdsAction" in repr_str
        assert "order_number=100" in repr_str
        assert "pickup_number=50" in repr_str
        assert "message='test'" in repr_str


class TestKdsActionIntegration:
    """Integration tests for KdsAction with various scenarios."""

    @pytest.fixture
    def sample_kds_actions(self):
        """Fixture providing sample KdsAction instances."""
        return [
            KdsAction(),  # Default
            KdsAction(order_number=100),  # Partial
            KdsAction(order_number=200, pickup_number=75, message="complete"),  # Complete
            KdsAction(pickup_number=0, message=""),  # Edge values
        ]

    def test_batch_serialization(self, sample_kds_actions):
        """Test serialization of multiple KdsAction instances."""
        serialized = [action.to_dict() for action in sample_kds_actions]

        assert len(serialized) == 4
        assert all(isinstance(data, dict) for data in serialized)

        # Verify specific values
        assert serialized[0]["order_number"] is None
        assert serialized[1]["order_number"] == 100
        assert serialized[2]["message"] == "complete"
        assert serialized[3]["pickup_number"] == 0

    def test_batch_deserialization(self, sample_kds_actions):
        """Test deserialization of multiple KdsAction instances."""
        # Serialize first
        serialized = [action.to_dict() for action in sample_kds_actions]

        # Then deserialize
        deserialized = [KdsAction.from_dict(data) for data in serialized]

        assert len(deserialized) == 4
        assert all(isinstance(action, KdsAction) for action in deserialized)

        # Verify they match original
        for original, restored in zip(sample_kds_actions, deserialized):
            assert original == restored

    def test_json_compatibility(self):
        """Test JSON serialization compatibility."""
        import json

        action = KdsAction(order_number=123, pickup_number=456, message="json_test")

        # Convert to dict and then to JSON
        data_dict = action.to_dict()
        json_str = json.dumps(data_dict)

        # Parse back from JSON
        parsed_dict = json.loads(json_str)
        restored_action = KdsAction.from_dict(parsed_dict)

        assert restored_action == action

    def test_model_copy(self):
        """Test copying KdsAction instances."""
        original = KdsAction(order_number=100, pickup_number=50, message="original")

        # Test copy with modifications
        copied = original.model_copy(update={"message": "copied"})

        assert copied.order_number == original.order_number
        assert copied.pickup_number == original.pickup_number
        assert copied.message == "copied"
        assert original.message == "original"  # Original unchanged

    def test_model_dump_json(self):
        """Test JSON dumping directly from model."""
        action = KdsAction(order_number=100, pickup_number=50, message="json_dump")

        json_str = action.model_dump_json()

        assert isinstance(json_str, str)
        assert "100" in json_str
        assert "50" in json_str
        assert "json_dump" in json_str
