"""Simple test to check if imports work."""


def test_can_import_io_signal():
    """Test that we can import IoSignal."""
    from avena_commons.event_listener.types.io import IoSignal

    assert IoSignal is not None


def test_io_signal_basic():
    """Test basic IoSignal creation."""
    from avena_commons.event_listener.types.io import IoSignal

    signal = IoSignal(
        device_type="tor_pieca", device_id=1, signal_name="in", signal_value=True
    )

    assert signal.device_type == "tor_pieca"
    assert signal.device_id == 1
    assert signal.signal_name == "in"
    assert signal.signal_value == True


if __name__ == "__main__":
    # Add path for direct execution
    import sys
    from pathlib import Path

    src_path = Path(__file__).parent.parent.parent.parent / "src"
    sys.path.insert(0, str(src_path))

    test_can_import_io_signal()
    test_io_signal_basic()
    print("All tests passed!")
