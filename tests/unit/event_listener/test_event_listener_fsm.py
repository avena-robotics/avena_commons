# import asyncio
from unittest.mock import AsyncMock

import pytest

from avena_commons.event_listener.event import Event
from avena_commons.event_listener.event_listener import (
    EventListener,
    EventListenerState,
)

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture
def event_listener(mocker):
    """Fixture to create a mocked EventListener instance."""
    # Mock the __init__ method to prevent it from running its own threads
    mocker.patch.object(EventListener, "__init__", lambda s, *args, **kwargs: None)

    listener = EventListener(name="test_listener")

    # Manually set attributes that would be set in __init__
    listener._EventListener__fsm_state = EventListenerState.READY
    listener._message_logger = None  # Mock or disable logger if needed

    # Mock the methods that send events
    mocker.patch.object(listener, "_event", new_callable=AsyncMock)

    return listener


class TestEventListenerFSM:
    """Tests for the Finite State Machine logic in EventListener."""

    async def test_handle_initialize_happy_path(self, event_listener, mocker):
        """
        Tests successful initialization flow:
        READY -> INITIALIZING -> INIT_COMPLETE
        """
        # Arrange
        event_listener._on_initialize = AsyncMock()
        event = Event(event_type="CMD_INITIALIZE")

        # Act
        await event_listener._handle_initialize_command(event)

        # Assert
        # Check if the lifecycle hook was called
        event_listener._on_initialize.assert_awaited_once()

        # Check the final state
        assert (
            event_listener._EventListener__fsm_state == EventListenerState.INIT_COMPLETE
        )

        # TODO: Check if EVENT_INIT_SUCCESS was sent

    async def test_handle_initialize_failure_path(self, event_listener, mocker):
        """
        Tests failed initialization flow:
        READY -> INITIALIZING -> FAULT
        """
        # Arrange
        mocker.patch.object(
            event_listener,
            "_on_initialize",
            new_callable=AsyncMock,
            side_effect=Exception("Hardware Failure"),
        )
        mocker.patch(
            "avena_commons.event_listener.event_listener.error"
        )  # Mock the logger
        event = Event(event_type="CMD_INITIALIZE")

        # Act
        await event_listener._handle_initialize_command(event)

        # Assert
        # Check if the lifecycle hook was called
        event_listener._on_initialize.assert_awaited_once()

        # Check the final state
        assert event_listener._EventListener__fsm_state == EventListenerState.FAULT

        # Check if error was logged
        # error.assert_called_with("Initialization failed: Hardware Failure", message_logger=None)

        # TODO: Check if EVENT_INIT_FAILURE was sent

    async def test_handle_initialize_wrong_state(self, event_listener, mocker):
        """

        Tests calling CMD_INITIALIZE when the listener is in an incorrect state (e.g., STARTED).
        """
        # Arrange
        event_listener._EventListener__fsm_state = EventListenerState.STARTED
        event_listener._on_initialize = AsyncMock()
        mocker.patch(
            "avena_commons.event_listener.event_listener.warning"
        )  # Mock the logger
        event = Event(event_type="CMD_INITIALIZE")

        # Act
        await event_listener._handle_initialize_command(event)

        # Assert
        # Check that the lifecycle hook was NOT called
        event_listener._on_initialize.assert_not_awaited()

        # Check that the state has NOT changed
        assert event_listener._EventListener__fsm_state == EventListenerState.STARTED

        # Check if warning was logged
        # warning.assert_called_with("Received CMD_INITIALIZE in unexpected state: STARTED", message_logger=None)
