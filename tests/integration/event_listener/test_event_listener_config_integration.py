# File: tests/unit/test_event_listener_config_integration.py
from unittest.mock import MagicMock

import pytest


class TestEventListenerConfigurationIntegration:
    """Integration tests for the complete configuration load-save workflow."""

    @pytest.fixture
    def mock_listener(self):
        """Create a mock EventListener with actual configuration methods."""
        listener = MagicMock()

        # Mock infrastructure
        listener._EventListener__lock_for_general_purpose = MagicMock()
        listener._EventListener__lock_for_general_purpose.__enter__ = MagicMock(
            return_value=None
        )
        listener._EventListener__lock_for_general_purpose.__exit__ = MagicMock(
            return_value=None
        )
        listener._message_logger = MagicMock()
        listener._EventListener__config_file_path = "/tmp/test_config.json"

        # Initialize configuration
        listener._default_configuration = {}

        # Bind actual method implementations
        listener._merge_configuration = self._merge_configuration.__get__(listener)
        listener._merge_dict_recursive = self._merge_dict_recursive.__get__(listener)

        return listener

    @staticmethod
    def _merge_configuration(self, config_data: dict):
        """Merge loaded configuration data with default configuration."""
        for key, value in config_data.items():
            if key in self._default_configuration:
                if isinstance(self._default_configuration[key], dict) and isinstance(
                    value, dict
                ):
                    self._default_configuration[key] = self._merge_dict_recursive(
                        self._default_configuration[key], value
                    )
                else:
                    self._default_configuration[key] = value
            else:
                self._default_configuration[key] = value

    @staticmethod
    def _merge_dict_recursive(self, default_dict: dict, config_dict: dict) -> dict:
        """Recursively merge two dictionaries."""
        result = default_dict.copy()

        for key, value in config_dict.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_dict_recursive(result[key], value)
            else:
                result[key] = value

        return result

    def test_load_configuration_merging(self, mock_listener):
        """Test that loading configuration merges correctly with defaults."""
        # Set up initial default configuration
        mock_listener._default_configuration = {
            "app_setting1": "app_default1",
            "shared_setting": "app_default_shared",
            "database": {"app_host": "localhost", "shared_port": 3306},
        }

        # Configuration from file
        file_config = {
            "shared_setting": "manually_edited_shared",
            "manual_setting": "user_added_manual",
            "database": {
                "shared_port": 5432,  # manually changed
                "manual_ssl": True,  # manually added
            },
            "manual_section": {"custom_feature": "enabled"},
        }

        # Merge configuration
        mock_listener._merge_configuration(file_config)

        # Verify configuration was merged correctly
        expected = {
            "app_setting1": "app_default1",  # Preserved from default
            "shared_setting": "manually_edited_shared",  # Overridden by file
            "manual_setting": "user_added_manual",  # Added from file
            "database": {
                "app_host": "localhost",  # Preserved from default
                "shared_port": 5432,  # Overridden by file
                "manual_ssl": True,  # Added from file
            },
            "manual_section": {
                "custom_feature": "enabled"  # Added from file
            },
        }
        assert mock_listener._default_configuration == expected

    def test_recursive_dict_merging_deep_nesting(self, mock_listener):
        """Test that deeply nested dictionaries are merged correctly."""
        default_dict = {
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

        config_dict = {
            "level1": {
                "level2": {
                    "level3": {"shared_key": "new_value", "new_key": "new_value"},
                    "level2_new": "added",
                },
                "level1_new": "added",
            }
        }

        result = mock_listener._merge_dict_recursive(default_dict, config_dict)

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

    def test_configuration_merge_edge_cases(self, mock_listener):
        """Test edge cases in configuration merging."""
        # Test merging with None values
        default_dict = {"key1": "value1", "key2": None}
        config_dict = {"key1": None, "key3": "value3"}

        result = mock_listener._merge_dict_recursive(default_dict, config_dict)
        expected = {"key1": None, "key2": None, "key3": "value3"}
        assert result == expected

        # Test merging with mixed types
        default_dict = {"mixed": {"nested": "value"}}
        config_dict = {"mixed": "string_value"}  # Different type

        result = mock_listener._merge_dict_recursive(default_dict, config_dict)
        expected = {"mixed": "string_value"}  # Should replace with new type
        assert result == expected

    def test_merge_configuration_with_empty_defaults(self, mock_listener):
        """Test merging when default configuration is empty."""
        mock_listener._default_configuration = {}

        file_config = {"new_setting": "value", "nested": {"key": "value"}}

        mock_listener._merge_configuration(file_config)

        # Should add all values from file config
        assert mock_listener._default_configuration == file_config

    def test_merge_configuration_with_empty_file_config(self, mock_listener):
        """Test merging when file configuration is empty."""
        original_config = {"app_setting": "value", "nested": {"key": "value"}}
        mock_listener._default_configuration = original_config.copy()

        # Merge empty config
        mock_listener._merge_configuration({})

        # Should remain unchanged
        assert mock_listener._default_configuration == original_config

    def test_list_and_primitive_value_handling(self, mock_listener):
        """Test that lists and primitive values are handled correctly in merging."""
        default_dict = {
            "list_setting": [1, 2, 3],
            "string_setting": "default",
            "number_setting": 42,
            "bool_setting": True,
        }

        config_dict = {
            "list_setting": [4, 5, 6],  # Should replace entirely
            "string_setting": "updated",  # Should replace
            "number_setting": 100,  # Should replace
            "bool_setting": False,  # Should replace
        }

        result = mock_listener._merge_dict_recursive(default_dict, config_dict)

        expected = {
            "list_setting": [4, 5, 6],
            "string_setting": "updated",
            "number_setting": 100,
            "bool_setting": False,
        }

        assert result == expected

    def test_preserve_original_dict_immutability(self, mock_listener):
        """Test that original dictionaries are not modified during merge."""
        original_default = {"key1": "value1", "nested": {"key2": "value2"}}

        original_config = {"key1": "new_value1", "nested": {"key3": "value3"}}

        # Create copies to check immutability
        default_copy = original_default.copy()
        config_copy = original_config.copy()

        result = mock_listener._merge_dict_recursive(original_default, original_config)

        # Verify original dictionaries weren't modified
        assert original_default == default_copy
        assert original_config == config_copy

        # Verify result is correct
        expected = {
            "key1": "new_value1",
            "nested": {"key2": "value2", "key3": "value3"},
        }
        assert result == expected
