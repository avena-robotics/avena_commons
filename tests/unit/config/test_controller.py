"""
Unit tests for the ControllerConfig class from avena_commons.config.controller.

This module tests the controller configuration functionality including:
- ControllerConfig class initialization
- Configuration value retrieval with type conversion
- Default value handling
- Integration with the base Config class

All tests follow the avena_commons testing guidelines with proper
fixtures, comprehensive coverage, and clear test organization.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

import pytest

from avena_commons.config.controller import ControllerConfig


class TestControllerConfig:
    """Test cases for the ControllerConfig class."""

    @pytest.fixture
    def temp_controller_config_file(self):
        """Fixture providing a temporary controller config file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("""[CONTROLLER]
CONTROLLER_PATH = /test/controller
RESOURCES_PATH = /test/resources
URDF_PATH = /test/urdf/robot.urdf
LOG_LEVEL = DEBUG
APS = APS01
TEST_INT = 42
TEST_FLOAT = 3.14
TEST_STRING = hello_world
""")
            temp_file_path = temp_file.name

        yield temp_file_path

        # Cleanup
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

    @pytest.fixture
    def minimal_controller_config_file(self):
        """Fixture providing a minimal controller config file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("[CONTROLLER]\n")
            temp_file_path = temp_file.name

        yield temp_file_path

        # Cleanup
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

    def test_controller_config_initialization_read_only(
        self, temp_controller_config_file
    ):
        """Test ControllerConfig initialization in read-only mode."""
        config = ControllerConfig(temp_controller_config_file, read_only=True)

        assert config._read_only is True
        assert config._ControllerConfig__section == "CONTROLLER"
        assert config.config is not None

        # Verify that the config was read from file
        assert config.config.has_section("CONTROLLER")

    def test_controller_config_initialization_writable(
        self, temp_controller_config_file
    ):
        """Test ControllerConfig initialization in writable mode."""
        config = ControllerConfig(temp_controller_config_file, read_only=False)

        assert config._read_only is False
        assert config._ControllerConfig__section == "CONTROLLER"
        assert config.config is not None

    def test_controller_config_initialization_default_read_only(
        self, temp_controller_config_file
    ):
        """Test ControllerConfig initialization with default read_only parameter."""
        config = ControllerConfig(temp_controller_config_file)

        assert config._read_only is True

    def test_controller_config_default_values_with_minimal_file(
        self, minimal_controller_config_file
    ):
        """Test ControllerConfig with minimal config file uses defaults."""
        config = ControllerConfig(minimal_controller_config_file)

        # Test default values
        expected_controller_path = os.path.expanduser("~") + "/controller"
        assert config.get("CONTROLLER_PATH") == expected_controller_path
        assert config.get("RESOURCES_PATH") == f"{expected_controller_path}/resources"
        assert (
            config.get("URDF_PATH")
            == f"{expected_controller_path}/URDFS/urdf_janusz/robot.urdf"
        )
        assert config.get("LOG_LEVEL") == "INFO"
        assert config.get("APS") == "APS00"

    def test_get_method_string_values(self, temp_controller_config_file):
        """Test get method returns string values correctly."""
        config = ControllerConfig(temp_controller_config_file)

        assert config.get("CONTROLLER_PATH") == "/test/controller"
        assert config.get("LOG_LEVEL") == "DEBUG"
        assert config.get("APS") == "APS01"
        assert config.get("TEST_STRING") == "hello_world"

    def test_get_method_integer_values(self, temp_controller_config_file):
        """Test get method converts and returns integer values correctly."""
        config = ControllerConfig(temp_controller_config_file)

        result = config.get("TEST_INT")
        assert result == 42
        assert isinstance(result, int)

    def test_get_method_float_values(self, temp_controller_config_file):
        """Test get method converts and returns float values correctly."""
        config = ControllerConfig(temp_controller_config_file)

        result = config.get("TEST_FLOAT")
        assert result == 3.14
        assert isinstance(result, float)

    def test_get_method_type_conversion_priority(self, temp_controller_config_file):
        """Test get method type conversion priority (float over int)."""
        # Create a config file with a value that could be both int and float
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("[CONTROLLER]\nTEST_NUMBER = 42.0\n")
            temp_file_path = temp_file.name

        try:
            config = ControllerConfig(temp_file_path)
            result = config.get("TEST_NUMBER")

            # Should be converted to float, not int
            assert result == 42.0
            assert isinstance(result, float)

        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_get_method_non_numeric_string(self, temp_controller_config_file):
        """Test get method returns non-numeric strings as strings."""
        config = ControllerConfig(temp_controller_config_file)

        result = config.get("LOG_LEVEL")
        assert result == "DEBUG"
        assert isinstance(result, str)

    def test_get_method_empty_string(self):
        """Test get method handles empty string values."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("[CONTROLLER]\nEMPTY_VALUE = \n")
            temp_file_path = temp_file.name

        try:
            config = ControllerConfig(temp_file_path)
            result = config.get("EMPTY_VALUE")

            assert result == ""
            assert isinstance(result, str)

        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_get_method_whitespace_values(self):
        """Test get method handles whitespace values."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("[CONTROLLER]\nWHITESPACE_VALUE =    spaces   \n")
            temp_file_path = temp_file.name

        try:
            config = ControllerConfig(temp_file_path)
            result = config.get("WHITESPACE_VALUE")

            # ConfigParser should handle whitespace trimming
            assert result == "spaces"
            assert isinstance(result, str)

        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_get_method_nonexistent_key(self, temp_controller_config_file):
        """Test get method with non-existent key raises exception."""
        config = ControllerConfig(temp_controller_config_file)

        with pytest.raises(Exception):  # ConfigParser raises NoOptionError
            config.get("NONEXISTENT_KEY")

    def test_get_controller_configuration_method(self, temp_controller_config_file):
        """Test get_controller_configuration method returns all params."""
        config = ControllerConfig(temp_controller_config_file)

        params = config.get_controller_configuration()

        assert isinstance(params, dict)
        assert "CONTROLLER_PATH" in params
        assert "LOG_LEVEL" in params
        assert "APS" in params
        assert "TEST_INT" in params
        assert "TEST_FLOAT" in params
        assert "TEST_STRING" in params

        # Values should be strings (as returned by ConfigParser)
        assert params["CONTROLLER_PATH"] == "/test/controller"
        assert params["LOG_LEVEL"] == "DEBUG"
        assert params["TEST_INT"] == "42"  # Note: dict values are strings
        assert params["TEST_FLOAT"] == "3.14"

    def test_get_controller_configuration_empty_section(
        self, minimal_controller_config_file
    ):
        """Test get_controller_configuration with minimal config."""
        config = ControllerConfig(minimal_controller_config_file)

        params = config.get_controller_configuration()

        assert isinstance(params, dict)
        # Should contain default values
        assert "CONTROLLER_PATH" in params
        assert "LOG_LEVEL" in params
        assert "APS" in params

    def test_str_method_inheritance(self, temp_controller_config_file):
        """Test __str__ method uses parent class implementation."""
        config = ControllerConfig(temp_controller_config_file)

        result = str(config)

        assert "[CONTROLLER]" in result
        assert "CONTROLLER_PATH" in result
        assert "LOG_LEVEL" in result

    def test_del_method_override(self, temp_controller_config_file):
        """Test __del__ method is overridden and doesn't call parent's _dump_all."""
        config = ControllerConfig(temp_controller_config_file)

        # Mock the parent's _dump_all method to ensure it's not called
        with patch.object(config.__class__.__bases__[0], "_dump_all") as mock_dump:
            config.__del__()

            # Should not call parent's _dump_all
            mock_dump.assert_not_called()

    def test_config_file_inheritance(self, temp_controller_config_file):
        """Test that ControllerConfig inherits config_file method correctly."""
        config = ControllerConfig(temp_controller_config_file)

        assert config.config_file() == temp_controller_config_file

    def test_variable_interpolation(self):
        """Test ConfigParser variable interpolation with defaults."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("""[CONTROLLER]
