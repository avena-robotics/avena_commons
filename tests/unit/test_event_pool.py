"""
Unit tests for EventPool module.

Tests all EventPool classes: EventPool, IncomingEventPool, ProcessingEventPool, SendingEventPool
"""

import time
from datetime import datetime, timedelta

import pytest

from avena_commons.event_listener.event import Event
from avena_commons.event_listener.event_pool import (
    EventMetadata,
    EventPool,
    IncomingEventPool,
    OverflowPolicy,
    ProcessingEventPool,
    SendingEventPool,
)


@pytest.fixture
def sample_event():
    """Create a sample event for testing"""
    return Event(
        source="test_source",
        source_address="127.0.0.1",
        source_port=8000,
        destination="test_destination",
        destination_address="127.0.0.1",
        destination_port=8001,
        event_type="test_event",
        data={"test": "data"},
    )


@pytest.fixture
def sample_events():
    """Create multiple sample events with different timestamps"""
    events = []
    base_time = datetime.now()
    for i in range(5):
        event = Event(
            source="test_source",
            source_address="127.0.0.1",
            source_port=8000,
            destination="test_destination",
            destination_address="127.0.0.1",
            destination_port=8001,
            event_type=f"test_event_{i}",
            data={"index": i},
            timestamp=base_time + timedelta(seconds=i),
        )
        events.append(event)
    return events


class TestEventMetadata:
    """Tests for EventMetadata dataclass"""

    def test_creation(self, sample_event):
        """Test EventMetadata creation"""
        meta = EventMetadata(event=sample_event)
        assert meta.event == sample_event
        assert meta.retry_count == 0
        assert meta.priority == 0
        assert isinstance(meta.added_at, datetime)
        assert isinstance(meta.metadata, dict)

    def test_age_seconds(self, sample_event):
        """Test age_seconds property"""
        meta = EventMetadata(event=sample_event)
        time.sleep(0.1)
        assert meta.age_seconds >= 0.1

    def test_timestamp_key(self, sample_event):
        """Test timestamp_key property"""
        meta = EventMetadata(event=sample_event)
        assert meta.timestamp_key == sample_event.timestamp.isoformat()


