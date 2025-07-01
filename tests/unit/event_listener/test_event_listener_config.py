# File: tests/unit/test_event_listener_config.py
import json
import os
import tempfile
from unittest.mock import patch

import pytest

from avena_commons.event_listener.event_listener import EventListener


class TestEventListenerConfiguration:
    """Test suite for EventListener configuration management."""

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

    def test_merge_configuration_basic(self, mock_listener):
        """Test basic configuration merging."""
        # Setup default configuration
        mock_listener._default_configuration = {
            "key1": "default_value1",
            "key2": "default_value2",
        }

        # Mock loaded config data
        config_data = {"key1": "loaded_value1", "key3": "loaded_value3"}

        # Merge configuration
        mock_listener._merge_configuration(config_data)

        # Assert results
        expected = {
            "key1": "loaded_value1",  # Updated from loaded data
            "key2": "default_value2",  # Preserved from default
            "key3": "loaded_value3",  # Added from loaded data
        }
        assert mock_listener._default_configuration == expected

    def test_merge_configuration_nested_dicts(self, mock_listener):
        """Test merging with nested dictionaries."""
        # Setup default configuration
        mock_listener._default_configuration = {
            "database": {"host": "localhost", "port": 5432, "name": "default_db"},
            "logging": {"level": "INFO"},
        }

        # Mock loaded config data
        config_data = {
            "database": {"host": "remote_host", "timeout": 30},
            "cache": {"enabled": True},
        }

        # Merge configuration
        mock_listener._merge_configuration(config_data)

        # Assert results
        expected = {
            "database": {
                "host": "remote_host",  # Updated
                "port": 5432,  # Preserved
                "name": "default_db",  # Preserved
                "timeout": 30,  # Added
            },
            "logging": {
                "level": "INFO"  # Preserved
            },
            "cache": {
                "enabled": True  # Added
            },
        }
        assert mock_listener._default_configuration == expected

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

    def test_merge_config_for_save(self, mock_listener):
        """Test merging configuration for saving to file."""
        existing_config = {
            "manual_setting": "user_edited",
            "shared_setting": "old_value",
            "nested": {"manual_nested": "user_value", "shared_nested": "old_nested"},
        }

        current_config = {
            "shared_setting": "new_value",
            "app_setting": "app_value",
            "nested": {"shared_nested": "new_nested", "app_nested": "app_nested_value"},
        }

        result = mock_listener._merge_config_for_save(existing_config, current_config)

        expected = {
            "manual_setting": "user_edited",  # Preserved from existing
            "shared_setting": "new_value",  # Updated from current
            "app_setting": "app_value",  # Added from current
            "nested": {
                "manual_nested": "user_value",  # Preserved from existing
                "shared_nested": "new_nested",  # Updated from current
                "app_nested": "app_nested_value",  # Added from current
            },
        }
        assert result == expected

    def test_has_config_changes_identical(self, mock_listener):
        """Test change detection with identical configurations."""
        config1 = {"key1": "value1", "key2": {"nested": "value"}}
        config2 = {"key1": "value1", "key2": {"nested": "value"}}

        assert not mock_listener._has_config_changes(config1, config2)

    def test_has_config_changes_different(self, mock_listener):
        """Test change detection with different configurations."""
        config1 = {"key1": "value1", "key2": {"nested": "value"}}
        config2 = {"key1": "value1", "key2": {"nested": "different"}}

        assert mock_listener._has_config_changes(config1, config2)

    def test_has_config_changes_serialization_error(self, mock_listener):
        """Test change detection when serialization fails."""
        with patch.object(
            mock_listener,
            "_serialize_value",
            side_effect=Exception("Serialization error"),
        ):
            config1 = {"key": "value"}
            config2 = {"key": "value"}

            # Should return True when comparison fails
            assert mock_listener._has_config_changes(config1, config2)

    def test_load_configuration_file_not_exists(self, mock_listener, temp_config_file):
        """Test loading configuration when file doesn't exist."""
        # Remove the temp file to simulate non-existence
        os.unlink(temp_config_file)

        mock_listener._default_configuration = {"default": "value"}
        mock_listener._EventListener__load_configuration()

        # Should remain unchanged
        assert mock_listener._default_configuration == {"default": "value"}

    def test_load_configuration_success(self, mock_listener, temp_config_file):
        """Test successful configuration loading."""
        # Setup default configuration
        mock_listener._default_configuration = {
            "default_key": "default_value",
            "shared_key": "default_shared",
        }

        # Write test config to file
        config_data = {"shared_key": "loaded_shared", "loaded_key": "loaded_value"}
        with open(temp_config_file, "w") as f:
            json.dump(config_data, f)

        # Load configuration
        mock_listener._EventListener__load_configuration()

        # Verify merge
        expected = {
            "default_key": "default_value",  # Preserved
            "shared_key": "loaded_shared",  # Updated
            "loaded_key": "loaded_value",  # Added
        }
        assert mock_listener._default_configuration == expected

    def test_save_configuration_no_changes(self, mock_listener, temp_config_file):
        """Test saving configuration when no changes exist."""
        # Setup configuration
        config = {"key": "value"}
        mock_listener._default_configuration = config

        # Write same config to file
        with open(temp_config_file, "w") as f:
            json.dump(config, f)

        # Mock the change detection to return False
        with patch.object(mock_listener, "_has_config_changes", return_value=False):
            mock_listener._EventListener__save_configuration()

        # File should remain unchanged (same content)
        with open(temp_config_file, "r") as f:
            file_content = json.load(f)
        assert file_content == config

    def test_save_configuration_with_changes(self, mock_listener, temp_config_file):
        """Test saving configuration when changes exist."""
        # Setup existing file content
        existing_config = {"manual_edit": "user_value", "shared_key": "old_value"}
        with open(temp_config_file, "w") as f:
            json.dump(existing_config, f)

        # Setup current configuration
        mock_listener._default_configuration = {
            "shared_key": "new_value",
            "app_key": "app_value",
        }

        # Save configuration
        mock_listener._EventListener__save_configuration()

        # Verify merged result was saved
        with open(temp_config_file, "r") as f:
            saved_config = json.load(f)

        expected = {
            "manual_edit": "user_value",  # Preserved from existing
            "shared_key": "new_value",  # Updated from current
            "app_key": "app_value",  # Added from current
        }
        assert saved_config == expected

    def test_save_configuration_empty(self, mock_listener, temp_config_file):
        """Test saving empty configuration."""
        # Remove the temp file first since we want to test the case where no file exists
        if os.path.exists(temp_config_file):
            os.unlink(temp_config_file)

        mock_listener._default_configuration = {}

        # Should skip saving
        mock_listener._EventListener__save_configuration()

        # File should not be created when config is empty
        assert not os.path.exists(temp_config_file)

    def test_save_configuration_empty_with_existing_file(
        self, mock_listener, temp_config_file
    ):
        """Test saving empty configuration when file already exists."""
        # Write some initial content to the file
        initial_content = {"existing": "data"}
        with open(temp_config_file, "w") as f:
            json.dump(initial_content, f)

        # Record the modification time
        initial_mtime = os.path.getmtime(temp_config_file)

        # Set empty configuration
        mock_listener._default_configuration = {}

        # Should skip saving
        mock_listener._EventListener__save_configuration()

        # File should still exist but remain unchanged
        assert os.path.exists(temp_config_file)
        final_mtime = os.path.getmtime(temp_config_file)

        # File should not have been modified
        assert final_mtime == initial_mtime

        # Content should remain the same
        with open(temp_config_file, "r") as f:
            content = json.load(f)
        assert content == initial_content

    def test_custom_deserialize_configuration(self, mock_listener, temp_config_file):
        """Test loading with custom deserialization method."""

        # Add custom deserialize method
        def custom_deserialize(config_data):
            mock_listener._default_configuration.update(config_data)
            mock_listener._default_configuration["custom_processed"] = True

        mock_listener._deserialize_configuration = custom_deserialize

        # Write test config
        config_data = {"test_key": "test_value"}
        with open(temp_config_file, "w") as f:
            json.dump(config_data, f)

        # Load configuration
        mock_listener._EventListener__load_configuration()

        # Verify custom method was called
        assert mock_listener._default_configuration["test_key"] == "test_value"
        assert mock_listener._default_configuration["custom_processed"] is True