CONTROLLER_PATH = /custom/controller
RESOURCES_PATH = %(CONTROLLER_PATH)s/resources
""")
            temp_file_path = temp_file.name

        try:
            config = ControllerConfig(temp_file_path)

            # Test interpolation works
            assert config.get("RESOURCES_PATH") == "/custom/controller/resources"

        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_read_from_file_inheritance(self, temp_controller_config_file):
        """Test that read_from_file method is inherited and works."""
        config = ControllerConfig(temp_controller_config_file)

        # The file should already be read during initialization
        # Verify by checking if a key exists
        assert config.get("TEST_STRING") == "hello_world"

        # Test calling read_from_file again
        result = config.read_from_file()
        assert result is config  # Should return self


class TestControllerConfigIntegration:
    """Integration tests for ControllerConfig class."""

    def test_full_workflow_with_file_operations(self):
        """Test complete ControllerConfig workflow with real file operations."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("""[CONTROLLER]
CONTROLLER_PATH = /integration/test
LOG_LEVEL = WARNING
APS = APS99
NUMERIC_VALUE = 123
FLOAT_VALUE = 456.789
""")
            temp_file_path = temp_file.name

        try:
            # Test initialization and configuration reading
            config = ControllerConfig(temp_file_path, read_only=False)

            # Test various get operations
            assert config.get("CONTROLLER_PATH") == "/integration/test"
            assert config.get("LOG_LEVEL") == "WARNING"
            assert config.get("APS") == "APS99"
            assert config.get("NUMERIC_VALUE") == 123
            assert config.get("FLOAT_VALUE") == 456.789

            # Test get_controller_configuration
            params = config.get_controller_configuration()
            assert params["CONTROLLER_PATH"] == "/integration/test"
            assert params["LOG_LEVEL"] == "WARNING"

            # Test string representation
            config_str = str(config)
            assert "[CONTROLLER]" in config_str
            assert "CONTROLLER_PATH" in config_str

        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_error_handling_with_malformed_config(self):
        """Test error handling with malformed configuration files."""
        # Test with file that has no CONTROLLER section
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("[OTHER_SECTION]\nkey = value\n")
            temp_file_path = temp_file.name

        try:
            config = ControllerConfig(temp_file_path)

            # Should use defaults when section doesn't exist in file
            expected_controller_path = os.path.expanduser("~") + "/controller"
            assert config.get("CONTROLLER_PATH") == expected_controller_path

        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)

    def test_config_with_comments_and_formatting(self):
        """Test ControllerConfig with comments and various formatting."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False
        ) as temp_file:
            temp_file.write("""# This is a comment
[CONTROLLER]
# Another comment
CONTROLLER_PATH = /test/path  # inline comment
LOG_LEVEL = INFO

# Some spacing
APS = APS42
""")
            temp_file_path = temp_file.name

        try:
            config = ControllerConfig(temp_file_path)

            # Should parse correctly despite comments and formatting
            assert config.get("CONTROLLER_PATH") == "/test/path"
            assert config.get("LOG_LEVEL") == "INFO"
            assert config.get("APS") == "APS42"

        finally:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