class TestEventPool:
    """Tests for base EventPool class"""

    def test_initialization(self):
        """Test EventPool initialization"""
        pool = EventPool(name="test_pool", max_size=10)
        assert pool.name == "test_pool"
        assert pool.max_size == 10
        assert len(pool) == 0

    def test_append_single_event(self, sample_event):
        """Test appending a single event"""
        pool = EventPool(name="test_pool")
        result = pool.append(sample_event)
        assert result is True
        assert len(pool) == 1
        assert sample_event.timestamp.isoformat() in pool

    def test_append_duplicate_timestamp(self, sample_event):
        """Test that duplicate timestamps are rejected"""
        pool = EventPool(name="test_pool")
        pool.append(sample_event)
        result = pool.append(sample_event)  # Same timestamp
        assert result is False
        assert len(pool) == 1

    def test_extend_multiple_events(self, sample_events):
        """Test extending with multiple events"""
        pool = EventPool(name="test_pool")
        added = pool.extend(sample_events)
        assert added == len(sample_events)
        assert len(pool) == len(sample_events)

    def test_pop_oldest(self, sample_events):
        """Test popping oldest event (FIFO)"""
        pool = EventPool(name="test_pool")
        pool.extend(sample_events)

        meta = pool.pop_oldest()
        assert meta.event == sample_events[0]  # First event
        assert len(pool) == len(sample_events) - 1

    def test_pop_by_timestamp(self, sample_events):
        """Test popping by specific timestamp"""
        pool = EventPool(name="test_pool")
        pool.extend(sample_events)

        target_event = sample_events[2]
        meta = pool.pop_by_timestamp(target_event.timestamp)
        assert meta.event == target_event
        assert len(pool) == len(sample_events) - 1

    def test_peek_oldest(self, sample_events):
        """Test peeking at oldest without removing"""
        pool = EventPool(name="test_pool")
        pool.extend(sample_events)

        meta = pool.peek_oldest()
        assert meta.event == sample_events[0]
        assert len(pool) == len(sample_events)  # Not removed

    def test_get_by_timestamp(self, sample_events):
        """Test getting by timestamp without removing"""
        pool = EventPool(name="test_pool")
        pool.extend(sample_events)

        target_event = sample_events[2]
        meta = pool.get_by_timestamp(target_event.timestamp)
        assert meta.event == target_event
        assert len(pool) == len(sample_events)  # Not removed

    def test_filter(self, sample_events):
        """Test filtering events"""
        pool = EventPool(name="test_pool")
        pool.extend(sample_events)

        # Filter events with even index
        filtered = pool.filter(lambda meta: meta.event.data["index"] % 2 == 0)
        assert len(filtered) == 3  # indices 0, 2, 4

    def test_remove_if(self, sample_events):
        """Test conditional removal"""
        pool = EventPool(name="test_pool")
        pool.extend(sample_events)

        # Remove events with even index
        removed = pool.remove_if(lambda meta: meta.event.data["index"] % 2 == 0)
        assert removed == 3
        assert len(pool) == 2  # indices 1, 3 remain

    def test_clear(self, sample_events):
        """Test clearing the pool"""
        pool = EventPool(name="test_pool")
        pool.extend(sample_events)

        count = pool.clear()
        assert count == len(sample_events)
        assert len(pool) == 0

    def test_copy(self, sample_events):
        """Test copying the pool"""
        pool = EventPool(name="test_pool")
        pool.extend(sample_events)

        pool_copy = pool.copy()
        assert len(pool_copy) == len(pool)
        assert pool_copy is not pool._pool  # Different object

    def test_iterator(self, sample_events):
        """Test iterating over pool"""
        pool = EventPool(name="test_pool")
        pool.extend(sample_events)

        collected = list(pool)
        assert len(collected) == len(sample_events)
        assert all(isinstance(meta, EventMetadata) for meta in collected)

    def test_contains(self, sample_event):
        """Test __contains__ operator"""
        pool = EventPool(name="test_pool")
        pool.append(sample_event)

        assert sample_event in pool
        assert sample_event.timestamp.isoformat() in pool

    def test_get_stats(self, sample_events):
        """Test getting pool statistics"""
        pool = EventPool(name="test_pool", max_size=100)
        pool.extend(sample_events)

        stats = pool.get_stats()
        assert stats["name"] == "test_pool"
        assert stats["size"] == len(sample_events)
        assert stats["max_size"] == 100
        assert stats["total_added"] == len(sample_events)
        assert stats["total_removed"] == 0
        assert stats["total_dropped"] == 0
        assert stats["oldest_event"] is not None
        assert stats["newest_event"] is not None


class TestOverflowPolicies:
    """Tests for different overflow policies"""

    def test_drop_oldest_policy(self, sample_events):
        """Test DROP_OLDEST overflow policy"""
        pool = EventPool(
            name="test_pool", max_size=3, overflow_policy=OverflowPolicy.DROP_OLDEST
        )

        # Add 5 events to pool with max_size=3
        pool.extend(sample_events)

        # Should have 3 newest events
        assert len(pool) == 3
        remaining = [meta.event for meta in pool]
        assert sample_events[2] in remaining
        assert sample_events[3] in remaining
        assert sample_events[4] in remaining

        stats = pool.get_stats()
        assert stats["total_dropped"] == 2  # 2 oldest dropped

    def test_drop_newest_policy(self, sample_events):
        """Test DROP_NEWEST overflow policy"""
        pool = EventPool(
            name="test_pool", max_size=3, overflow_policy=OverflowPolicy.DROP_NEWEST
        )

        # Add first 3 events
        pool.extend(sample_events[:3])
        assert len(pool) == 3

        # Try to add 2 more - should be rejected
        result1 = pool.append(sample_events[3])
        result2 = pool.append(sample_events[4])
        assert result1 is False
        assert result2 is False
        assert len(pool) == 3

        # Should have 3 oldest events
        remaining = [meta.event for meta in pool]
        assert sample_events[0] in remaining
        assert sample_events[1] in remaining
        assert sample_events[2] in remaining

        stats = pool.get_stats()
        assert stats["total_dropped"] == 2

    def test_raise_error_policy(self, sample_events):
        """Test RAISE_ERROR overflow policy"""
        pool = EventPool(
            name="test_pool", max_size=3, overflow_policy=OverflowPolicy.RAISE_ERROR
        )

        pool.extend(sample_events[:3])
        assert len(pool) == 3

        # Next append should raise OverflowError
        with pytest.raises(OverflowError, match="Queue overflow"):
            pool.append(sample_events[3])

    def test_unlimited_policy(self, sample_events):
        """Test UNLIMITED overflow policy"""
        pool = EventPool(
            name="test_pool",
            max_size=3,
            overflow_policy=OverflowPolicy.UNLIMITED,  # max_size ignored
        )

        pool.extend(sample_events)
        assert len(pool) == len(sample_events)  # All added despite max_size=3


