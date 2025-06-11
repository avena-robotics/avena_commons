"""
Unit tests for the Config class from avena_commons.config.common.

This module tests the configuration file management functionality including:
- Config class initialization
- File path handling
- Content manipulation methods
- Error handling scenarios

All tests follow the avena_commons testing guidelines with proper
fixtures, comprehensive coverage, and clear test organization.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest

from avena_commons.config.common import Config


class TestConfig:
    """Test cases for the Config class."""

    @pytest.fixture
    def temp_config_file(self):
        """Fixture providing a temporary config file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write(
                "[DEFAULT]\ntest_key = test_value\n\n[SECTION1]\nkey1 = value1\n"
            )
            temp_file_path = temp_file.name

        yield temp_file_path

        # Cleanup
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

    @pytest.fixture
    def config_with_content(self):
        """Fixture providing a config file with test content."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ini", delete=False
        ) as temp_file:
            temp_file.write("\n\n[CONTROLLER]\nkey1 = value1\nkey2 = value2\n")
            temp_file_path = temp_file.name

        yield temp_file_path

        # Cleanup
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

    def test_config_initialization_read_only(self, temp_config_file):
        """Test Config initialization in read-only mode."""
        config = Config(temp_config_file, read_only=True)

        assert config._read_only is True
        assert config._config_file_base == os.path.splitext(temp_config_file)[0]
        assert config._config_file_extenstion == os.path.splitext(temp_config_file)[1]

    def test_config_initialization_writable(self, temp_config_file):
        """Test Config initialization in writable mode."""
        config = Config(temp_config_file, read_only=False)

        assert config._read_only is False
        assert config._config_file_base == os.path.splitext(temp_config_file)[0]
        assert config._config_file_extenstion == os.path.splitext(temp_config_file)[1]

    def test_config_initialization_default_read_only(self, temp_config_file):
        """Test Config initialization with default read_only parameter."""
        config = Config(temp_config_file)

        assert config._read_only is True

    def test_config_file_method(self, temp_config_file):
        """Test config_file method returns correct path."""
        config = Config(temp_config_file)

        assert config.config_file() == temp_config_file

    def test_config_file_method_with_different_extensions(self):
        """Test config_file method with different file extensions."""
        test_cases = [
            "/path/to/config.ini",
            "/path/to/config.conf",
            "/path/to/config.cfg",
            "/path/to/config",  # No extension
        ]

        for config_path in test_cases:
            config = Config(config_path)
            assert config.config_file() == config_path

    def test_read_from_file_method(self, temp_config_file):
        """Test read_from_file method."""
        # We need to create a config with an actual config attribute for this test
        config = Config(temp_config_file)

        # Mock the config attribute since it's not created in the base class
        with patch.object(config, "config") as mock_config:
            result = config.read_from_file()

            mock_config.read.assert_called_once_with(temp_config_file)
            assert result is config  # Should return self

    def test_save_to_file_read_only_mode(self, temp_config_file):
        """Test save_to_file method in read-only mode does nothing."""
        config = Config(temp_config_file, read_only=True)

        # Mock the config attribute and methods
        with patch.object(config, "config") as mock_config:
            config.save_to_file()

            # Should not call write in read-only mode
            mock_config.write.assert_not_called()

    def test_save_to_file_writable_mode(self, temp_config_file):
        """Test save_to_file method in writable mode."""
        config = Config(temp_config_file, read_only=False)

        # Mock the config attribute and private method
        with (
            patch.object(config, "config") as mock_config,
            patch.object(
                config, "_Config__remove_content_up_to_first_blank_line"
            ) as mock_remove,
        ):
            # Mock the open function
            with patch("builtins.open", create=True) as mock_open:
                config.save_to_file()

                # Verify file was opened for writing
                mock_open.assert_called_once_with(temp_config_file, "w")

                # Verify config.write was called
                mock_config.write.assert_called_once()

                # Verify cleanup method was called
                mock_remove.assert_called_once()

    def test_remove_content_up_to_first_blank_line_with_blank_line(
        self, config_with_content
    ):
        """Test __remove_content_up_to_first_blank_line method when blank line exists."""
        config = Config(config_with_content, read_only=False)

        # Call the private method directly
        config._Config__remove_content_up_to_first_blank_line()

        # Read the file content to verify blank lines were removed
        with open(config_with_content, "r") as f:
            content = f.read()

        # Should not start with blank lines anymore
        assert not content.startswith("\n")
        assert "[CONTROLLER]" in content

    def test_remove_content_up_to_first_blank_line_no_blank_line(
        self, temp_config_file
    ):
        """Test __remove_content_up_to_first_blank_line method when no blank line exists."""
        config = Config(temp_config_file, read_only=False)

        # Read original content
        with open(temp_config_file, "r") as f:
            original_content = f.read()

        # Call the private method
        config._Config__remove_content_up_to_first_blank_line()

        # Read content after method call
        with open(temp_config_file, "r") as f:
            new_content = f.read()

        # Content should remain unchanged
        assert original_content == new_content

    def test_dump_all_read_only_mode(self, temp_config_file):
        """Test _dump_all method in read-only mode."""
        config = Config(temp_config_file, read_only=True)

        with patch.object(config, "save_to_file") as mock_save:
            config._dump_all()

            # Should not call save_to_file in read-only mode
            mock_save.assert_not_called()

    def test_dump_all_writable_mode_success(self, temp_config_file):
        """Test _dump_all method in writable mode with successful save."""
        config = Config(temp_config_file, read_only=False)

        with (
            patch.object(config, "save_to_file") as mock_save,
            patch("builtins.print") as mock_print,
        ):
            config._dump_all()

            mock_save.assert_called_once()
            mock_print.assert_called_once()

            # Verify success message
            call_args = mock_print.call_args[0][0]
            assert "Configuration saved" in call_args
            assert config._config_file_base in call_args

    def test_dump_all_writable_mode_exception(self, temp_config_file):
        """Test _dump_all method in writable mode with exception."""
        config = Config(temp_config_file, read_only=False)

        with (
            patch.object(
                config, "save_to_file", side_effect=Exception("Test error")
            ) as mock_save,
            patch("builtins.print") as mock_print,
            patch("traceback.print_exception") as mock_traceback,
        ):
            config._dump_all()

            mock_save.assert_called_once()

            # Verify error message was printed
            assert mock_print.call_count == 1
            call_args = mock_print.call_args[0][0]
            assert "Failed to save configuration" in call_args
            assert "Test error" in call_args

            # Verify traceback was printed
            mock_traceback.assert_called_once()

    def test_str_method(self, temp_config_file):
        """Test __str__ method."""
        config = Config(temp_config_file)

        # Mock the config attribute with sections
        mock_section = Mock()
        mock_section.__iter__ = Mock(return_value=iter(["key1", "key2"]))
        mock_section.__getitem__ = Mock(side_effect=lambda k: f"value_{k}")

        mock_config = Mock()
        mock_config.sections.return_value = ["SECTION1", "SECTION2"]
        mock_config.__getitem__ = Mock(return_value=mock_section)

        config.config = mock_config

        result = str(config)

        assert "[SECTION1]" in result
        assert "[SECTION2]" in result
        assert "key1 = value_key1" in result
        assert "key2 = value_key2" in result

    def test_str_method_empty_config(self, temp_config_file):
        """Test __str__ method with empty config."""
        config = Config(temp_config_file)

        # Mock empty config
        mock_config = Mock()
        mock_config.sections.return_value = []
        config.config = mock_config

        result = str(config)

        assert result == ""

    def test_del_method_calls_dump_all(self, temp_config_file):
        """Test __del__ method calls _dump_all."""
        config = Config(temp_config_file, read_only=False)

        with patch.object(config, "_dump_all") as mock_dump:
            config.__del__()

            mock_dump.assert_called_once()

    def test_config_with_various_file_extensions(self):
        """Test Config class with various file extensions."""
        extensions = [".ini", ".conf", ".cfg", ".config", ""]

        for ext in extensions:
            config_path = f"/test/config{ext}"
            config = Config(config_path)

            base_name = "/test/config"
            assert config._config_file_base == base_name
            assert config._config_file_extenstion == ext
            assert config.config_file() == config_path

    def test_config_path_edge_cases(self):
        """Test Config class with edge case file paths."""
        edge_cases = [
            "/path/with.dots.in.name.conf",
            "config.ini",
            "./relative/path/config.conf",
            "/absolute/path/config",
            "config",
        ]

        for config_path in edge_cases:
            config = Config(config_path)
            expected_base, expected_ext = os.path.splitext(config_path)

            assert config._config_file_base == expected_base
            assert config._config_file_extenstion == expected_ext
            assert config.config_file() == config_path


class TestConfigIntegration:
    """Integration tests for Config class."""

    def test_config_full_workflow(self):
        """Test complete Config workflow with real file operations."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("[SECTION1]\nkey1 = value1\n")
            temp_file_path = temp_file.name

        try:
            # Test initialization and file operations
            config = Config(temp_file_path, read_only=False)

            # Verify file path parsing
            expected_base, expected_ext = os.path.splitext(temp_file_path)
            assert config._config_file_base == expected_base
            assert config._config_file_extenstion == expected_ext
            assert config.config_file() == temp_file_path

            # Test save operations don't crash
            with patch.object(config, "config") as mock_config:
                config.save_to_file()

            # Test dump_all doesn't crash
            with patch.object(config, "save_to_file"):
                config._dump_all()

        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_config_edge_case_file_operations(self):
        """Test Config with edge case file operations."""
        # Test with non-existent file
        config = Config("/non/existent/path/config.ini")

        assert config.config_file() == "/non/existent/path/config.ini"
        assert config._config_file_base == "/non/existent/path/config"
        assert config._config_file_extenstion == ".ini"

        # Test private methods don't crash with non-existent file
        with patch("builtins.open", side_effect=FileNotFoundError):
            # Should handle file not found gracefully
            try:
                config._Config__remove_content_up_to_first_blank_line()
            except FileNotFoundError:
                pass  # Expected behavior
