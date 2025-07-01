# File: tests/integration/test_event_listener_config_integration.py
from unittest.mock import MagicMock

import pytest


class TestEventListenerConfigurationIntegration:
    """Integration tests for the complete baseline configuration load-save workflow."""

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
        listener._configuration = {}
        listener._default_configuration = {}

        # Bind actual method implementations
        listener._merge_configuration = self._merge_configuration.__get__(listener)
        listener._merge_dict_recursive = self._merge_dict_recursive.__get__(listener)
        listener._extract_config_differences = self._extract_config_differences.__get__(
            listener
        )

        return listener

    @staticmethod
    def _merge_configuration(self, config_data: dict):
        """Merge loaded configuration data with default configuration."""
        for key, value in config_data.items():
            if key in self._default_configuration:
                if isinstance(self._configuration[key], dict) and isinstance(
                    value, dict
                ):
                    self._configuration[key] = self._merge_dict_recursive(
                        self._configuration[key], value
                    )
                else:
                    self._configuration[key] = value
            else:
                self._configuration[key] = value

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

    @staticmethod
    def _extract_config_differences(self, baseline: dict, current: dict) -> dict:
        """Extract differences between baseline and current configuration."""
        differences = {}

        for key, current_value in current.items():
            if key not in baseline:
                differences[key] = current_value
            elif isinstance(current_value, dict) and isinstance(baseline[key], dict):
                nested_diff = self._extract_config_differences(
                    baseline[key], current_value
                )
                if nested_diff:
                    differences[key] = nested_diff
            elif current_value != baseline[key]:
                differences[key] = current_value

        return differences

    def test_complete_baseline_workflow(self, mock_listener):
        """Test the complete workflow: load with baseline, modify, save only changes."""
        # Step 1: Application sets up initial defaults (baseline)
        app_defaults = {
            "database": {"host": "localhost", "port": 5432, "ssl": False},
            "app_setting": "default_value",
            "features": {"feature_a": True, "feature_b": False},
        }
        mock_listener._configuration = app_defaults.copy()

        # Establish baseline (this happens in __load_configuration)
        mock_listener._default_configuration = app_defaults.copy()

        # Step 2: Load user changes from file
        user_changes = {
            "database": {"host": "remote_host", "timeout": 30},
            "user_setting": "custom_value",
            "features": {"feature_b": True, "feature_c": True},
        }

        # Merge user changes (this happens in __load_configuration)
        mock_listener._merge_configuration(user_changes)

        # Verify working configuration after load
        expected_working = {
            "database": {
                "host": "remote_host",
                "port": 5432,
                "ssl": False,
                "timeout": 30,
            },
            "app_setting": "default_value",
            "user_setting": "custom_value",
            "features": {"feature_a": True, "feature_b": True, "feature_c": True},
        }
        assert mock_listener._configuration == expected_working

        # Step 3: Application modifies some settings during runtime
        mock_listener._configuration["database"]["ssl"] = True
        mock_listener._configuration["app_setting"] = "runtime_changed"
        mock_listener._configuration["new_runtime_setting"] = "added"

        # Step 4: Extract differences for saving (this happens in __save_configuration)
        differences = mock_listener._extract_config_differences(
            mock_listener._default_configuration, mock_listener._configuration
        )

        # Verify only changes from baseline are extracted
        expected_differences = {
            "database": {"host": "remote_host", "ssl": True, "timeout": 30},
            "user_setting": "custom_value",
            "app_setting": "runtime_changed",
            "features": {"feature_b": True, "feature_c": True},
            "new_runtime_setting": "added",
        }
        assert differences == expected_differences

    def test_baseline_preserves_user_changes(self, mock_listener):
        """Test that baseline approach correctly preserves user customizations."""
        # Application baseline
        app_default = {
            "section1": {"app_key1": "app_value1", "shared_key": "app_default"},
            "app_section": {"setting": "default"},
        }
        mock_listener._configuration = app_default.copy()
        mock_listener._default_configuration = app_default.copy()

        # User made changes in config file
        user_file_changes = {
            "section1": {"shared_key": "user_custom", "user_key1": "user_value1"},
            "user_section": {"custom_setting": "user_custom"},
        }

        # Load user changes
        mock_listener._merge_configuration(user_file_changes)

        # Application makes runtime changes
        mock_listener._configuration["app_section"]["setting"] = "runtime_changed"
        mock_listener._configuration["section1"]["app_key1"] = "runtime_changed"

        # Extract differences - should preserve user changes and include app runtime changes
        differences = mock_listener._extract_config_differences(
            mock_listener._default_configuration, mock_listener._configuration
        )

        expected = {
            "section1": {
                "app_key1": "runtime_changed",  # App runtime change
                "shared_key": "user_custom",  # User customization preserved
                "user_key1": "user_value1",  # User addition preserved
            },
            "app_section": {
                "setting": "runtime_changed"  # App runtime change
            },
            "user_section": {
                "custom_setting": "user_custom"  # User section preserved
            },
        }
        assert differences == expected

    def test_no_changes_means_no_save(self, mock_listener):
        """Test that when config equals baseline, no changes are detected."""
        default_config = {
            "key1": "value1",
            "nested": {"key2": "value2", "key3": "value3"},
        }

        mock_listener._default_configuration = default_config.copy()
        mock_listener._configuration = default_config.copy()

        # No changes made - config identical to baseline
        differences = mock_listener._extract_config_differences(
            mock_listener._default_configuration, mock_listener._configuration
        )

        # Should detect no changes
        assert differences == {}

    def test_partial_revert_to_baseline(self, mock_listener):
        """Test scenario where some settings revert to baseline values."""
        baseline = {
            "database": {"host": "localhost", "port": 5432},
            "setting1": "default_value",
        }
        mock_listener._default_configuration = baseline.copy()

        # Initially load some changes
        initial_changes = {
            "database": {"host": "remote_host", "timeout": 30},
            "setting1": "custom_value",
            "new_setting": "added_value",
        }
        mock_listener._configuration = baseline.copy()
        mock_listener._merge_configuration(initial_changes)

        # Later, revert some settings to baseline values
        mock_listener._configuration["database"]["host"] = (
            "localhost"  # Back to baseline
        )
        mock_listener._configuration["setting1"] = "default_value"  # Back to baseline

        # Extract differences
        differences = mock_listener._extract_config_differences(
            mock_listener._default_configuration, mock_listener._configuration
        )

        # Should only contain actual changes from baseline
        expected = {
            "database": {"timeout": 30},  # Still changed from baseline
            "new_setting": "added_value",  # Still added from baseline
        }
        assert differences == expected

    def test_complex_nested_changes_and_preservations(self, mock_listener):
        """Test complex scenario with deep nesting and mixed changes."""
        baseline = {
            "level1": {
                "level2": {
                    "app_setting": "app_default",
                    "shared_setting": "shared_default",
                    "level3": {
                        "deep_app": "deep_app_default",
                        "deep_shared": "deep_shared_default",
                    },
                }
            },
            "app_root": "app_root_default",
        }
        mock_listener._default_configuration = baseline.copy()
        mock_listener._configuration = baseline.copy()

        # User changes loaded from file
        user_changes = {
            "level1": {
                "level2": {
                    "shared_setting": "user_custom",
                    "user_setting": "user_value",
                    "level3": {
                        "deep_shared": "user_deep_custom",
                        "deep_user": "user_deep_value",
                    },
                },
                "user_level2": {"user_nested": "user_nested_value"},
            },
            "user_root": "user_root_value",
        }
        mock_listener._merge_configuration(user_changes)

        # Application makes runtime changes
        mock_listener._configuration["level1"]["level2"]["app_setting"] = (
            "runtime_changed"
        )
        mock_listener._configuration["app_root"] = "runtime_changed"

        # Extract differences
        differences = mock_listener._extract_config_differences(
            mock_listener._default_configuration, mock_listener._configuration
        )

        expected = {
            "level1": {
                "level2": {
                    "app_setting": "runtime_changed",  # App runtime change
                    "shared_setting": "user_custom",  # User customization
                    "user_setting": "user_value",  # User addition
                    "level3": {
                        "deep_shared": "user_deep_custom",  # User deep customization
                        "deep_user": "user_deep_value",  # User deep addition
                    },
                },
                "user_level2": {  # User section
                    "user_nested": "user_nested_value"
                },
            },
            "app_root": "runtime_changed",  # App runtime change
            "user_root": "user_root_value",  # User root addition
        }
        assert differences == expected

    def test_empty_baseline_scenario(self, mock_listener):
        """Test scenario where baseline is empty (fresh installation)."""
        # Empty baseline (fresh app installation)
        mock_listener._default_configuration = {}
        mock_listener._configuration = {}

        # User adds some configuration
        user_config = {
            "database": {"host": "user_host", "port": 3306},
            "user_setting": "user_value",
        }
        mock_listener._merge_configuration(user_config)

        # Extract differences
        differences = mock_listener._extract_config_differences(
            mock_listener._default_configuration, mock_listener._configuration
        )

        # Everything should be considered a change since baseline is empty
        assert differences == user_config

    def test_type_changes_in_nested_config(self, mock_listener):
        """Test handling of type changes in nested configuration."""
        baseline = {"setting": {"nested": "dict_value"}, "list_setting": [1, 2, 3]}
        mock_listener._default_configuration = baseline.copy()
        mock_listener._configuration = baseline.copy()

        # Change types
        mock_listener._configuration["setting"] = "string_value"  # Dict -> String
        mock_listener._configuration["list_setting"] = [
            4,
            5,
            6,
            7,
        ]  # List change

        differences = mock_listener._extract_config_differences(
            mock_listener._default_configuration, mock_listener._configuration
        )

        expected = {"setting": "string_value", "list_setting": [4, 5, 6, 7]}
        assert differences == expected
