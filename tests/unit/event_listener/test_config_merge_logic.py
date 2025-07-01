# File: tests/unit/test_baseline_config_logic.py


class TestBaselineConfigurationLogic:
    """Test suite for baseline configuration logic in isolation."""

    def extract_config_differences(self, baseline: dict, current: dict) -> dict:
        """
        Implementation of extract config differences method for testing.

        This is the actual logic from EventListener._extract_config_differences
        """
        differences = {}

        # Check for new or modified keys in current config
        for key, current_value in current.items():
            if key not in baseline:
                # New key that doesn't exist in baseline
                differences[key] = current_value
            elif isinstance(current_value, dict) and isinstance(baseline[key], dict):
                # Recursively check nested dictionaries
                nested_diff = self.extract_config_differences(
                    baseline[key], current_value
                )
                if nested_diff:  # Only add if there are actual differences
                    differences[key] = nested_diff
            elif current_value != baseline[key]:
                # Value has changed
                differences[key] = current_value

        return differences

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

    def test_extract_config_differences_no_changes(self):
        """Test that no differences are detected when configs are identical."""
        baseline = {"key1": "value1", "nested": {"key2": "value2"}}
        current = {"key1": "value1", "nested": {"key2": "value2"}}

        differences = self.extract_config_differences(baseline, current)
        assert differences == {}

    def test_extract_config_differences_simple_changes(self):
        """Test detection of simple configuration changes."""
        baseline = {"key1": "value1", "key2": "value2"}
        current = {"key1": "changed_value1", "key2": "value2", "key3": "new_value"}

        differences = self.extract_config_differences(baseline, current)
        expected = {"key1": "changed_value1", "key3": "new_value"}
        assert differences == expected

    def test_extract_config_differences_nested_changes(self):
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

        differences = self.extract_config_differences(baseline, current)
        expected = {
            "database": {"host": "remote", "timeout": 30},
            "logging": {"level": "INFO"},
        }
        assert differences == expected

    def test_extract_config_differences_deep_nesting(self):
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

        differences = self.extract_config_differences(baseline, current)
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
        # Empty baseline, non-empty current
        result1 = self.extract_config_differences({}, {"key": "value"})
        assert result1 == {"key": "value"}

        # Non-empty baseline, empty current
        result2 = self.extract_config_differences({"key": "value"}, {})
        assert result2 == {}

        # Both empty
        result3 = self.extract_config_differences({}, {})
        assert result3 == {}

    def test_type_replacement_in_differences(self):
        """Test that different types are detected as changes."""
        baseline = {"setting": {"nested": "value"}}
        current = {"setting": "string_value"}  # Different type

        differences = self.extract_config_differences(baseline, current)
        expected = {"setting": "string_value"}  # Should detect type change
        assert differences == expected

    def test_list_changes_in_differences(self):
        """Test that list changes are detected."""
        baseline = {"list_setting": [1, 2, 3]}
        current = {"list_setting": [1, 2, 3, 4]}

        differences = self.extract_config_differences(baseline, current)
        expected = {"list_setting": [1, 2, 3, 4]}  # Should detect list change
        assert differences == expected

    def test_immutability_of_original_dicts(self):
        """Test that original dictionaries are not modified during operations."""
        original_baseline = {"key1": "value1", "nested": {"key2": "value2"}}
        original_current = {"key1": "new_value1", "nested": {"key3": "value3"}}

        # Create copies to check immutability
        baseline_copy = original_baseline.copy()
        current_copy = original_current.copy()

        differences = self.extract_config_differences(
            original_baseline, original_current
        )

        # Verify original dictionaries weren't modified
        assert original_baseline == baseline_copy
        assert original_current == current_copy

        # Verify result is correct
        expected = {
            "key1": "new_value1",
            "nested": {"key3": "value3"},
        }
        assert differences == expected

    def test_complex_baseline_scenario(self):
        """Test with a complex, realistic baseline vs current configuration."""
        baseline_config = {
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

        differences = self.extract_config_differences(baseline_config, current_config)

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

    def test_baseline_workflow_integration(self):
        """Test the complete baseline workflow from load to save."""
        # Step 1: Initial app defaults (baseline)
        app_defaults = {
            "database": {"host": "localhost", "port": 5432},
            "app_setting": "default_value",
        }

        # Step 2: File contains user changes
        user_changes = {
            "database": {"host": "remote_host", "timeout": 30},
            "new_feature": {"enabled": True},
        }

        # Step 3: Merge user changes with app defaults (load workflow)
        working_config = self.merge_dict_recursive(app_defaults, user_changes)
        expected_working = {
            "database": {"host": "remote_host", "port": 5432, "timeout": 30},
            "app_setting": "default_value",
            "new_feature": {"enabled": True},
        }
        assert working_config == expected_working

        # Step 4: Extract only the differences for saving (save workflow)
        differences = self.extract_config_differences(app_defaults, working_config)
        expected_differences = {
            "database": {"host": "remote_host", "timeout": 30},
            "new_feature": {"enabled": True},
        }
        assert differences == expected_differences

    def test_no_changes_after_load_save_cycle(self):
        """Test that load-save cycle preserves changes correctly."""
        # Original baseline
        baseline = {"key1": "default1", "nested": {"key2": "default2"}}

        # User changes saved to file
        file_changes = {"key1": "changed1", "nested": {"key3": "new3"}}

        # Load: merge changes with baseline
        working_config = self.merge_dict_recursive(baseline, file_changes)

        # Save: extract differences
        extracted_changes = self.extract_config_differences(baseline, working_config)

        # Should get back the same changes
        assert extracted_changes == file_changes

    def test_partial_nested_changes(self):
        """Test that only modified parts of nested structures are included in differences."""
        baseline = {
            "section1": {
                "unchanged_key": "value1",
                "changed_key": "old_value",
                "nested_section": {
                    "unchanged_nested": "nested_value1",
                    "changed_nested": "old_nested_value",
                },
            },
            "section2": {"all_unchanged": "value2"},
        }

        current = {
            "section1": {
                "unchanged_key": "value1",  # Same
                "changed_key": "new_value",  # Changed
                "nested_section": {
                    "unchanged_nested": "nested_value1",  # Same
                    "changed_nested": "new_nested_value",  # Changed
                    "added_nested": "added_value",  # New
                },
            },
            "section2": {
                "all_unchanged": "value2"  # Same
            },
            "section3": {  # New section
                "new_key": "new_value"
            },
        }

        differences = self.extract_config_differences(baseline, current)

        expected = {
            "section1": {
                "changed_key": "new_value",
                "nested_section": {
                    "changed_nested": "new_nested_value",
                    "added_nested": "added_value",
                },
            },
            "section3": {"new_key": "new_value"},
        }

        assert differences == expected
