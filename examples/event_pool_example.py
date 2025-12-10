"""
Example usage of EventPool module.

This example demonstrates how to use EventPool for managing event queues
with different overflow policies, retry logic, and automatic cleanup.
"""

import time
from datetime import datetime, timedelta

from avena_commons.event_listener.event import Event
from avena_commons.event_listener.event_pool import (
    IncomingEventPool,
    OverflowPolicy,
    ProcessingEventPool,
    SendingEventPool,
)


def create_sample_event(event_type: str, destination_port: int = 8001) -> Event:
    """Create a sample event for testing"""
    return Event(
        source="example_source",
        source_address="127.0.0.1",
        source_port=8000,
        destination="example_destination",
        destination_address="127.0.0.1",
        destination_port=destination_port,
        event_type=event_type,
        data={"example": "data", "timestamp": datetime.now().isoformat()},
    )


def example_incoming_pool():
    """Example: Using IncomingEventPool for receiving events"""
    print("\n=== IncomingEventPool Example ===")

    # Create pool with max size and auto-cleanup
    pool = IncomingEventPool(max_size=5, max_age_seconds=10)
    print(f"Created pool: {pool}")

    # Add events
    for i in range(7):
        event = create_sample_event(f"incoming_event_{i}")
        result = pool.append(event)
        print(f"Added event {i}: {result}")

    print(f"Pool size: {len(pool)} (max: 5, overflow policy: DROP_OLDEST)")
    print(f"Stats: {pool.get_stats()}")

    # Process events in batches
    print("\nProcessing batch of 3 events:")
    batch = pool.pop_batch(batch_size=3)
    for meta in batch:
        print(f"  - Processing: {meta.event.event_type}")

    print(f"Remaining in pool: {len(pool)}")


def example_processing_pool():
    """Example: Using ProcessingEventPool with timeout tracking"""
    print("\n=== ProcessingEventPool Example ===")

    # Create pool with timeout tracking
    pool = ProcessingEventPool(max_timeout=2.0)
    print(f"Created pool: {pool}")

    # Add events with different timeouts
    event1 = create_sample_event("quick_task")
    event1.maximum_processing_time = 0.5  # 500ms timeout

    event2 = create_sample_event("slow_task")
    event2.maximum_processing_time = 2.0  # 2s timeout

    pool.append(event1)
    pool.append(event2)
    print(f"Added 2 events with different timeouts")

    # Simulate processing time
    print("Waiting 1 second...")
    time.sleep(1.0)

    # Check for timed-out events
    timed_out = pool.get_timed_out_events()
    print(f"Timed out events: {len(timed_out)}")
    for meta in timed_out:
        print(f"  - {meta.event.event_type} (age: {meta.age_seconds:.2f}s)")

    # Cleanup timed-out events
    removed = pool.cleanup_timed_out()
    print(f"Cleaned up {removed} timed-out events")
    print(f"Remaining in pool: {len(pool)}")


def example_sending_pool():
    """Example: Using SendingEventPool with retry logic"""
    print("\n=== SendingEventPool Example ===")

    # Create pool with max retries
    pool = SendingEventPool(max_retries=3)
    print(f"Created pool: {pool}")

    # Add events to different destinations
    for i in range(5):
        port = 8001 if i < 3 else 8002
        event = create_sample_event(f"outgoing_event_{i}", destination_port=port)
        pool.append_with_retry(event, retry_count=0)

    print(f"Added 5 events (3 to port 8001, 2 to port 8002)")

    # Group by destination (for cumulative sending)
    groups = pool.group_by_destination()
    print(f"\nGrouped by destination: {len(groups)} groups")
    for (address, port), meta_list in groups.items():
        print(f"  - {address}:{port} -> {len(meta_list)} events")

    # Simulate sending with retry
    print("\nSimulating send failures and retries:")
    event = pool.peek_oldest().event
    for retry in range(4):
        print(f"  Attempt {retry + 1}:")
        meta = pool.increment_retry(event.timestamp)
        if meta is None:
            print(f"    Event dropped (exceeded max_retries={pool.max_retries})")
            break
        else:
            print(f"    Retry count: {meta.retry_count}")

    print(f"\nRemaining in pool: {len(pool)}")


