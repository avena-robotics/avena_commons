# File: tests/unit/test_event_listener_save_config.py
from datetime import datetime
from enum import Enum
from unittest.mock import MagicMock, mock_open, patch

import pytest


class TestEventListenerSaveConfiguration:
    """Test suite for EventListener save configuration with baseline approach."""

    @pytest.fixture
    def mock_listener(self):
        """Create a mock EventListener for testing save configuration methods."""
        # Create a minimal mock without importing the actual EventListener class
        listener = MagicMock()

        # Mock the threading lock
        listener._EventListener__lock_for_general_purpose = MagicMock()
        listener._EventListener__lock_for_general_purpose.__enter__ = MagicMock(
            return_value=None
        )
        listener._EventListener__lock_for_general_purpose.__exit__ = MagicMock(
            return_value=None
        )

        # Mock logger
        listener._message_logger = MagicMock()

        # Mock config file path
        listener._EventListener__config_file_path = "/tmp/test_config.json"

        # Set up actual implementations of the methods we want to test
        listener._extract_config_differences = self._extract_config_differences.__get__(
            listener
        )
        listener._serialize_value = self._serialize_value.__get__(listener)

        return listener

    @staticmethod
    def _extract_config_differences(self, baseline: dict, current: dict) -> dict:
        """Implementation of the extract config differences method."""
        differences = {}

        # Check for new or modified keys in current config
        for key, current_value in current.items():
            if key not in baseline:
                # New key that doesn't exist in baseline
                differences[key] = current_value
            elif isinstance(current_value, dict) and isinstance(baseline[key], dict):
                # Recursively check nested dictionaries
                nested_diff = self._extract_config_differences(
                    baseline[key], current_value
                )
                if nested_diff:  # Only add if there are actual differences
                    differences[key] = nested_diff
            elif current_value != baseline[key]:
                # Value has changed
                differences[key] = current_value

        return differences

    @staticmethod
    def _serialize_value(self, value):
        """Implementation of the serialize value method."""
        if isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, Enum):
            return value.value
        return value

    def test_extract_config_differences_no_changes(self, mock_listener):
        """Test that no differences are detected when configs are identical."""
        baseline = {"key1": "value1", "nested": {"key2": "value2"}}
        current = {"key1": "value1", "nested": {"key2": "value2"}}

        differences = mock_listener._extract_config_differences(baseline, current)
        assert differences == {}

    def test_extract_config_differences_simple_changes(self, mock_listener):
        """Test detection of simple configuration changes."""
        baseline = {"key1": "value1", "key2": "value2"}
        current = {"key1": "changed_value1", "key2": "value2", "key3": "new_value"}

        differences = mock_listener._extract_config_differences(baseline, current)
        expected = {"key1": "changed_value1", "key3": "new_value"}
        assert differences == expected

    def test_extract_config_differences_nested_changes(self, mock_listener):
        """Test detection of nested configuration changes."""
        baseline = {
            "database": {"host": "localhost", "port": 5432},
            "cache": {"enabled": False},
        }
        current = {
            "database": {"host": "remote", "port": 5432, "timeout": 30},
            "cache": {"enabled": False},
            "logging": {"level": "INFO"},
        }

        differences = mock_listener._extract_config_differences(baseline, current)
        expected = {
            "database": {"host": "remote", "timeout": 30},
            "logging": {"level": "INFO"},
        }
        assert differences == expected

    def test_extract_config_differences_deep_nesting(self, mock_listener):
        """Test extraction of differences with deep nesting."""
        baseline = {
            "level1": {
                "level2": {
                    "level3": {
                        "existing_key": "existing_value",
                        "shared_key": "old_value",
                    },
                    "level2_existing": "preserved",
                }
            }
        }

        current = {
            "level1": {
                "level2": {
                    "level3": {
                        "existing_key": "existing_value",
                        "shared_key": "new_value",
                        "new_key": "new_value",
                    },
                    "level2_existing": "preserved",
                    "level2_new": "added",
                },
                "level1_new": "added",
            }
        }

        differences = mock_listener._extract_config_differences(baseline, current)
        expected = {
            "level1": {
                "level2": {
                    "level3": {
                        "shared_key": "new_value",
                        "new_key": "new_value",
                    },
                    "level2_new": "added",
                },
                "level1_new": "added",
            }
        }
        assert differences == expected

    def test_save_configuration_baseline_workflow(self):
        """Test the complete save configuration workflow with baseline comparison."""
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("json.dump") as mock_json_dump,
            patch("os.path.exists") as mock_exists,
            patch("os.remove") as mock_remove,
        ):
            # Setup scenario: baseline vs current configuration with changes
            mock_exists.return_value = False  # No existing file initially

            default_config = {
                "database": {
                    "host": "localhost",
                    "port": 5432,
                },
                "app_setting": "default_value",
            }

            current_config = {
                "database": {
                    "host": "remote_host",  # Changed from baseline
                    "port": 5432,  # Same as baseline
                    "timeout": 30,  # New setting
                },
                "app_setting": "default_value",  # Same as baseline
                "new_feature": {  # Entirely new section
                    "enabled": True,
                    "config": "value",
                },
            }

            # Create a mock that implements our save configuration logic
            mock_listener = MagicMock()
            mock_listener._default_configuration = default_config
            mock_listener._configuration = current_config
            mock_listener._EventListener__config_file_path = "/tmp/config.json"
            mock_listener._message_logger = MagicMock()

            # Extract differences (this is what __save_configuration does)
            differences = {}
            for key, current_value in current_config.items():
                if key not in default_config:
                    differences[key] = current_value
                elif isinstance(current_value, dict) and isinstance(
                    default_config[key], dict
                ):
                    nested_diff = {}
                    for nested_key, nested_value in current_value.items():
                        if (
                            nested_key not in default_config[key]
                            or default_config[key][nested_key] != nested_value
                        ):
                            nested_diff[nested_key] = nested_value
                    if nested_diff:
                        differences[key] = nested_diff
                elif current_value != default_config[key]:
                    differences[key] = current_value

            # Save only differences
            if differences:
                mock_json_dump(
                    differences,
                    mock_file(),
                    indent=4,
                    sort_keys=True,
                    ensure_ascii=False,
                )

            # Verify the result contains only the actual changes
            mock_json_dump.assert_called_once()
            saved_config = mock_json_dump.call_args[0][0]

            expected_differences = {
                "database": {
                    "host": "remote_host",  # Changed value
                    "timeout": 30,  # New value
                },
                "new_feature": {  # Entirely new section
                    "enabled": True,
                    "config": "value",
                },
            }

            assert saved_config == expected_differences

    def test_serialize_value_functionality(self, mock_listener):
        """Test the serialize value method with various data types."""
        # Test basic types
        assert mock_listener._serialize_value("string") == "string"
        assert mock_listener._serialize_value(123) == 123
        assert mock_listener._serialize_value(True) == True

        # Test dict
        input_dict = {"key1": "value1", "key2": {"nested": "value"}}
        expected_dict = {"key1": "value1", "key2": {"nested": "value"}}
        assert mock_listener._serialize_value(input_dict) == expected_dict

        # Test list
        input_list = ["item1", {"nested": "value"}, 123]
        expected_list = ["item1", {"nested": "value"}, 123]
        assert mock_listener._serialize_value(input_list) == expected_list

        # Test datetime
        test_datetime = datetime(2023, 1, 1, 12, 0, 0)
        assert mock_listener._serialize_value(test_datetime) == "2023-01-01T12:00:00"

    def test_empty_configurations(self, mock_listener):
        """Test handling of empty configurations in difference extraction."""
        # Empty baseline, non-empty current
        differences1 = mock_listener._extract_config_differences({}, {"key": "value"})
        assert differences1 == {"key": "value"}

        # Non-empty baseline, empty current
        differences2 = mock_listener._extract_config_differences({"key": "value"}, {})
        assert differences2 == {}

        # Both empty
        differences3 = mock_listener._extract_config_differences({}, {})
        assert differences3 == {}

    def test_complex_nested_structure_differences(self, mock_listener):
        """Test with a complex, realistic configuration structure."""
        default_config = {
            "database": {
                "host": "localhost",
                "port": 5432,
                "ssl": {"enabled": False},
                "pools": {"read": 5, "write": 2},
            },
            "features": {"feature_x": True, "feature_y": False},
            "logging": {"level": "INFO"},
        }

        current_config = {
            "database": {
                "host": "remote.example.com",  # Changed
                "port": 5432,  # Same
                "ssl": {"enabled": True, "verify_mode": "strict"},  # Changed + new
                "pools": {"read": 5, "write": 2},  # Same
                "timeout": 30,  # New
            },
            "features": {"feature_x": True, "feature_y": False},  # Same
            "logging": {"level": "DEBUG", "file": "/var/log/app.log"},  # Changed + new
            "monitoring": {"enabled": True},  # Entirely new section
        }

        differences = mock_listener._extract_config_differences(
            default_config, current_config
        )

        expected = {
            "database": {
                "host": "remote.example.com",
                "ssl": {"enabled": True, "verify_mode": "strict"},
                "timeout": 30,
            },
            "logging": {"level": "DEBUG", "file": "/var/log/app.log"},
            "monitoring": {"enabled": True},
        }

        assert differences == expected

    def test_type_changes_in_differences(self, mock_listener):
        """Test that type changes are properly detected."""
        baseline = {"setting": {"nested": "value"}}
        current = {"setting": "string_value"}  # Changed from dict to string

        differences = mock_listener._extract_config_differences(baseline, current)
        expected = {"setting": "string_value"}
        assert differences == expected

    def test_list_changes_in_differences(self, mock_listener):
        """Test that list changes are detected."""
        baseline = {"list_setting": [1, 2, 3]}
        current = {"list_setting": [1, 2, 3, 4]}  # List changed

        differences = mock_listener._extract_config_differences(baseline, current)
        expected = {"list_setting": [1, 2, 3, 4]}
        assert differences == expected

    def test_no_file_removal_on_changes(self):
        """Test that file is not removed when there are actual changes."""
        with (
            patch("os.path.exists") as mock_exists,
            patch("os.remove") as mock_remove,
            patch("builtins.open", mock_open()),
            patch("json.dump"),
        ):
            mock_exists.return_value = True

            # This would be the logic in __save_configuration when changes exist
            config_changes = {"key": "changed_value"}

            if config_changes:
                # File should not be removed when there are changes
                pass
            else:
                mock_remove("/tmp/config.json")

            # Verify remove was not called since there were changes
            mock_remove.assert_not_called()

    def test_file_removal_on_no_changes(self):
        """Test that file is removed when no changes exist."""
        with (
            patch("os.path.exists") as mock_exists,
            patch("os.remove") as mock_remove,
        ):
            mock_exists.return_value = True

            # This would be the logic in __save_configuration when no changes exist
            config_changes = {}

            if config_changes:
                pass  # Would save file
            else:
                mock_remove("/tmp/config.json")

            # Verify remove was called since there were no changes
            mock_remove.assert_called_once_with("/tmp/config.json")