class TestAutoCleanup:
    """Tests for automatic cleanup of old events"""

    def test_cleanup_old_events(self, sample_event):
        """Test that old events are cleaned up automatically"""
        pool = EventPool(name="test_pool", max_age_seconds=0.2)

        pool.append(sample_event)
        assert len(pool) == 1

        # Wait for event to age
        time.sleep(0.3)

        # Cleanup is triggered on next operation
        pool._cleanup_old_events()
        assert len(pool) == 0

        stats = pool.get_stats()
        assert stats["total_removed"] == 1

    def test_cleanup_triggered_on_append(self, sample_events):
        """Test cleanup is triggered automatically on append"""
        pool = EventPool(name="test_pool", max_age_seconds=0.2)

        # Add first event
        pool.append(sample_events[0])
        time.sleep(0.3)  # Let it age

        # Add second event - should trigger cleanup of first
        pool.append(sample_events[1])

        assert len(pool) == 1  # Only second event remains


class TestIncomingEventPool:
    """Tests for IncomingEventPool specialization"""

    def test_initialization(self):
        """Test IncomingEventPool initialization"""
        pool = IncomingEventPool()
        assert pool.name == "incoming_events"
        assert pool.max_size == 10000
        assert pool.max_age_seconds == 300
        assert pool.overflow_policy == OverflowPolicy.DROP_OLDEST

    def test_pop_batch(self, sample_events):
        """Test batch popping"""
        pool = IncomingEventPool()
        pool.extend(sample_events)

        batch = pool.pop_batch(batch_size=3)
        assert len(batch) == 3
        assert len(pool) == 2  # 5 - 3 = 2 remaining

        # Check FIFO order
        assert batch[0].event == sample_events[0]
        assert batch[1].event == sample_events[1]
        assert batch[2].event == sample_events[2]


class TestProcessingEventPool:
    """Tests for ProcessingEventPool specialization"""

    def test_initialization(self):
        """Test ProcessingEventPool initialization"""
        pool = ProcessingEventPool()
        assert pool.name == "processing_events"
        assert pool.max_size is None  # Unlimited
        assert pool.overflow_policy == OverflowPolicy.UNLIMITED

    def test_get_timed_out_events(self):
        """Test getting timed-out events"""
        pool = ProcessingEventPool(max_timeout=0.2)

        # Create event with short timeout
        event = Event(
            source="test",
            source_address="127.0.0.1",
            source_port=8000,
            destination="test",
            destination_address="127.0.0.1",
            destination_port=8001,
            event_type="test",
            maximum_processing_time=0.1,  # 100ms timeout
        )

        pool.append(event)
        time.sleep(0.15)  # Wait past timeout

        timed_out = pool.get_timed_out_events()
        assert len(timed_out) == 1
        assert timed_out[0].event == event

    def test_cleanup_timed_out(self):
        """Test cleanup of timed-out events"""
        pool = ProcessingEventPool(max_timeout=0.2)

        event = Event(
            source="test",
            source_address="127.0.0.1",
            source_port=8000,
            destination="test",
            destination_address="127.0.0.1",
            destination_port=8001,
            event_type="test",
            maximum_processing_time=0.1,
        )

        pool.append(event)
        time.sleep(0.15)

        removed = pool.cleanup_timed_out()
        assert removed == 1
        assert len(pool) == 0


