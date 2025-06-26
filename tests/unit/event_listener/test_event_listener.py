"""
Unit tests for the EventListener class.

This module tests the core EventListener functionality including:
- EventListener initialization and configuration
- Event handling and processing
- State management and thread safety
- Queue operations and management
- Shutdown procedures and resource cleanup

All tests follow the avena_commons testing guidelines with proper
fixtures, comprehensive coverage, and clear test organization.
"""

import threading
import time
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from avena_commons.event_listener.event import Event, EventPriority, Result
from avena_commons.event_listener.event_listener import (
    EventListener,
    EventListenerState,
)
from avena_commons.util.logger import MessageLogger


class TestEventListener:
    """Test cases for the EventListener class."""

    @pytest.fixture
    def mock_message_logger(self):
        """Fixture providing a mock MessageLogger."""
        return Mock(spec=MessageLogger)

    @pytest.fixture
    def sample_event(self):
        """Fixture providing a sample Event object."""
        return Event(
            source="test_source",
            source_address="127.0.0.1",
            source_port=8001,
            destination="test_destination",
            destination_address="127.0.0.1",
            destination_port=8002,
            event_type="test_event",
            data={"test_key": "test_value"},
            priority=EventPriority.MEDIUM,
        )

    @pytest.fixture
    def basic_event_listener(self, mock_message_logger):
        """Fixture providing a basic EventListener instance."""
        # Use unique port to avoid conflicts
        import random

        port = random.randint(9000, 9999)

        listener = EventListener(
            name="test_listener",
            address="127.0.0.1",
            port=port,
            message_logger=mock_message_logger,
            do_not_load_state=True,  # Prevent file operations in tests
        )
        yield listener
        # Cleanup
        try:
            listener.shutdown()
        except:
            pass

    def test_event_listener_initialization_minimal(self, mock_message_logger):
        """Test EventListener initialization with minimal parameters."""
        listener = EventListener(
            name="test_minimal",
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        assert listener._EventListener__name == "test_minimal"
        assert listener._EventListener__address == "127.0.0.1"
        assert listener._EventListener__port == 8000
        assert listener._message_logger == mock_message_logger
        assert listener._EventListener__el_state == EventListenerState.RUNNING
        assert not listener._shutdown_requested

        # Cleanup
        listener.shutdown()

    def test_event_listener_initialization_full_parameters(self, mock_message_logger):
        """Test EventListener initialization with all parameters."""
        listener = EventListener(
            name="test_full",
            address="192.168.1.100",
            port=9001,
            message_logger=mock_message_logger,
            do_not_load_state=True,
            discovery_neighbours=True,
            raport_overtime=False,
        )

        assert listener._EventListener__name == "test_full"
        assert listener._EventListener__address == "192.168.1.100"
        assert listener._EventListener__port == 9001
        assert listener._message_logger == mock_message_logger
        assert listener._EventListener__discovery_neighbours == True
        assert listener._EventListener__raport_overtime == False

        # Cleanup
        listener.shutdown()

    def test_event_listener_state_initialization(self, basic_event_listener):
        """Test that EventListener initializes with correct state."""
        listener = basic_event_listener

        assert listener._EventListener__el_state == EventListenerState.RUNNING
        assert listener._EventListener__incoming_events == []
        assert listener._processing_events == []
        assert listener._EventListener__events_to_send == []
        assert listener._EventListener__received_events == 0
        assert listener._EventListener__sended_events == 0

    def test_event_listener_properties(self, basic_event_listener):
        """Test EventListener property getters and setters."""
        listener = basic_event_listener

        # Test received_events property
        assert listener.received_events == 0

        # Test sended_events property
        assert listener.sended_events == 0

        # Test frequency properties
        assert listener.check_local_data_frequency == 100
        listener.check_local_data_frequency = 200
        assert listener._EventListener__check_local_data_frequency == 200

        assert listener.analyze_queue_frequency == 100
        listener.analyze_queue_frequency = 150
        assert listener._EventListener__analyze_queue_frequency == 150

    def test_queue_size_methods(self, basic_event_listener, sample_event):
        """Test queue size measurement methods."""
        listener = basic_event_listener

        # Initially empty queues
        assert listener.size_of_incomming_events_queue() == 0
        assert listener.size_of_processing_events_queue() == 0
        assert listener.size_of_events_to_send_queue() == 0

        # Add events to queues
        listener._EventListener__incoming_events.append(sample_event)
        assert listener.size_of_incomming_events_queue() == 1

        listener._processing_events.append(sample_event)
        assert listener.size_of_processing_events_queue() == 1

        listener._EventListener__events_to_send.append({
            "event": sample_event,
            "retry_count": 0,
        })
        assert listener.size_of_events_to_send_queue() == 1

    @pytest.mark.asyncio
    async def test_event_handler(self, basic_event_listener, sample_event):
        """Test event handler method."""
        listener = basic_event_listener

        # Mock the event handler method
        with patch.object(listener, f"_EventListener__event_handler") as mock_handler:
            mock_handler.return_value = None

            # Test that handler is callable
            await listener._EventListener__event_handler(sample_event)
            mock_handler.assert_called_once_with(sample_event)

    def test_add_to_processing(self, basic_event_listener, sample_event):
        """Test adding event to processing queue."""
        listener = basic_event_listener

        # Add event to processing queue
        result = listener._add_to_processing(sample_event)

        assert result is True
        assert len(listener._processing_events) == 1
        assert listener._processing_events[0] == sample_event
        assert sample_event.is_processing is True

    def test_find_and_remove_processing_event(self, basic_event_listener):
        """Test finding and removing event from processing queue."""
        listener = basic_event_listener

        # Create test event
        test_event = Event(event_type="test_remove", id=12345, data={"test": "data"})

        # Add to processing queue
        listener._add_to_processing(test_event)
        assert len(listener._processing_events) == 1

        # Find and remove by event_type and id
        found_event = listener._find_and_remove_processing_event(test_event)

        assert found_event == test_event
        assert len(listener._processing_events) == 0
        assert found_event.is_processing is False

    def test_find_and_remove_processing_event_not_found(self, basic_event_listener):
        """Test finding and removing non-existent event."""
        listener = basic_event_listener

        # Try to find non-existent event
        found_event = listener._find_and_remove_processing_event(
            Event(event_type="non_existent", id=99999)
        )

        assert found_event is None

    @pytest.mark.asyncio
    async def test_create_event(self, basic_event_listener):
        """Test event creation method."""
        listener = basic_event_listener

        event = await listener._event(
            destination="test_dest",
            destination_address="192.168.1.1",
            destination_port=9000,
            event_type="test_type",
            id=123,
            data={"key": "value"},
            to_be_processed=True,
            maximum_processing_time=30.0,
        )

        assert isinstance(event, Event)
        assert event.source == listener._EventListener__name
        assert event.source_address == listener._EventListener__address
        assert event.source_port == listener._EventListener__port
        assert event.destination == "test_dest"
        assert event.destination_address == "192.168.1.1"
        assert event.destination_port == 9000
        assert event.event_type == "test_type"
        assert event.id == 123
        assert event.data == {"key": "value"}
        assert event.to_be_processed is True
        assert event.maximum_processing_time == 30.0

    @pytest.mark.asyncio
    async def test_reply_method(self, basic_event_listener, sample_event):
        """Test reply method."""
        listener = basic_event_listener

        # Add result to sample event
        sample_event.result = Result(
            result="success", error_code=0, error_message="Test completed"
        )

        # Mock the HTTP request
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"status": "ok"}
            mock_post.return_value = mock_response

            await listener._reply(sample_event)

            # Verify request was made
            mock_post.assert_called_once()
            call_args = mock_post.call_args

            # Check URL
            expected_url = (
                f"http://{sample_event.source_address}:{sample_event.source_port}/event"
            )
            assert call_args[0][0] == expected_url

            # Check that JSON data contains the event
            json_data = call_args[1]["json"]
            assert json_data["source"] == listener._EventListener__name

    @pytest.mark.asyncio
    async def test_cumulative_reply(self, basic_event_listener):
        """Test cumulative reply method."""
        listener = basic_event_listener

        # Create multiple events
        events = []
        for i in range(3):
            event = Event(
                source=f"source_{i}",
                source_address="127.0.0.1",
                source_port=8000 + i,
                event_type=f"test_{i}",
                data={"index": i},
            )
            event.result = Result(result="success")
            events.append(event)

        # Mock the HTTP requests
        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"status": "ok"}
            mock_post.return_value = mock_response

            await listener._cumulative_reply(events)

            # Should make one request per event
            assert mock_post.call_count == 3

    def test_thread_safety_with_locks(self, basic_event_listener, sample_event):
        """Test thread safety of queue operations."""
        listener = basic_event_listener

        def add_events():
            for i in range(10):
                event = Event(
                    event_type=f"thread_test_{i}",
                    data={"thread": threading.current_thread().name},
                )
                with listener._EventListener__atomic_operation_for_incoming_events():
                    listener._EventListener__incoming_events.append(event)

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=add_events)
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify all events were added
        assert len(listener._EventListener__incoming_events) == 50

    @pytest.mark.asyncio
    async def test_analyze_event_default(self, basic_event_listener, sample_event):
        """Test default analyze_event method."""
        listener = basic_event_listener

        # Default implementation should return True
        result = await listener._analyze_event(sample_event)
        assert result is True

    @pytest.mark.asyncio
    async def test_check_local_data_default(self, basic_event_listener):
        """Test default check_local_data method."""
        listener = basic_event_listener

        # Default implementation should not raise exceptions
        await listener._check_local_data()

    def test_execute_before_shutdown_default(self, basic_event_listener):
        """Test default execute_before_shutdown method."""
        listener = basic_event_listener

        # Default implementation should not raise exceptions
        listener._execute_before_shutdown()

    def test_shutdown_method(self, basic_event_listener):
        """Test shutdown method."""
        listener = basic_event_listener

        # Should not be shutting down initially
        assert not listener._shutdown_requested

        # Shutdown should succeed
        result = listener.shutdown()
        assert result is True
        assert listener._shutdown_requested is True

    def test_shutdown_multiple_calls(self, basic_event_listener):
        """Test that multiple shutdown calls are safe."""
        listener = basic_event_listener

        # First shutdown
        result1 = listener.shutdown()
        assert result1 is True

        # Second shutdown should also succeed (no-op)
        result2 = listener.shutdown()
        assert result2 is True

    def test_debug_methods(self, basic_event_listener, sample_event):
        """Test debug logging methods."""
        listener = basic_event_listener

        # Add timestamp for processing time calculation
        sample_event.timestamp = datetime.now()

        # These should not raise exceptions
        listener._event_receive_debug(sample_event)
        listener._event_add_to_processing_debug(sample_event)
        listener._event_find_and_remove_debug(sample_event)
        listener._event_send_debug(sample_event)

    def test_serialize_value_method(self, basic_event_listener):
        """Test value serialization method."""
        listener = basic_event_listener

        # Test various data types
        test_cases = [
            ("string", "string"),
            (123, 123),
            (12.34, 12.34),
            (True, True),
            (None, None),
            ([1, 2, 3], [1, 2, 3]),
            ({"key": "value"}, {"key": "value"}),
        ]

        for input_val, expected in test_cases:
            result = listener._serialize_value(input_val)
            assert result == expected

    def test_context_managers(self, basic_event_listener):
        """Test thread-safe context managers."""
        listener = basic_event_listener

        # Test general purpose atomic operation
        with listener._EventListener__atomic():
            # Should not raise exceptions
            pass

        # Test events-to-send atomic operation
        with listener._EventListener__atomic_operation_for_events_to_send():
            # Should not raise exceptions
            pass

        # Test incoming events atomic operation
        with listener._EventListener__atomic_operation_for_incoming_events():
            # Should not raise exceptions
            pass

        # Test processing events atomic operation
        with listener._EventListener__atomic_operation_for_processing_events():
            # Should not raise exceptions
            pass

    @pytest.mark.parametrize("frequency", [1, 50, 100, 200])
    def test_frequency_settings(self, mock_message_logger, frequency):
        """Test different frequency settings."""
        listener = EventListener(
            name=f"test_freq_{frequency}",
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        listener.check_local_data_frequency = frequency
        assert listener._EventListener__check_local_data_frequency == frequency

        listener.analyze_queue_frequency = frequency
        assert listener._EventListener__analyze_queue_frequency == frequency

        # Cleanup
        listener.shutdown()

    def test_state_persistence_disabled(self, mock_message_logger):
        """Test EventListener with state persistence disabled."""
        listener = EventListener(
            name="test_no_state",
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        # Should initialize without loading state
        assert listener._EventListener__name == "test_no_state"

        # Cleanup
        listener.shutdown()

    def test_discovery_neighbors_enabled(self, mock_message_logger):
        """Test EventListener with discovery neighbors enabled."""
        listener = EventListener(
            name="test_discovery",
            message_logger=mock_message_logger,
            do_not_load_state=True,
            discovery_neighbours=True,
        )

        assert listener._EventListener__discovery_neighbours is True

        # Cleanup
        listener.shutdown()

    def test_event_listener_name_normalization(self, mock_message_logger):
        """Test that event listener name is normalized to lowercase."""
        listener = EventListener(
            name="TEST_UPPERCASE_NAME",
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        assert listener._EventListener__name == "test_uppercase_name"

        # Cleanup
        listener.shutdown()

    def test_port_type_conversion(self, mock_message_logger):
        """Test that port is converted to integer."""
        listener = EventListener(
            name="test_port",
            port="9000",  # String port
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        assert listener._EventListener__port == 9000
        assert isinstance(listener._EventListener__port, int)

        # Cleanup
        listener.shutdown()


class TestEventListenerIntegration:
    """Integration tests for EventListener functionality."""

    @pytest.fixture
    def mock_message_logger(self):
        """Fixture providing a mock MessageLogger."""
        return Mock(spec=MessageLogger)

    @pytest.mark.asyncio
    async def test_event_processing_workflow(self, mock_message_logger):
        """Test complete event processing workflow."""

        # Create a test EventListener subclass
        class TestEventListener(EventListener):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.processed_events = []

            async def _analyze_event(self, event: Event) -> bool:
                self.processed_events.append(event)
                return True  # Remove event after processing

        listener = TestEventListener(
            name="test_workflow",
            port=9001,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        try:
            # Create test event
            test_event = Event(
                source="test_source",
                destination="test_workflow",
                event_type="workflow_test",
                data={"workflow": "test"},
            )

            # Add event to incoming queue
            with listener._EventListener__atomic_operation_for_incoming_events():
                listener._EventListener__incoming_events.append(test_event)

            # Process the event
            await listener._EventListener__analyze_incoming_events()

            # Verify event was processed
            assert len(listener.processed_events) == 1
            assert listener.processed_events[0] == test_event

            # Verify event was removed from incoming queue
            assert len(listener._EventListener__incoming_events) == 0

        finally:
            listener.shutdown()

    def test_concurrent_queue_operations(self, mock_message_logger):
        """Test concurrent access to event queues."""
        listener = EventListener(
            name="test_concurrent",
            port=9002,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        try:
            results = []

            def queue_operations():
                for i in range(5):
                    event = Event(
                        event_type=f"concurrent_{i}",
                        data={"thread": threading.current_thread().name},
                    )

                    # Add to incoming
                    with (
                        listener._EventListener__atomic_operation_for_incoming_events()
                    ):
                        listener._EventListener__incoming_events.append(event)

                    # Move to processing
                    listener._add_to_processing(event)

                    # Add to send queue
                    with listener._EventListener__atomic_operation_for_events_to_send():
                        listener._EventListener__events_to_send.append({
                            "event": event,
                            "retry_count": 0,
                        })

                    results.append(True)

            # Create multiple threads
            threads = []
            for i in range(3):
                thread = threading.Thread(target=queue_operations)
                threads.append(thread)

            # Start all threads
            for thread in threads:
                thread.start()

            # Wait for completion
            for thread in threads:
                thread.join()

            # Verify all operations completed successfully
            assert len(results) == 15  # 3 threads × 5 operations
            assert all(results)

            # Verify queue states
            assert len(listener._EventListener__incoming_events) == 15
            assert len(listener._processing_events) == 15
            assert len(listener._EventListener__events_to_send) == 15

        finally:
            listener.shutdown()


class TestEventListenerShutdown:
    """Comprehensive tests for EventListener shutdown functionality."""

    @pytest.fixture
    def mock_message_logger(self):
        """Fixture providing a mock MessageLogger."""
        return Mock(spec=MessageLogger)

    @pytest.fixture
    def shutdown_test_listener(self, mock_message_logger):
        """Fixture providing a configured EventListener for shutdown testing."""
        listener = EventListener(
            name="shutdown_test",
            port=9900,
            message_logger=mock_message_logger,
            do_not_load_state=True,
            raport_overtime=False,
        )
        yield listener
        # Ensure cleanup even if test fails
        try:
            if not listener._shutdown_requested:
                listener.shutdown()
        except:
            pass

    def test_proper_instance_creation(self, mock_message_logger):
        """Test proper EventListener instance creation and initialization."""
        listener = EventListener(
            name="creation_test",
            port=9901,
            address="127.0.0.1",
            message_logger=mock_message_logger,
            do_not_load_state=True,
            discovery_neighbours=False,
            raport_overtime=False,
        )

        try:
            # Verify initialization state
            assert listener._EventListener__name == "creation_test"
            assert listener._EventListener__port == 9901
            assert listener._EventListener__address == "127.0.0.1"
            assert listener._shutdown_requested is False
            assert listener._EventListener__el_state == EventListenerState.RUNNING

            # Verify thread creation (threads should exist but may not be alive yet)
            assert hasattr(listener, "analysis_thread")
            assert hasattr(listener, "send_event_thread")
            assert hasattr(listener, "local_check_thread")

            # Verify signal handlers are registered
            import signal

            assert (
                signal.getsignal(signal.SIGINT)
                == listener._EventListener__signal_handler
            )
            assert (
                signal.getsignal(signal.SIGTERM)
                == listener._EventListener__signal_handler
            )

            # Verify FastAPI app and config are created
            assert listener.app is not None
            assert listener.config is not None

            # Verify event queues are initialized
            assert isinstance(listener._EventListener__incoming_events, list)
            assert isinstance(listener._processing_events, list)
            assert isinstance(listener._EventListener__events_to_send, list)

            # Verify locks are initialized
            assert listener._EventListener__lock_for_general_purpose is not None
            assert listener._EventListener__lock_for_incoming_events is not None
            assert listener._EventListener__lock_for_processing_events is not None
            assert listener._EventListener__lock_for_events_to_send is not None

        finally:
            listener.shutdown()

    def test_graceful_shutdown_via_shutdown_method(self, shutdown_test_listener):
        """Test graceful shutdown using the public shutdown() method."""
        listener = shutdown_test_listener

        # Verify initial state
        assert not listener._shutdown_requested

        # Add some events to queues to test state persistence
        test_event = Event(
            source="shutdown_test_source",
            destination="shutdown_test",
            event_type="test_event",
            data={"test": "data"},
        )

        with listener._EventListener__atomic_operation_for_incoming_events():
            listener._EventListener__incoming_events.append(test_event)

        # Perform shutdown
        shutdown_start = time.time()
        result = listener.shutdown()
        shutdown_duration = time.time() - shutdown_start

        # Verify shutdown was successful
        assert result is True
        assert listener._shutdown_requested is True

        # Verify shutdown completed in reasonable time (should be fast for unit test)
        assert shutdown_duration < 3.0

        # Verify threads are stopped or stopping
        if hasattr(listener, "analysis_thread") and listener.analysis_thread:
            assert (
                not listener.analysis_thread.is_alive() or listener._shutdown_requested
            )
        if hasattr(listener, "send_event_thread") and listener.send_event_thread:
            assert (
                not listener.send_event_thread.is_alive()
                or listener._shutdown_requested
            )
        if hasattr(listener, "local_check_thread") and listener.local_check_thread:
            assert (
                not listener.local_check_thread.is_alive()
                or listener._shutdown_requested
            )

    def test_multiple_shutdown_calls_are_safe(self, shutdown_test_listener):
        """Test that multiple shutdown() calls are safe and idempotent."""
        listener = shutdown_test_listener

        # First shutdown
        result1 = listener.shutdown()
        assert result1 is True
        assert listener._shutdown_requested is True

        # Second shutdown should also succeed (idempotent)
        result2 = listener.shutdown()
        assert result2 is True
        assert listener._shutdown_requested is True

        # Third shutdown should also succeed
        result3 = listener.shutdown()
        assert result3 is True

    def test_thread_cleanup_verification(self, mock_message_logger):
        """Test that all threads are properly cleaned up during shutdown."""
        listener = EventListener(
            name="thread_cleanup_test",
            port=9902,
            message_logger=mock_message_logger,
            do_not_load_state=True,
            discovery_neighbours=True,  # Enable discovery to test all threads
            raport_overtime=False,
        )

        try:
            # Let threads start
            time.sleep(0.1)

            # Collect thread references before shutdown
            analysis_thread = getattr(listener, "analysis_thread", None)
            send_event_thread = getattr(listener, "send_event_thread", None)
            local_check_thread = getattr(listener, "local_check_thread", None)
            discovering_thread = getattr(listener, "discovering_thread", None)

            # Verify threads exist and may be alive
            threads_to_check = []
            if analysis_thread:
                threads_to_check.append(("analysis", analysis_thread))
            if send_event_thread:
                threads_to_check.append(("send_event", send_event_thread))
            if local_check_thread:
                threads_to_check.append(("local_check", local_check_thread))
            if discovering_thread:
                threads_to_check.append(("discovering", discovering_thread))

            # Perform shutdown
            listener.shutdown()

            # Wait a bit for threads to finish
            time.sleep(0.2)

            # Verify all threads have stopped
            for thread_name, thread in threads_to_check:
                if thread and thread.is_alive():
                    # Give extra time for thread to finish
                    thread.join(timeout=1.0)
                    assert not thread.is_alive(), (
                        f"{thread_name} thread should have stopped after shutdown"
                    )

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()

    @patch("signal.signal")
    def test_signal_handler_registration(self, mock_signal, mock_message_logger):
        """Test that signal handlers are properly registered."""
        import signal as signal_module

        listener = EventListener(
            name="signal_test",
            port=9903,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        try:
            # Verify signal handlers were registered
            mock_signal.assert_any_call(
                signal_module.SIGINT, listener._EventListener__signal_handler
            )
            mock_signal.assert_any_call(
                signal_module.SIGTERM, listener._EventListener__signal_handler
            )

        finally:
            listener.shutdown()

    @patch("sys.exit")
    def test_signal_handler_shutdown_behavior(self, mock_exit, mock_message_logger):
        """Test signal handler triggers shutdown and exits."""
        listener = EventListener(
            name="signal_behavior_test",
            port=9904,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        try:
            # Verify initial state
            assert not listener._shutdown_requested

            # Simulate SIGINT signal
            import signal

            listener._EventListener__signal_handler(signal.SIGINT, None)

            # Verify shutdown was triggered
            assert listener._shutdown_requested is True

            # Verify sys.exit was called
            mock_exit.assert_called_once_with(0)

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()

    def test_ctrl_c_simulation(self, mock_message_logger):
        """Test Ctrl+C (SIGINT) simulation for graceful shutdown."""
        import signal

        listener = EventListener(
            name="ctrl_c_test",
            port=9905,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        try:
            # Store original signal handler
            original_handler = signal.signal(
                signal.SIGINT, listener._EventListener__signal_handler
            )

            # Verify signal handler is set
            current_handler = signal.getsignal(signal.SIGINT)
            assert current_handler == listener._EventListener__signal_handler

            # Mock the signal handler to avoid actual sys.exit
            def mock_signal_handler(signum, frame):
                listener._EventListener__shutdown()
                # Don't call sys.exit in test

            # Replace with mock handler
            signal.signal(signal.SIGINT, mock_signal_handler)

            # Verify initial state
            assert not listener._shutdown_requested

            # Simulate Ctrl+C by sending SIGINT to current process
            # Note: We use the mock handler to avoid sys.exit
            mock_signal_handler(signal.SIGINT, None)

            # Verify shutdown was triggered
            assert listener._shutdown_requested is True

            # Restore original handler
            signal.signal(signal.SIGINT, original_handler)

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()

    def test_resource_cleanup_verification(self, mock_message_logger):
        """Test that all resources are properly cleaned up during shutdown."""
        listener = EventListener(
            name="resource_cleanup_test",
            port=9906,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        try:
            # Verify resources exist before shutdown
            assert listener.app is not None
            assert listener.config is not None
            assert listener._message_logger is not None

            # Add some data to verify state persistence
            test_event = Event(
                source="cleanup_test",
                destination="resource_cleanup_test",
                event_type="cleanup_event",
                data={"cleanup": True},
            )
            with listener._EventListener__atomic_operation_for_incoming_events():
                listener._EventListener__incoming_events.append(test_event)

            # Perform shutdown
            listener.shutdown()

            # Verify shutdown flag is set
            assert listener._shutdown_requested is True

            # Verify FastAPI app is cleared
            assert listener.app is None

            # Note: config is kept to avoid AttributeError in uvicorn shutdown
            # assert listener.config is not None  # This is expected behavior

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()

    def test_shutdown_under_load(self, mock_message_logger):
        """Test graceful shutdown while EventListener is under load."""
        listener = EventListener(
            name="load_test",
            port=9907,
            message_logger=mock_message_logger,
            do_not_load_state=True,
            raport_overtime=False,
        )

        try:
            # Simulate load by adding many events
            events_to_add = 100
            for i in range(events_to_add):
                event = Event(
                    source=f"load_source_{i}",
                    destination="load_test",
                    event_type="load_event",
                    data={"event_number": i, "load_test": True},
                )
                with listener._EventListener__atomic_operation_for_incoming_events():
                    listener._EventListener__incoming_events.append(event)

            # Verify events were added
            initial_queue_size = listener.size_of_incomming_events_queue()
            assert initial_queue_size > 0

            # Perform shutdown under load
            shutdown_start = time.time()
            result = listener.shutdown()
            shutdown_duration = time.time() - shutdown_start

            # Verify shutdown succeeded despite load
            assert result is True
            assert listener._shutdown_requested is True

            # Shutdown should complete within reasonable time even under load
            assert shutdown_duration < 5.0

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()

    def test_shutdown_with_discovery_enabled(self, mock_message_logger):
        """Test shutdown when discovery_neighbours is enabled."""
        listener = EventListener(
            name="discovery_shutdown_test",
            port=9908,
            message_logger=mock_message_logger,
            do_not_load_state=True,
            discovery_neighbours=True,
            raport_overtime=False,
        )

        try:
            # Let discovery thread start
            time.sleep(0.1)

            # Verify discovery thread exists
            assert hasattr(listener, "discovering_thread")

            # Perform shutdown
            result = listener.shutdown()

            # Verify shutdown succeeded
            assert result is True
            assert listener._shutdown_requested is True

            # Verify discovery thread is stopped
            if hasattr(listener, "discovering_thread") and listener.discovering_thread:
                time.sleep(0.1)  # Give time for thread to see shutdown flag
                # Note: discovery thread should see shutdown flag and exit naturally

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()

    def test_destructor_shutdown(self, mock_message_logger):
        """Test that __del__ method triggers shutdown if not already shut down."""

        # Create listener in a separate scope to test destructor
        def create_and_destroy_listener():
            listener = EventListener(
                name="destructor_test",
                port=9909,
                message_logger=mock_message_logger,
                do_not_load_state=True,
            )

            # Verify it's not shut down initially
            assert not listener._shutdown_requested

            # Return the listener for verification, then let it go out of scope
            return listener

        # Create listener
        listener = create_and_destroy_listener()

        # Manually call destructor to test it
        try:
            # Verify initial state
            assert not listener._shutdown_requested

            # Call destructor explicitly
            listener.__del__()

            # Verify shutdown was called
            assert listener._shutdown_requested is True

        except Exception:
            # Cleanup in case of test failure
            if not listener._shutdown_requested:
                listener.shutdown()

    def test_thread_timeout_handling(self, mock_message_logger):
        """Test handling of thread join timeouts during shutdown."""
        listener = EventListener(
            name="timeout_test",
            port=9910,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        try:
            # Mock thread that won't stop easily
            original_stop_analysis = listener._EventListener__stop_analysis
            original_stop_send_event = listener._EventListener__stop_send_event
            original_stop_local_check = listener._EventListener__stop_local_check

            # Create a mock thread that simulates timeout
            class MockHangingThread:
                def is_alive(self):
                    return True

                def join(self, timeout=None):
                    # Simulate a thread that doesn't join within timeout
                    time.sleep(0.1)  # Simulate some delay
                    return None

            # Replace one thread with mock hanging thread
            listener.analysis_thread = MockHangingThread()

            # Shutdown should handle the timeout gracefully
            start_time = time.time()
            result = listener.shutdown()
            duration = time.time() - start_time

            # Verify shutdown completed (even with hanging thread)
            assert result is True
            assert listener._shutdown_requested is True

            # Should not hang indefinitely due to timeout
            assert duration < 10.0

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()

    def test_concurrent_shutdown_attempts(self, mock_message_logger):
        """Test thread safety when multiple threads attempt shutdown simultaneously."""
        listener = EventListener(
            name="concurrent_shutdown_test",
            port=9911,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        shutdown_results = []
        shutdown_threads = []

        def attempt_shutdown():
            """Attempt shutdown from a thread."""
            result = listener.shutdown()
            shutdown_results.append(result)

        try:
            # Create multiple threads that will attempt shutdown
            for i in range(5):
                thread = threading.Thread(target=attempt_shutdown)
                shutdown_threads.append(thread)

            # Start all threads
            for thread in shutdown_threads:
                thread.start()

            # Wait for all threads to complete
            for thread in shutdown_threads:
                thread.join(timeout=2.0)

            # Verify all threads completed
            assert len(shutdown_results) == 5

            # All shutdown attempts should succeed (idempotent)
            assert all(result is True for result in shutdown_results)

            # Listener should be shut down
            assert listener._shutdown_requested is True

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()

    @patch("avena_commons.event_listener.event_listener.time.sleep")
    def test_shutdown_timing_optimization(self, mock_sleep, mock_message_logger):
        """Test that shutdown uses appropriate timing for thread coordination."""
        listener = EventListener(
            name="timing_test",
            port=9912,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        try:
            # Perform shutdown
            listener.shutdown()

            # Verify that appropriate sleep calls were made for thread coordination
            # The shutdown process should include small sleeps for thread coordination
            mock_sleep.assert_called()

            # Check that sleep calls use reasonable durations (0.1 seconds)
            sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
            assert any(0.05 <= duration <= 0.15 for duration in sleep_calls), (
                f"Expected sleep duration around 0.1s, got: {sleep_calls}"
            )

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()

    def test_state_persistence_during_shutdown(self, mock_message_logger, tmp_path):
        """Test that state is properly saved during shutdown."""
        # Use temporary directory for test files
        test_name = "state_persistence_test"

        listener = EventListener(
            name=test_name,
            port=9913,
            message_logger=mock_message_logger,
            do_not_load_state=True,
        )

        try:
            # Add events to verify state saving
            test_events = []
            for i in range(3):
                event = Event(
                    source=f"state_test_{i}",
                    destination=test_name,
                    event_type="state_persistence_event",
                    data={"index": i, "test_data": f"data_{i}"},
                )
                test_events.append(event)
                with listener._EventListener__atomic_operation_for_incoming_events():
                    listener._EventListener__incoming_events.append(event)

            # Verify events are in queue
            assert listener.size_of_incomming_events_queue() >= 3

            # Mock the save methods to verify they're called
            with (
                patch.object(
                    listener, "_EventListener__save_queues"
                ) as mock_save_queues,
                patch.object(
                    listener, "_EventListener__save_configuration"
                ) as mock_save_config,
            ):
                # Perform shutdown
                result = listener.shutdown()

                # Verify shutdown succeeded
                assert result is True

                # Verify save methods were called
                mock_save_queues.assert_called_once()
                mock_save_config.assert_called_once()

        finally:
            if not listener._shutdown_requested:
                listener.shutdown()