def example_batch_processing():
    """Example: Batch processing with grouped sending"""
    print("\n=== Batch Processing Example ===")

    pool = SendingEventPool()

    # Add events with staggered timestamps
    for i in range(10):
        port = 8001 if i % 2 == 0 else 8002
        event = create_sample_event(f"batch_event_{i}", destination_port=port)
        # Manually set different timestamps
        event.timestamp = datetime.now() + timedelta(seconds=i)
        pool.append(event)

    print(f"Added 10 events")

    # Pop batch grouped by destination
    print("\nPopping batch of 6 events, grouped by destination:")
    groups = pool.pop_batch_grouped(batch_size=6)

    for (address, port), meta_list in groups.items():
        print(f"\n  Destination {address}:{port}:")
        for meta in meta_list:
            print(f"    - {meta.event.event_type}")

    print(f"\nRemaining in pool: {len(pool)}")


def example_overflow_policies():
    """Example: Different overflow policies"""
    print("\n=== Overflow Policies Example ===")

    from avena_commons.event_listener.event_pool import EventPool

    # Policy 1: DROP_OLDEST
    print("\n1. DROP_OLDEST policy (default):")
    pool1 = EventPool(
        name="drop_oldest", max_size=3, overflow_policy=OverflowPolicy.DROP_OLDEST
    )
    for i in range(5):
        pool1.append(create_sample_event(f"event_{i}"))
    print(f"   Added 5 events, pool size: {len(pool1)} (keeps newest 3)")
    print(f"   Dropped: {pool1.get_stats()['total_dropped']}")

    # Policy 2: DROP_NEWEST
    print("\n2. DROP_NEWEST policy:")
    pool2 = EventPool(
        name="drop_newest", max_size=3, overflow_policy=OverflowPolicy.DROP_NEWEST
    )
    for i in range(5):
        result = pool2.append(create_sample_event(f"event_{i}"))
        if not result:
            print(f"   Event {i} rejected (pool full)")
    print(f"   Pool size: {len(pool2)} (keeps oldest 3)")

    # Policy 3: UNLIMITED
    print("\n3. UNLIMITED policy:")
    pool3 = EventPool(
        name="unlimited",
        max_size=3,  # Ignored
        overflow_policy=OverflowPolicy.UNLIMITED,
    )
    for i in range(5):
        pool3.append(create_sample_event(f"event_{i}"))
    print(f"   Added 5 events, pool size: {len(pool3)} (ignores max_size)")


def example_statistics():
    """Example: Pool statistics and monitoring"""
    print("\n=== Statistics Example ===")

    pool = IncomingEventPool(max_size=100)

    # Add and process some events
    for i in range(20):
        event = create_sample_event(f"stat_event_{i}")
        pool.append(event)

    # Remove some
    for _ in range(5):
        pool.pop_oldest()

    # Get detailed stats
    stats = pool.get_stats()
    print("\nPool statistics:")
    print(f"  Name: {stats['name']}")
    print(f"  Current size: {stats['size']}")
    print(f"  Max size: {stats['max_size']}")
    print(f"  Overflow policy: {stats['overflow_policy']}")
    print(f"  Total added: {stats['total_added']}")
    print(f"  Total removed: {stats['total_removed']}")
    print(f"  Total dropped: {stats['total_dropped']}")
    print(f"  Average age: {stats['avg_age_seconds']:.3f}s")
    print(f"  Oldest event: {stats['oldest_event']}")
    print(f"  Newest event: {stats['newest_event']}")


def main():
    """Run all examples"""
    print("=" * 60)
    print("EventPool Usage Examples")
    print("=" * 60)

    example_incoming_pool()
    example_processing_pool()
    example_sending_pool()
    example_batch_processing()
    example_overflow_policies()
    example_statistics()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