class TestSendingEventPool:
    """Tests for SendingEventPool specialization"""

    def test_initialization(self):
        """Test SendingEventPool initialization"""
        pool = SendingEventPool()
        assert pool.name == "events_to_send"
        assert pool.max_size == 50000
        assert pool.max_retries == 3

    def test_append_with_retry(self, sample_event):
        """Test appending with retry count"""
        pool = SendingEventPool()

        result = pool.append_with_retry(sample_event, retry_count=1)
        assert result is True

        meta = pool.get_by_timestamp(sample_event.timestamp)
        assert meta.retry_count == 1

    def test_increment_retry(self, sample_event):
        """Test incrementing retry count"""
        pool = SendingEventPool(max_retries=3)
        pool.append_with_retry(sample_event, retry_count=0)

        # Increment once
        meta = pool.increment_retry(sample_event.timestamp)
        assert meta is not None
        assert meta.retry_count == 1

        # Increment to max
        pool.increment_retry(sample_event.timestamp)
        pool.increment_retry(sample_event.timestamp)

        # Next increment should remove event (exceeded max)
        meta = pool.increment_retry(sample_event.timestamp)
        assert meta is None
        assert len(pool) == 0

    def test_group_by_destination(self):
        """Test grouping events by destination"""
        pool = SendingEventPool()

        # Create events with different destinations
        events = []
        for i in range(5):
            port = 8001 if i < 3 else 8002  # 3 to port 8001, 2 to port 8002
            event = Event(
                source="test",
                source_address="127.0.0.1",
                source_port=8000,
                destination="test",
                destination_address="127.0.0.1",
                destination_port=port,
                event_type=f"test_{i}",
                timestamp=datetime.now() + timedelta(seconds=i),
            )
            events.append(event)
            pool.append(event)

        groups = pool.group_by_destination()
        assert len(groups) == 2  # Two destinations
        assert len(groups[("127.0.0.1", 8001)]) == 3
        assert len(groups[("127.0.0.1", 8002)]) == 2

    def test_pop_batch_grouped(self):
        """Test popping batch grouped by destination"""
        pool = SendingEventPool()

        # Create events
        events = []
        for i in range(5):
            port = 8001 if i < 3 else 8002
            event = Event(
                source="test",
                source_address="127.0.0.1",
                source_port=8000,
                destination="test",
                destination_address="127.0.0.1",
                destination_port=port,
                event_type=f"test_{i}",
                timestamp=datetime.now() + timedelta(seconds=i),
            )
            events.append(event)
            pool.append(event)

        groups = pool.pop_batch_grouped(batch_size=10)
        assert len(groups) == 2
        assert len(pool) == 0  # All removed


class TestThreadSafety:
    """Tests for thread-safety using RLock"""

    def test_reentrant_lock(self, sample_event):
        """Test that RLock allows reentrant calls"""
        pool = EventPool(name="test_pool")

        # extend() calls append() - both acquire lock
        # RLock should handle this without deadlock
        result = pool.extend([sample_event])
        assert result == 1
        assert len(pool) == 1

    def test_concurrent_access(self, sample_events):
        """Test concurrent access from multiple threads"""
        import threading

        pool = EventPool(name="test_pool", max_size=1000)
        threads = []

        def add_events(events):
            for event in events:
                pool.append(event)

        # Split events across threads
        chunk_size = len(sample_events) // 2
        for i in range(2):
            chunk = sample_events[i * chunk_size : (i + 1) * chunk_size]
            thread = threading.Thread(target=add_events, args=(chunk,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All events should be added (no race conditions)
        assert len(pool) == len(sample_events)
