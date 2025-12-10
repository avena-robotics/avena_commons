"""
Event Pool module for thread-safe event queue management.

This module provides a unified queue system for EventListener using
timestamp-based dictionaries for fast lookups and automatic deduplication.
"""

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Iterator, Optional

from avena_commons.util.logger import MessageLogger, debug, error, warning

from .event import Event


class OverflowPolicy(Enum):
    """Policy for handling queue overflow"""

    DROP_OLDEST = "drop_oldest"  # Remove oldest events
    DROP_NEWEST = "drop_newest"  # Reject new events
    RAISE_ERROR = "raise_error"  # Raise exception
    UNLIMITED = "unlimited"  # No limit


@dataclass
class EventMetadata:
    """
    Metadata wrapper for events in the pool.

    Attributes:
        event: The actual Event object
        added_at: When the event was added to the pool
        retry_count: Number of retry attempts (for sending queue)
        priority: Priority level (higher = more important)
        metadata: Additional custom metadata
    """

    event: Event
    added_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        """Age of the event in seconds since it was added"""
        return (datetime.now() - self.added_at).total_seconds()

    @property
    def timestamp_key(self) -> str:
        """ISO format timestamp key for this event"""
        return self.event.timestamp.isoformat()


class EventPool:
    """
    Thread-safe pool of events using timestamp as key.

    Features:
    - Dictionary {timestamp_iso: EventMetadata} for O(1) lookups
    - Thread-safe operations using RLock (reentrant)
    - Configurable max size with overflow policies
    - Automatic garbage collection of old events
    - Filtering and iteration support
    - Built-in statistics tracking

    Example:
        >>> pool = EventPool(name="test", max_size=1000)
        >>> pool.append(event)
        True
        >>> meta = pool.pop_oldest()
        >>> print(pool.get_stats())
    """

    def __init__(
        self,
        name: str,
        max_size: Optional[int] = None,
        overflow_policy: OverflowPolicy = OverflowPolicy.DROP_OLDEST,
        max_age_seconds: Optional[float] = None,
        message_logger: Optional[MessageLogger] = None,
    ):
        """
        Initialize EventPool.

        Args:
            name: Name of the pool (for logging)
            max_size: Maximum number of events (None = unlimited)
            overflow_policy: What to do when pool is full
            max_age_seconds: Auto-cleanup events older than this (None = no cleanup)
            message_logger: Logger instance
        """
        self.name = name
        self.max_size = max_size
        self.overflow_policy = overflow_policy
        self.max_age_seconds = max_age_seconds
        self._message_logger = message_logger

        # OrderedDict maintains insertion order (Python 3.7+)
        self._pool: OrderedDict[str, EventMetadata] = OrderedDict()
        self._lock = threading.RLock()  # Reentrant lock - allows recursion

        # Statistics
        self._total_added = 0
        self._total_removed = 0
        self._total_dropped = 0

    def __len__(self) -> int:
        """Return the number of events in the pool"""
        with self._lock:
            return len(self._pool)

    def __contains__(self, timestamp_or_event) -> bool:
        """Check if an event exists in the pool"""
        with self._lock:
            if isinstance(timestamp_or_event, Event):
                key = timestamp_or_event.timestamp.isoformat()
            else:
                key = timestamp_or_event
            return key in self._pool

    def __iter__(self) -> Iterator[EventMetadata]:
        """Iterate over events in chronological order"""
        with self._lock:
            # Return iterator over a copy to avoid modification during iteration
            return iter(list(self._pool.values()))

    def __repr__(self) -> str:
        return f"EventPool(name={self.name}, size={len(self)}, max_size={self.max_size})"

    def _make_key(self, event: Event) -> str:
        """Create timestamp key for an event"""
        return event.timestamp.isoformat()

    def _cleanup_old_events(self) -> int:
        """
        Remove events older than max_age_seconds.

        Returns:
            Number of events removed
        """
        if self.max_age_seconds is None:
            return 0

        with self._lock:
            to_remove = []

            for key, meta in self._pool.items():
                if meta.age_seconds > self.max_age_seconds:
                    to_remove.append(key)

            for key in to_remove:
                del self._pool[key]
                self._total_removed += 1

            if to_remove:
                debug(
                    f"{self.name}: Cleaned up {len(to_remove)} old events",
                    message_logger=self._message_logger,
                )

            return len(to_remove)

    def _handle_overflow(self) -> bool:
        """
        Handle queue overflow according to policy.

        Returns:
            True if event can be added, False if should be rejected
        """
        if self.max_size is None or len(self._pool) < self.max_size:
            return True

        match self.overflow_policy:
            case OverflowPolicy.DROP_OLDEST:
                # Remove oldest event (first in OrderedDict)
                if self._pool:
                    oldest_key = next(iter(self._pool))
                    del self._pool[oldest_key]
                    self._total_dropped += 1
                    debug(
                        f"{self.name}: Dropped oldest event due to overflow",
                        message_logger=self._message_logger,
                    )
                return True

            case OverflowPolicy.DROP_NEWEST:
                # Reject new event
                self._total_dropped += 1
                warning(
                    f"{self.name}: Dropped new event due to overflow",
                    message_logger=self._message_logger,
                )
                return False

            case OverflowPolicy.RAISE_ERROR:
                raise OverflowError(
                    f"{self.name}: Queue overflow (max_size={self.max_size})"
                )

            case OverflowPolicy.UNLIMITED:
                return True

        return True

    def append(
        self,
        event: Event,
        retry_count: int = 0,
        priority: int = 0,
        metadata: Optional[dict] = None,
    ) -> bool:
        """
        Add an event to the pool.

        Args:
            event: Event to add
            retry_count: Retry counter (for sending queue)
            priority: Priority level
            metadata: Additional metadata dictionary

        Returns:
            True if added, False if rejected (DROP_NEWEST policy or duplicate)
        """
        with self._lock:
            # Cleanup old events
            self._cleanup_old_events()

            # Check overflow
            if not self._handle_overflow():
                return False

            key = self._make_key(event)

            # Check for duplicate timestamp
            if key in self._pool:
                debug(
                    f"{self.name}: Event with timestamp {key} already exists, skipping",
                    message_logger=self._message_logger,
                )
                return False

            # Add event
            self._pool[key] = EventMetadata(
                event=event,
                retry_count=retry_count,
                priority=priority,
                metadata=metadata or {},
            )
            self._total_added += 1

            return True

    def extend(self, events: list[Event]) -> int:
        """
        Add multiple events at once.

        Args:
            events: List of events to add

        Returns:
            Number of events actually added
        """
        with self._lock:  # Single lock for entire operation
            added = 0
            for event in events:
                # Note: append() will try to acquire lock again, but RLock allows this
                if self.append(event):
                    added += 1
                else:
                    # If overflow policy is DROP_NEWEST, stop trying
                    if self.overflow_policy == OverflowPolicy.DROP_NEWEST:
                        break
            return added

    def pop_oldest(self) -> Optional[EventMetadata]:
        """
        Get and remove the oldest event (FIFO).

        Returns:
            EventMetadata or None if pool is empty
        """
        with self._lock:
            if not self._pool:
                return None

            # Get first key (oldest)
            oldest_key = next(iter(self._pool))
            meta = self._pool.pop(oldest_key)
            self._total_removed += 1

            return meta

    def pop_by_timestamp(self, timestamp) -> Optional[EventMetadata]:
        """
        Get and remove event by timestamp.

        Args:
            timestamp: datetime or ISO string

        Returns:
            EventMetadata or None if not found
        """
        with self._lock:
            if isinstance(timestamp, datetime):
                key = timestamp.isoformat()
            else:
                key = str(timestamp)

            meta = self._pool.pop(key, None)
            if meta:
                self._total_removed += 1

            return meta

    def peek_oldest(self) -> Optional[EventMetadata]:
        """
        Get oldest event without removing it.

        Returns:
            EventMetadata or None if pool is empty
        """
        with self._lock:
            if not self._pool:
                return None
            return next(iter(self._pool.values()))

    def get_by_timestamp(self, timestamp) -> Optional[EventMetadata]:
        """
        Get event by timestamp without removing it.

        Args:
            timestamp: datetime or ISO string

        Returns:
            EventMetadata or None if not found
        """
        with self._lock:
            if isinstance(timestamp, datetime):
                key = timestamp.isoformat()
            else:
                key = str(timestamp)
            return self._pool.get(key)

    def filter(
        self, predicate: Callable[[EventMetadata], bool]
    ) -> list[EventMetadata]:
        """
        Return list of events matching predicate.

        Args:
            predicate: Function that takes EventMetadata and returns bool

        Returns:
            List of matching EventMetadata objects
        """
        with self._lock:
            return [meta for meta in self._pool.values() if predicate(meta)]

    def remove_if(self, predicate: Callable[[EventMetadata], bool]) -> int:
        """
        Remove events matching predicate.

        Args:
            predicate: Function that takes EventMetadata and returns bool

        Returns:
            Number of events removed
        """
        with self._lock:
            to_remove = [
                key for key, meta in self._pool.items() if predicate(meta)
            ]

            for key in to_remove:
                del self._pool[key]
                self._total_removed += 1

            return len(to_remove)

    def copy(self) -> OrderedDict[str, EventMetadata]:
        """
        Return a copy of the pool.

        Returns:
            OrderedDict copy of the pool
        """
        with self._lock:
            return self._pool.copy()

    def clear(self) -> int:
        """
        Clear the entire pool.

        Returns:
            Number of events removed
        """
        with self._lock:
            count = len(self._pool)
            self._pool.clear()
            self._total_removed += count
            return count

    def get_stats(self) -> dict:
        """
        Get pool statistics.

        Returns:
            Dictionary with stats: size, oldest/newest timestamps, averages, totals
        """
        with self._lock:
            oldest = None
            newest = None
            total_age = 0.0

            if self._pool:
                oldest_meta = next(iter(self._pool.values()))
                newest_meta = next(reversed(self._pool.values()))
                oldest = oldest_meta.added_at
                newest = newest_meta.added_at
                total_age = sum(meta.age_seconds for meta in self._pool.values())

            return {
                "name": self.name,
                "size": len(self._pool),
                "max_size": self.max_size,
                "overflow_policy": self.overflow_policy.value,
                "oldest_event": oldest,
                "newest_event": newest,
                "avg_age_seconds": total_age / len(self._pool) if self._pool else 0,
                "total_added": self._total_added,
                "total_removed": self._total_removed,
                "total_dropped": self._total_dropped,
            }


