"""Test Python path setup."""


def test_python_path():
    """Test that sys.path includes the src directory."""
    import sys

    print("Python path:", sys.path)

    # Check if src directory is in path
    src_in_path = any("src" in path for path in sys.path)
    print("Src in path:", src_in_path)

    assert src_in_path


def test_can_import_avena_commons():
    """Test that we can import the base avena_commons module."""
    try:
        import avena_commons

        print("Successfully imported avena_commons")
        assert True
    except ImportError as e:
        print(f"Failed to import avena_commons: {e}")
        assert False


def test_can_import_event_listener():
    """Test that we can import the event_listener module."""
    try:
        import avena_commons.event_listener

        print("Successfully imported avena_commons.event_listener")
        assert True
    except ImportError as e:
        print(f"Failed to import event_listener: {e}")
        assert False
