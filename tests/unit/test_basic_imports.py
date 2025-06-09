"""Test basic avena_commons import in pytest."""


def test_basic_import():
    """Test that we can import avena_commons."""
    import avena_commons

    assert avena_commons is not None


def test_event_listener_import():
    """Test that we can import event_listener."""
    import avena_commons.event_listener

    assert avena_commons.event_listener is not None