class IncomingEventPool(EventPool):
    """
    Pool for incoming events from external sources.

    Features:
    - FIFO processing
    - Batch operations for efficiency
    - Automatic cleanup of old events
    - Default overflow: drop oldest
    """

    def __init__(
        self, max_size: int = 10000, max_age_seconds: float = 300, **kwargs
    ):
        """
        Initialize IncomingEventPool.

        Args:
            max_size: Maximum queue size (default 10000)
            max_age_seconds: Auto-cleanup after this many seconds (default 300 = 5 min)
            **kwargs: Additional arguments passed to EventPool
        """
        super().__init__(
            name="incoming_events",
            max_size=max_size,
            overflow_policy=OverflowPolicy.DROP_OLDEST,
            max_age_seconds=max_age_seconds,
            **kwargs,
        )

    def pop_batch(self, batch_size: int = 100) -> list[EventMetadata]:
        """
        Get a batch of oldest events (for efficient processing).

        Args:
            batch_size: Maximum number of events to retrieve

        Returns:
            List of EventMetadata objects (up to batch_size)
        """
        with self._lock:
            batch = []
            for _ in range(min(batch_size, len(self._pool))):
                meta = self.pop_oldest()
                if meta:
                    batch.append(meta)
                else:
                    break
            return batch


class ProcessingEventPool(EventPool):
    """
    Pool for events currently being processed.

    Features:
    - Timeout tracking
    - Unlimited size
    - Timeout-based cleanup
    """

    def __init__(self, max_timeout: float = 60.0, **kwargs):
        """
        Initialize ProcessingEventPool.

        Args:
            max_timeout: Default timeout for processing (default 60s)
            **kwargs: Additional arguments passed to EventPool
        """
        super().__init__(
            name="processing_events",
            max_size=None,  # Unlimited
            overflow_policy=OverflowPolicy.UNLIMITED,
            max_age_seconds=max_timeout * 2,  # Cleanup at 2x timeout
            **kwargs,
        )
        self.max_timeout = max_timeout

    def get_timed_out_events(self) -> list[EventMetadata]:
        """
        Get events that exceeded their processing timeout.

        Returns:
            List of timed-out EventMetadata objects
        """
        return self.filter(
            lambda meta: meta.event.maximum_processing_time > 0
            and meta.age_seconds > meta.event.maximum_processing_time
        )

    def cleanup_timed_out(self) -> int:
        """
        Remove events that exceeded their timeout.

        Returns:
            Number of events removed
        """
        count = self.remove_if(
            lambda meta: meta.event.maximum_processing_time > 0
            and meta.age_seconds > meta.event.maximum_processing_time
        )

        if count > 0:
            warning(
                f"{self.name}: Removed {count} timed-out events",
                message_logger=self._message_logger,
            )

        return count


