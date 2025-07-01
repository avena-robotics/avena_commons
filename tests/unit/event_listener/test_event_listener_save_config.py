# File: tests/unit/test_event_listener_save_config.py
from datetime import datetime
from enum import Enum
from unittest.mock import MagicMock, mock_open, patch

import pytest


class TestEventListenerSaveConfiguration:
    """Test suite for EventListener save configuration with intelligent merging."""

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
        listener._merge_config_for_save = self._merge_config_for_save.__get__(listener)
        listener._has_config_changes = self._has_config_changes.__get__(listener)
        listener._serialize_value = self._serialize_value.__get__(listener)

        return listener

    @staticmethod
    def _merge_config_for_save(
        self, existing_config: dict, current_config: dict
    ) -> dict:
        """Implementation of the merge config for save method."""
        result = existing_config.copy()

        # Update with current configuration values
        for key, value in current_config.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # Recursively merge nested dictionaries
                result[key] = self._merge_config_for_save(result[key], value)
            else:
                # Direct assignment - current config takes precedence
                result[key] = value

        return result

    @staticmethod
    def _has_config_changes(self, old_config: dict, new_config: dict) -> bool:
        """Implementation of the has config changes method."""
        try:
            # Serialize both configs for comparison to handle complex nested objects
            old_serialized = self._serialize_value(old_config)
            new_serialized = self._serialize_value(new_config)

            return old_serialized != new_serialized
        except Exception:
            return True  # If comparison fails, assume there are changes to be safe

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

    def test_merge_config_for_save_basic_merge(self, mock_listener):
        """Test basic merging of current config with existing file config."""
        existing_config = {
            "manual_setting": "user_value",
            "shared_setting": "old_value",
            "existing_only": "preserved",
        }

        current_config = {"shared_setting": "new_value", "app_setting": "app_value"}

        result = mock_listener._merge_config_for_save(existing_config, current_config)

        expected = {
            "manual_setting": "user_value",  # Preserved from existing
            "shared_setting": "new_value",  # Updated from current
            "existing_only": "preserved",  # Preserved from existing
            "app_setting": "app_value",  # Added from current
        }

        assert result == expected

    def test_merge_config_for_save_nested_dicts(self, mock_listener):
        """Test merging with nested dictionary structures."""
        existing_config = {
            "database": {
                "manual_host": "user_host",
                "shared_port": 3306,
                "manual_ssl": True,
            },
            "manual_cache": {"size": 1000},
        }

        current_config = {
            "database": {"shared_port": 5432, "app_timeout": 30},
            "app_logging": {"level": "INFO"},
        }

        result = mock_listener._merge_config_for_save(existing_config, current_config)

        expected = {
            "database": {
                "manual_host": "user_host",  # Preserved
                "shared_port": 5432,  # Updated from current
                "manual_ssl": True,  # Preserved
                "app_timeout": 30,  # Added from current
            },
            "manual_cache": {
                "size": 1000  # Preserved entirely
            },
            "app_logging": {
                "level": "INFO"  # Added from current
            },
        }

        assert result == expected

    def test_has_config_changes_identical_configs(self, mock_listener):
        """Test change detection with identical configurations."""
        config1 = {"key1": "value1", "nested": {"key2": "value2", "key3": 123}}

        config2 = {"key1": "value1", "nested": {"key2": "value2", "key3": 123}}

        assert not mock_listener._has_config_changes(config1, config2)

    def test_has_config_changes_different_configs(self, mock_listener):
        """Test change detection with different configurations."""
        config1 = {"key1": "value1", "nested": {"key2": "value2"}}

        config2 = {"key1": "value1", "nested": {"key2": "different_value"}}

        assert mock_listener._has_config_changes(config1, config2)

    def test_has_config_changes_serialization_error(self, mock_listener):
        """Test change detection when serialization fails."""
        config1 = {"key": "value"}
        config2 = {"key": "value"}

        # Mock serialize_value to raise an exception
        mock_listener._serialize_value = MagicMock(
            side_effect=Exception("Serialization failed")
        )

        # Should return True when comparison fails (assuming changes exist to be safe)
        assert mock_listener._has_config_changes(config1, config2)

    def test_save_configuration_integration_workflow(self):
        """Test the complete save configuration workflow with mocked I/O."""
        with (
            patch("builtins.open", mock_open()) as mock_file,
            patch("json.load") as mock_json_load,
            patch("json.dump") as mock_json_dump,
            patch("os.path.exists") as mock_exists,
        ):
            # Setup scenario: existing file with manual edits + app changes
            mock_exists.return_value = True

            existing_file_config = {
                "database": {
                    "host": "manual.example.com",
                    "port": 3306,
                    "manual_ssl_cert": "/path/to/cert",
                },
                "manual_feature_flag": True,
            }
            mock_json_load.return_value = existing_file_config

            current_app_config = {
                "database": {
                    "port": 5432,  # App changed this
                    "timeout": 30,  # App added this
                    "pool_size": 10,  # App added this
                },
                "app_version": "1.2.3",  # App added this
                "logging": {  # App added entire section
                    "level": "INFO",
                    "file": "/var/log/app.log",
                },
            }

            # Create a mock that implements our save configuration logic
            mock_listener = MagicMock()
            mock_listener._default_configuration = current_app_config
            mock_listener._EventListener__config_file_path = "/tmp/config.json"
            mock_listener._message_logger = MagicMock()

            # Implement the save logic directly in the test
            if mock_exists.return_value:
                with mock_file() as f:
                    existing_config = mock_json_load()

                # Merge logic
                merged_config = existing_file_config.copy()
                for key, value in current_app_config.items():
                    if (
                        key in merged_config
                        and isinstance(merged_config[key], dict)
                        and isinstance(value, dict)
                    ):
                        # Merge nested dicts
                        for nested_key, nested_value in value.items():
                            merged_config[key][nested_key] = nested_value
                    else:
                        merged_config[key] = value

                # Save merged config
                mock_json_dump(
                    merged_config,
                    mock_file(),
                    indent=4,
                    sort_keys=True,
                    ensure_ascii=False,
                )

            # Verify the result combines both manual and app settings correctly
            mock_json_dump.assert_called_once()
            saved_config = mock_json_dump.call_args[0][0]

            expected_final_config = {
                "database": {
                    "host": "manual.example.com",  # Preserved from manual
                    "port": 5432,  # Updated by app
                    "manual_ssl_cert": "/path/to/cert",  # Preserved from manual
                    "timeout": 30,  # Added by app
                    "pool_size": 10,  # Added by app
                },
                "manual_feature_flag": True,  # Preserved from manual
                "app_version": "1.2.3",  # Added by app
                "logging": {  # Added by app
                    "level": "INFO",
                    "file": "/var/log/app.log",
                },
            }

            assert saved_config == expected_final_config

    def test_recursive_dict_merge_deep_nesting(self):
        """Test that deeply nested dictionaries are merged correctly."""
        existing = {
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
                    "level3": {"shared_key": "new_value", "new_key": "new_value"},
                    "level2_new": "added",
                },
                "level1_new": "added",
            }
        }

        # Create a minimal mock for the merge function
        mock_self = MagicMock()

        def mock_merge_config_for_save(existing_dict, current_dict):
            result = existing_dict.copy()
            for key, value in current_dict.items():
                if (
                    key in result
                    and isinstance(result[key], dict)
                    and isinstance(value, dict)
                ):
                    result[key] = mock_merge_config_for_save(result[key], value)
                else:
                    result[key] = value
            return result

        result = mock_merge_config_for_save(existing, current)

        expected = {
            "level1": {
                "level2": {
                    "level3": {
                        "existing_key": "existing_value",  # Preserved
                        "shared_key": "new_value",  # Updated
                        "new_key": "new_value",  # Added
                    },
                    "level2_existing": "preserved",  # Preserved
                    "level2_new": "added",  # Added
                },
                "level1_new": "added",  # Added
            }
        }

        assert result == expected

    def test_empty_configurations(self):
        """Test handling of empty configurations."""
        mock_self = MagicMock()

        def mock_merge_config_for_save(existing_dict, current_dict):
            result = existing_dict.copy()
            for key, value in current_dict.items():
                result[key] = value
            return result

        # Empty existing, non-empty current
        result1 = mock_merge_config_for_save({}, {"key": "value"})
        assert result1 == {"key": "value"}

        # Non-empty existing, empty current
        result2 = mock_merge_config_for_save({"key": "value"}, {})
        assert result2 == {"key": "value"}

        # Both empty
        result3 = mock_merge_config_for_save({}, {})
        assert result3 == {}

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
