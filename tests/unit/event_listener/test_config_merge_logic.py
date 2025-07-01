# File: tests/unit/test_config_merge_logic.py


class TestConfigurationMergeLogic:
    """Test suite for configuration merging logic in isolation."""

    def merge_config_for_save(
        self, existing_config: dict, current_config: dict
    ) -> dict:
        """
        Implementation of merge config for save method for testing.

        This is the actual logic from EventListener._merge_config_for_save
        """
        result = existing_config.copy()

        # Update with current configuration values
        for key, value in current_config.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # Recursively merge nested dictionaries
                result[key] = self.merge_config_for_save(result[key], value)
            else:
                # Direct assignment - current config takes precedence
                result[key] = value

        return result

    def merge_dict_recursive(self, default_dict: dict, config_dict: dict) -> dict:
        """
        Implementation of recursive dict merge for testing.

        This is the actual logic from EventListener._merge_dict_recursive
        """
        result = default_dict.copy()

        for key, value in config_dict.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                # Recursively merge nested dictionaries
                result[key] = self.merge_dict_recursive(result[key], value)
            else:
                # Direct assignment for non-dict values or new keys
                result[key] = value

        return result

    def serialize_value(self, value):
        """
        Implementation of serialize value for testing.

        This is the actual logic from EventListener._serialize_value
        """
        if isinstance(value, dict):
            return {k: self.serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.serialize_value(item) for item in value]
        return value

    def has_config_changes(self, old_config: dict, new_config: dict) -> bool:
        """
        Implementation of has config changes for testing.

        This is the actual logic from EventListener._has_config_changes
        """
        try:
            old_serialized = self.serialize_value(old_config)
            new_serialized = self.serialize_value(new_config)

            return old_serialized != new_serialized
        except Exception:
            return True  # If comparison fails, assume there are changes to be safe

    def test_merge_config_for_save_basic(self):
        """Test basic configuration merging for save operation."""
        existing_config = {
            "manual_setting": "user_value",
            "shared_setting": "old_value",
            "existing_only": "preserved",
        }

        current_config = {"shared_setting": "new_value", "app_setting": "app_value"}

        result = self.merge_config_for_save(existing_config, current_config)

        expected = {
            "manual_setting": "user_value",  # Preserved from existing
            "shared_setting": "new_value",  # Updated from current
            "existing_only": "preserved",  # Preserved from existing
            "app_setting": "app_value",  # Added from current
        }

        assert result == expected

    def test_merge_config_for_save_nested(self):
        """Test nested dictionary merging for save operation."""
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

        result = self.merge_config_for_save(existing_config, current_config)

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

    def test_merge_dict_recursive_basic(self):
        """Test basic recursive dictionary merging."""
        default_dict = {"a": 1, "b": {"c": 2, "d": 3}}

        config_dict = {"b": {"c": 20, "e": 4}, "f": 5}

        result = self.merge_dict_recursive(default_dict, config_dict)

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

    def test_merge_dict_recursive_deep_nesting(self):
        """Test recursive merging with deep nesting."""
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

        result = self.merge_dict_recursive(default_dict, config_dict)

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

    def test_has_config_changes_identical(self):
        """Test change detection with identical configurations."""
        config1 = {"key1": "value1", "nested": {"key2": "value2", "key3": 123}}

        config2 = {"key1": "value1", "nested": {"key2": "value2", "key3": 123}}

        assert not self.has_config_changes(config1, config2)

    def test_has_config_changes_different(self):
        """Test change detection with different configurations."""
        config1 = {"key1": "value1", "nested": {"key2": "value2"}}

        config2 = {"key1": "value1", "nested": {"key2": "different_value"}}

        assert self.has_config_changes(config1, config2)

    def test_serialize_value_basic_types(self):
        """Test serialization of basic types."""
        assert self.serialize_value("string") == "string"
        assert self.serialize_value(123) == 123
        assert self.serialize_value(True) == True
        assert self.serialize_value(None) == None

    def test_serialize_value_dict(self):
        """Test serialization of dictionaries."""
        input_dict = {"key1": "value1", "key2": {"nested": "value"}}
        expected_dict = {"key1": "value1", "key2": {"nested": "value"}}
        assert self.serialize_value(input_dict) == expected_dict

    def test_serialize_value_list(self):
        """Test serialization of lists."""
        input_list = ["item1", {"nested": "value"}, 123]
        expected_list = ["item1", {"nested": "value"}, 123]
        assert self.serialize_value(input_list) == expected_list

    def test_edge_cases_empty_configs(self):
        """Test edge cases with empty configurations."""
        # Empty existing, non-empty current
        result1 = self.merge_config_for_save({}, {"key": "value"})
        assert result1 == {"key": "value"}

        # Non-empty existing, empty current
        result2 = self.merge_config_for_save({"key": "value"}, {})
        assert result2 == {"key": "value"}

        # Both empty
        result3 = self.merge_config_for_save({}, {})
        assert result3 == {}

    def test_type_replacement_in_merge(self):
        """Test that different types replace each other correctly."""
        existing = {"setting": {"nested": "value"}}
        current = {"setting": "string_value"}  # Different type

        result = self.merge_config_for_save(existing, current)
        expected = {"setting": "string_value"}  # Should replace with new type
        assert result == expected

    def test_list_replacement_in_merge(self):
        """Test that lists are replaced entirely, not merged."""
        existing = {"list_setting": [1, 2, 3]}
        current = {"list_setting": [4, 5, 6]}

        result = self.merge_config_for_save(existing, current)
        expected = {"list_setting": [4, 5, 6]}  # Should replace entirely
        assert result == expected

    def test_immutability_of_original_dicts(self):
        """Test that original dictionaries are not modified during merge."""
        original_existing = {"key1": "value1", "nested": {"key2": "value2"}}

        original_current = {"key1": "new_value1", "nested": {"key3": "value3"}}

        # Create copies to check immutability
        existing_copy = {"key1": "value1", "nested": {"key2": "value2"}}
        current_copy = {"key1": "new_value1", "nested": {"key3": "value3"}}

        result = self.merge_config_for_save(original_existing, original_current)

        # Verify original dictionaries weren't modified
        assert original_existing == existing_copy
        assert original_current == current_copy

        # Verify result is correct
        expected = {
            "key1": "new_value1",
            "nested": {"key2": "value2", "key3": "value3"},
        }
        assert result == expected

    def test_complex_nested_structure(self):
        """Test with a complex, realistic configuration structure."""
        existing_config = {
            "database": {
                "host": "manual-db.example.com",
                "port": 5432,
                "ssl": {"enabled": True, "cert_path": "/manual/path/cert.pem"},
                "manual_pools": {"read": 5, "write": 2},
            },
            "manual_features": {"feature_x": True, "feature_y": False},
        }

        current_config = {
            "database": {
                "port": 3306,  # App changed this
                "timeout": 30,  # App added this
                "ssl": {
                    "enabled": False,  # App changed this
                    "verify_mode": "strict",  # App added this
                },
                "app_pools": {"connection": 10},
            },
            "app_settings": {"version": "1.2.3", "debug": False},
        }

        result = self.merge_config_for_save(existing_config, current_config)

        expected = {
            "database": {
                "host": "manual-db.example.com",  # Preserved from manual
                "port": 3306,  # Updated by app
                "timeout": 30,  # Added by app
                "ssl": {
                    "enabled": False,  # Updated by app
                    "cert_path": "/manual/path/cert.pem",  # Preserved from manual
                    "verify_mode": "strict",  # Added by app
                },
                "manual_pools": {  # Preserved from manual
                    "read": 5,
                    "write": 2,
                },
                "app_pools": {  # Added by app
                    "connection": 10
                },
            },
            "manual_features": {  # Preserved from manual
                "feature_x": True,
                "feature_y": False,
            },
            "app_settings": {  # Added by app
                "version": "1.2.3",
                "debug": False,
            },
        }

        assert result == expected
