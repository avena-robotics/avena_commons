# File: tests/unit/test_event_listener_config.py
import json
import os
import tempfile
from unittest.mock import patch

import pytest

from avena_commons.event_listener.event_listener import EventListener


class TestEventListenerConfiguration:
    """Test suite for EventListener baseline configuration management."""

    @pytest.fixture
    def temp_config_file(self):
        """Create a temporary configuration file for testing."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_config.json", delete=False
        ) as f:
            yield f.name
        # Cleanup
        if os.path.exists(f.name):
            os.unlink(f.name)

    @pytest.fixture
    def mock_listener(self, temp_config_file):
        """Create a mock EventListener for testing configuration methods."""
        # Mock to avoid full initialization
        with (
            patch("avena_commons.event_listener.event_listener.signal"),
            patch("avena_commons.event_listener.event_listener.TEMP_DIR"),
            patch.object(EventListener, "_EventListener__start_analysis"),
            patch.object(EventListener, "_EventListener__start_send_event"),
            patch.object(EventListener, "_EventListener__start_local_check"),
            patch.object(EventListener, "_EventListener__start_state_update_thread"),
        ):
            listener = EventListener(name="test", port=8000)
            listener._EventListener__config_file_path = temp_config_file
            return listener

    def test_configuration_initialization(self, mock_listener):
        """Test that baseline configuration is properly initialized."""
        # Setup initial configuration
        initial_config = {
            "default_key": "default_value",
            "nested": {"default_nested": "default_nested_value"},
        }
        mock_listener._configuration = initial_config.copy()

        # Simulate the baseline setup that happens in __load_configuration
        mock_listener._default_configuration = initial_config.copy()

        # Verify baseline is established
        assert mock_listener._default_configuration == initial_config
        assert mock_listener._configuration == initial_config

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

    def test_save_configuration_no_changes(self, mock_listener, temp_config_file):
        """Test saving configuration when no changes exist from baseline."""
        # Setup baseline and current config (identical)
        config = {"key": "value", "nested": {"key2": "value2"}}
        mock_listener._default_configuration = config.copy()
        mock_listener._configuration = config.copy()

        # Should not create config file when no changes
        mock_listener._EventListener__save_configuration()
        assert not os.path.exists(temp_config_file)

    def test_save_configuration_with_changes(self, mock_listener, temp_config_file):
        """Test saving configuration when changes exist from baseline."""
        # Setup baseline
        baseline = {"key1": "baseline_value", "nested": {"shared": "baseline_nested"}}
        mock_listener._configuration = baseline

        # Setup current config with changes
        current = {
            "key1": "changed_value",
            "nested": {"shared": "changed_nested", "new_key": "new_value"},
            "new_section": {"setting": "value"},
        }
        mock_listener._configuration = current

        # Save configuration
        mock_listener._EventListener__save_configuration()

        # Verify only changes were saved
        assert os.path.exists(temp_config_file)
        with open(temp_config_file, "r") as f:
            saved_config = json.load(f)

        expected_changes = {
            "key1": "changed_value",
            "nested": {"shared": "changed_nested", "new_key": "new_value"},
            "new_section": {"setting": "value"},
        }
        assert saved_config == expected_changes

    def test_save_configuration_removes_file_when_no_changes(
        self, mock_listener, temp_config_file
    ):
        """Test that config file is removed when no changes exist."""
        # Create initial file
        initial_content = {"old": "data"}
        with open(temp_config_file, "w") as f:
            json.dump(initial_content, f)

        # Setup identical baseline and current
        config = {"key": "value"}
        mock_listener._configuration = config
        mock_listener._configuration = config

        # Save should remove the file
        mock_listener._EventListener__save_configuration()
        assert not os.path.exists(temp_config_file)

    def test_load_configuration_establishes_baseline(
        self, mock_listener, temp_config_file
    ):
        """Test that loading configuration establishes proper baseline."""
        # Setup initial default configuration
        initial_config = {"app_default": "value", "shared": "app_value"}
        mock_listener._configuration = initial_config.copy()

        # Create config file with changes
        file_config = {"shared": "file_value", "file_only": "file_setting"}
        with open(temp_config_file, "w") as f:
            json.dump(file_config, f)

        # Load configuration
        mock_listener._EventListener__load_configuration()

        # Verify baseline was established from initial config
        assert mock_listener._default_configuration == initial_config

        # Verify working config was merged
        expected_working = {
            "app_default": "value",
            "shared": "file_value",  # Overridden from file
            "file_only": "file_setting",  # Added from file
        }
        assert mock_listener._configuration == expected_working

    def test_merge_dict_recursive(self, mock_listener):
        """Test recursive dictionary merging."""
        default_dict = {"a": 1, "b": {"c": 2, "d": 3}}

        config_dict = {"b": {"c": 20, "e": 4}, "f": 5}

        result = mock_listener._merge_dict_recursive(default_dict, config_dict)

        expected = {
            "a": 1,
            "b": {
                "c": 20,  # Updated
                "d": 3,  # Preserved
                "e": 4,  # Added
            },
            "f": 5,  # Added
        }
        assert result == expected

    def test_load_configuration_file_not_exists(self, mock_listener, temp_config_file):
        """Test loading configuration when file doesn't exist."""
        # Remove the temp file to simulate non-existence
        os.unlink(temp_config_file)

        mock_listener._configuration = {"default": "value"}
        mock_listener._EventListener__load_configuration()

        # Should remain unchanged and baseline should be established
        assert mock_listener._configuration == {"default": "value"}
        assert mock_listener._default_configuration == {"default": "value"}

    def test_load_configuration_success(self, mock_listener, temp_config_file):
        """Test successful configuration loading."""
        # Setup default configuration
        mock_listener._configuration = {
            "default_key": "default_value",
            "shared_key": "default_shared",
        }

        # Write test config to file
        config_data = {"shared_key": "loaded_shared", "loaded_key": "loaded_value"}
        with open(temp_config_file, "w") as f:
            json.dump(config_data, f)

        # Load configuration
        mock_listener._EventListener__load_configuration()

        # Verify baseline was established
        expected_baseline = {
            "default_key": "default_value",
            "shared_key": "default_shared",
        }
        assert mock_listener._default_configuration == expected_baseline

        # Verify merge
        expected_working = {
            "default_key": "default_value",  # Preserved
            "shared_key": "loaded_shared",  # Updated
            "loaded_key": "loaded_value",  # Added
        }
        assert mock_listener._configuration == expected_working

    def test_save_configuration_empty(self, mock_listener, temp_config_file):
        """Test saving empty configuration."""
        # Remove the temp file first since we want to test the case where no file exists
        if os.path.exists(temp_config_file):
            os.unlink(temp_config_file)

        mock_listener._configuration = {}

        # Should skip saving
        mock_listener._EventListener__save_configuration()

        # File should not be created when config is empty
        assert not os.path.exists(temp_config_file)

    def test_custom_deserialize_configuration(self, mock_listener, temp_config_file):
        """Test loading with custom deserialization method."""

        # Add custom deserialize method
        def custom_deserialize(config_data):
            mock_listener._configuration.update(config_data)
            mock_listener._configuration["custom_processed"] = True

        mock_listener._deserialize_configuration = custom_deserialize

        # Write test config
        config_data = {"test_key": "test_value"}
        with open(temp_config_file, "w") as f:
            json.dump(config_data, f)

        # Load configuration
        mock_listener._EventListener__load_configuration()

        # Verify custom method was called
        assert mock_listener._configuration["test_key"] == "test_value"
        assert mock_listener._configuration["custom_processed"] is True
