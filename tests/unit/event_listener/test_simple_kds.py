"""
Simple test to debug pytest import issues.
"""

import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from avena_commons.event_listener.types.kds import KdsAction


def test_simple_import():
    """Test that we can import and create a KdsAction."""
    action = KdsAction()
    assert action.order_number is None
    assert action.pickup_number is None
    assert action.message is None


if __name__ == "__main__":
    test_simple_import()
    print("Simple test passed!")