class SendingEventPool(EventPool):
    """
    Pool for events waiting to be sent to other components.

    Features:
    - Retry logic with max retries
    - Grouping by destination
    - Batch sending support
    - Automatic cleanup of failed events
    """

    def __init__(self, max_retries: int = 3, **kwargs):
        """
        Initialize SendingEventPool.

        Args:
            max_retries: Maximum retry attempts (default 3)
            **kwargs: Additional arguments passed to EventPool
        """
        super().__init__(
            name="events_to_send",
            max_size=50000,
            overflow_policy=OverflowPolicy.DROP_OLDEST,
            max_age_seconds=600,  # 10 minutes
            **kwargs,
        )
        self.max_retries = max_retries

    def append_with_retry(self, event: Event, retry_count: int = 0) -> bool:
        """
        Add event with retry counter.

        Args:
            event: Event to add
            retry_count: Current retry count

        Returns:
            True if added, False if rejected
        """
        return self.append(
            event=event, retry_count=retry_count, metadata={"last_retry_at": None}
        )

    def increment_retry(self, timestamp) -> Optional[EventMetadata]:
        """
        Increment retry count for an event.

        Args:
            timestamp: Event timestamp (datetime or ISO string)

        Returns:
            EventMetadata if retry is allowed, None if max retries exceeded (event removed)
        """
        with self._lock:
            meta = self.get_by_timestamp(timestamp)
            if not meta:
                return None

            meta.retry_count += 1
            meta.metadata["last_retry_at"] = datetime.now()

            if meta.retry_count >= self.max_retries:
                # Exceeded max retries - remove event
                self.pop_by_timestamp(timestamp)
                error(
                    f"{self.name}: Event {timestamp} dropped after {self.max_retries} retries",
                    message_logger=self._message_logger,
                )
                return None

            return meta

    def group_by_destination(self) -> dict[tuple, list[EventMetadata]]:
        """
        Group events by (destination_address, destination_port).

        Used for creating cumulative events.

        Returns:
            Dictionary mapping (address, port) to list of EventMetadata
        """
        with self._lock:
            groups = {}
            for meta in self._pool.values():
                key = (meta.event.destination_address, meta.event.destination_port)
                if key not in groups:
                    groups[key] = []
                groups[key].append(meta)
            return groups

    def pop_batch_grouped(
        self, batch_size: int = 100
    ) -> dict[tuple, list[EventMetadata]]:
        """
        Get batch of events grouped by destination.

        Args:
            batch_size: Maximum number of events to retrieve

        Returns:
            Dictionary mapping (address, port) to list of EventMetadata
        """
        with self._lock:
            # Get batch of oldest events
            batch = []
            for _ in range(min(batch_size, len(self._pool))):
                meta = self.pop_oldest()
                if meta:
                    batch.append(meta)
                else:
                    break

            # Group by destination
            groups = {}
            for meta in batch:
                key = (meta.event.destination_address, meta.event.destination_port)
                if key not in groups:
                    groups[key] = []
                groups[key].append(meta)

            return groups
