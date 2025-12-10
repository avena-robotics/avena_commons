# Migration Guide: EventListener → EventPool

This document describes all changes needed to integrate EventPool into EventListener.

## Step 1: Remove old EventPool class (lines 48-70)

**DELETE:**
```python
class EventPool:
    def __init__(self, max_size: int):
        self.max_size = max_size
        self.pool: dict[str, Event] = {}
        self._lock = threading.RLock()  # Reentrant lock

    def append(self, event: Event) -> bool:
        with self._lock:
            if len(self.pool) < self.max_size:
                self.pool[event.timestamp.isoformat()] = event
                return True
            return False

    def extend(self, events: list[Event]) -> int:
        with self._lock:
            added = 0
            for event in events:
                if self.append(event):  # Teraz RLock obsłuży re-entry
                    added += 1
                else:
                    break
            return added
```

## Step 2: Add import

**ADD at line 26 (after `from .event import Event, Result`):**
```python
from .event_pool import (
    EventMetadata,
    EventPool,
    IncomingEventPool,
    OverflowPolicy,
    ProcessingEventPool,
    SendingEventPool,
)
```

## Step 3: Replace queue declarations in EventListener class

**REPLACE lines 81-85:**
```python
# OLD:
__incoming_events: list[Event] = []
_processing_events_dict: dict = {}  # Structure: {timestamp: event}
__events_to_send: list[dict] = []  # Lista słowników {event: Event, retry_count: int}
```

**WITH:**
```python
# NEW: EventPool-based queues (initialized in __init__)
_incoming_pool: IncomingEventPool = None
_processing_pool: ProcessingEventPool = None
_sending_pool: SendingEventPool = None
```

## Step 4: Remove old locks (lines 87-91)

**DELETE:**
```python
__lock_for_general_purpose = threading.Lock()
__lock_for_incoming_events = threading.Lock()
__lock_for_processing_events = threading.Lock()
__lock_for_events_to_send = threading.Lock()
__lock_for_state_data = threading.Lock()
```

**KEEP only:**
```python
__lock_for_state_data = threading.Lock()  # Still needed for _latest_state_data
```

## Step 5: Initialize EventPools in __init__

**ADD after line 181 (after `self.__discovery_neighbours = discovery_neighbours`):**
```python
# Initialize EventPool-based queues
self._incoming_pool = IncomingEventPool(
    max_size=10000,
    max_age_seconds=300,  # 5 minutes
    message_logger=message_logger,
)
self._processing_pool = ProcessingEventPool(
    max_timeout=60.0,
    message_logger=message_logger,
)
self._sending_pool = SendingEventPool(
    max_retries=3,  # Changed from 100000000!
    message_logger=message_logger,
)

info(
    f"Initialized event pools: incoming(10k), processing(unlimited), sending(50k)",
    message_logger=message_logger,
)
```

## Step 6: Remove old queue initialization (line 169)

**DELETE:**
```python
self.__incoming_events = []
```

## Step 7: Update size methods (lines 277-284)

**REPLACE:**
```python
# OLD:
def size_of_incomming_events_queue(self):
    return len(self.__incoming_events)

def size_of_processing_events_queue(self):
    return len(self._processing_events_dict)

def size_of_events_to_send_queue(self):
    return len(self.__events_to_send)
```

**WITH:**
```python
# NEW:
def size_of_incomming_events_queue(self) -> int:
    """Returns size of incoming events queue"""
    return len(self._incoming_pool)

def size_of_processing_events_queue(self) -> int:
    """Returns size of processing events queue"""
    return len(self._processing_pool)

def size_of_events_to_send_queue(self) -> int:
    """Returns size of sending events queue"""
    return len(self._sending_pool)

def get_queue_stats(self) -> dict:
    """Returns statistics for all event queues"""
    return {
        "incoming": self._incoming_pool.get_stats(),
        "processing": self._processing_pool.get_stats(),
        "sending": self._sending_pool.get_stats(),
    }
```

## Step 8: Remove context managers (lines 295-335)

**DELETE (no longer needed - EventPool has internal locking):**
```python
@contextmanager
def __atomic(self):
    """Context manager for thread-safe queue operations"""
    with self.__lock_for_general_purpose:
        yield

@contextmanager
def __atomic_operation_for_events_to_send(self):
    # ...

@contextmanager
def __atomic_operation_for_incoming_events(self):
    # ...

@contextmanager
def __atomic_operation_for_processing_events(self):
    # ...
```

## Step 9: Update __save_state() method (lines 369-433)

**REPLACE the queue serialization part:**
```python
# OLD (lines 398-420):
# Flatten processing_events_dict to a list of events
processing_events_list = []
for event in self._processing_events_dict.values():
    processing_events_list.append(event.to_dict())

queues_data = {
    "incoming_events": [
        event.to_dict() for event in self.__incoming_events
    ],
    "processing_events": processing_events_list,
    "events_to_send": [
        event_data["event"].to_dict()
        for event_data in self.__events_to_send
    ],
    "state": serialized_state,
}
```

**WITH:**
```python
# NEW:
queues_data = {
    "incoming_events": [
        meta.event.to_dict() for meta in self._incoming_pool
    ],
    "processing_events": [
        meta.event.to_dict() for meta in self._processing_pool
    ],
    "events_to_send": [
        {
            "event": meta.event.to_dict(),
            "retry_count": meta.retry_count,
        }
        for meta in self._sending_pool
    ],
    "state": serialized_state,
}
```

**ALSO UPDATE the empty check (line 377):**
```python
# OLD:
if not (
    self.__incoming_events
    or self.__events_to_send
    or self._state
    or self._processing_events_dict
):

# NEW:
if not (
    len(self._incoming_pool) > 0
    or len(self._sending_pool) > 0
    or self._state
    or len(self._processing_pool) > 0
):
```

## Step 10: Update __load_state() method (lines 435-500)

**REPLACE:**
```python
# OLD (lines 449-473):
# Konwersja danych na obiekty Event
for event_data in json_data.get("incoming_events", []):
    event = Event(**event_data)
    self.__incoming_events.append(event)

# Rekonstrukcja processing_events_dict
for event_data in json_data.get("processing_events", []):
    event = Event(**event_data)
    event_timestamp = event.timestamp.isoformat()
    self._processing_events_dict[event_timestamp] = event

# Rekonstrukcja events_to_send
for event_data in json_data.get("events_to_send", []):
    if isinstance(event_data, dict) and "event" in event_data:
        # Nowy format z retry_count
        event = Event(**event_data["event"])
        retry_count = event_data.get("retry_count", 0)
        self.__events_to_send.append({
            "event": event,
            "retry_count": retry_count,
        })
    else:
        # Stary format - tylko event
        event = Event(**event_data)
        self.__events_to_send.append({"event": event, "retry_count": 0})
```

**WITH:**
```python
# NEW:
# Restore incoming events
for event_data in json_data.get("incoming_events", []):
    event = Event(**event_data)
    self._incoming_pool.append(event)

# Restore processing events
for event_data in json_data.get("processing_events", []):
    event = Event(**event_data)
    self._processing_pool.append(event)

# Restore events to send with retry counts
for event_data in json_data.get("events_to_send", []):
    if isinstance(event_data, dict) and "event" in event_data:
        # New format with retry_count
        event = Event(**event_data["event"])
        retry_count = event_data.get("retry_count", 0)
        self._sending_pool.append_with_retry(event, retry_count)
    else:
        # Old format - just event
        event = Event(**event_data)
        self._sending_pool.append_with_retry(event, 0)
```

## Step 11: Update __analyze_queues() (lines 983-1022)

**REPLACE lines 1005-1011:**
```python
# OLD:
with self.__atomic_operation_for_incoming_events():
    if len(self.__incoming_events) > 0:
        debug(
            f"Analyzing incoming events queue. size={len(self.__incoming_events)}",
            message_logger=self._message_logger,
        )
        await self.__analyze_incoming_events()
```

**WITH:**
```python
# NEW:
if len(self._incoming_pool) > 0:
    debug(
        f"Analyzing incoming events queue. size={len(self._incoming_pool)}",
        message_logger=self._message_logger,
    )
    await self.__analyze_incoming_events()
```

## Step 12: Update __analyze_incoming_events() (lines 1025-1141)

**REPLACE lines 1032-1033:**
```python
# OLD:
events_to_process = self.__incoming_events.copy()
self.__incoming_events.clear()
```

**WITH:**
```python
# NEW - batch processing:
batch = self._incoming_pool.pop_batch(batch_size=100)
events_to_process = [meta.event for meta in batch]
```

**REPLACE line 1141:**
```python
# OLD:
self.__incoming_events.extend(new_queue)
```

**WITH:**
```python
# NEW:
for event in new_queue:
    self._incoming_pool.append(event)
```

## Step 13: Update __event_handler() (lines 1199-1231)

**REPLACE lines 1213-1228:**
```python
# OLD:
with self.__atomic_operation_for_incoming_events():
    if event.event_type == "cumulative":
        for event_data in event.data["events"]:
            unpacked_event = Event(**event_data)
            self.__incoming_events.append(unpacked_event)
        debug(
            f"Unpacked cumulative event into {len(event.data['events'])} events",
            message_logger=self._message_logger,
        )
    else:
        self.__incoming_events.append(event)
        if not event.is_system_event:
            debug(
                f"Added event to incomming events queue: {event}",
                message_logger=self._message_logger,
            )
```

**WITH:**
```python
# NEW:
if event.event_type == "cumulative":
    for event_data in event.data["events"]:
        unpacked_event = Event(**event_data)
        self._incoming_pool.append(unpacked_event)
    debug(
        f"Unpacked cumulative event into {len(event.data['events'])} events",
        message_logger=self._message_logger,
    )
else:
    self._incoming_pool.append(event)
    if not event.is_system_event:
        debug(
            f"Added event to incoming events queue: {event}",
            message_logger=self._message_logger,
        )
```

## Step 14: Update __send_event_loop() (lines 1357-1558)

This is a major refactoring. **REPLACE lines 1387-1459:**

```python
# OLD:
with self.__atomic_operation_for_events_to_send():
    local_queue = self.__events_to_send.copy()
    self.__events_to_send.clear()

if local_queue:
    # ... long cumulative grouping logic ...
```

**WITH:**
```python
# NEW:
groups = self._sending_pool.pop_batch_grouped(batch_size=100)

if groups:
    # Create send tasks
    send_tasks = []

    for (address, port), meta_list in groups.items():
        if len(meta_list) == 1:
            # Single event - send directly
            send_tasks.append(
                self._send_single_event(meta_list[0])
            )
        else:
            # Multiple events to same destination - create cumulative
            first_meta = meta_list[0]
            first_event = first_meta.event

            cumulative_event = Event(
                source=first_event.source,
                source_address=first_event.source_address,
                source_port=first_event.source_port,
                destination=first_event.destination,
                destination_address=first_event.destination_address,
                destination_port=first_event.destination_port,
                event_type="cumulative",
                payload=sum(m.event.payload for m in meta_list),
                data={"events": [m.event.to_dict() for m in meta_list]},
            )

            send_tasks.append(
                self._send_cumulative_event(cumulative_event, meta_list)
            )
```

**REPLACE lines 1465-1530 (send_single_event function):**

```python
# OLD:
async def send_single_event(event_data):
    event = event_data["event"]
    retry_count = event_data["retry_count"]

    if retry_count >= self.__retry_count:
        # ... drop event ...

    # ... send logic ...
```

**WITH:**
```python
async def send_single_event(meta: EventMetadata):
    """Send a single event (not cumulative)"""
    event = meta.event

    try:
        url = f"http://{event.destination_address}:{event.destination_port}{event.destination_endpoint}"

        with self._event_send_debug(event):
            async with session.post(
                url,
                json=event.to_dict(),
                timeout=aiohttp.ClientTimeout(total=0.5),  # 500ms instead of 25ms!
            ) as response:
                if response.status == 200:
                    self.__sended_events += 1
                    return None  # Success

        # Non-200 response - retry
        return meta

    except asyncio.TimeoutError:
        error(
            f"Timeout sending event to {url}",
            message_logger=self._message_logger,
        )
        return meta  # Return for retry
    except Exception as e:
        error(
            f"Error sending event: {e}",
            message_logger=self._message_logger,
        )
        return meta  # Return for retry

async def send_cumulative_event(cumulative: Event, original_metas: list[EventMetadata]):
    """Send cumulative event, return original metas if failed"""
    event = cumulative

    try:
        url = f"http://{event.destination_address}:{event.destination_port}{event.destination_endpoint}"

        with self._event_send_debug(event):
            async with session.post(
                url,
                json=event.to_dict(),
                timeout=aiohttp.ClientTimeout(total=0.5),
            ) as response:
                if response.status == 200:
                    self.__sended_events += len(original_metas)
                    return None  # Success

        # Failed - return original events for individual retry
        return original_metas

    except (asyncio.TimeoutError, Exception) as e:
        error(
            f"Error sending cumulative event: {e}",
            message_logger=self._message_logger,
        )
        return original_metas  # Return originals for retry
```

**REPLACE lines 1531-1549 (result handling):**

```python
# OLD:
# Create and run all tasks in parallel
tasks = [send_single_event(data) for data in local_queue]
results = await asyncio.gather(*tasks, return_exceptions=True)

# Collect failed events
failed_events = []
for r in results:
    if isinstance(r, (dict, list)):  # means failed event(s)
        if isinstance(r, list):  # original events from failed cumulative
            failed_events.extend(r)
        else:  # single failed event
            failed_events.append(r)

# If there are failed events, add them back
if failed_events:
    with self.__atomic_operation_for_events_to_send():
        self.__events_to_send.extend(failed_events)
```

**WITH:**
```python
# NEW:
# Parallel send
start_time = time.perf_counter()
results = await asyncio.gather(*send_tasks, return_exceptions=True)

# Handle retries
for result in results:
    if result is None:
        # Success - nothing to do
        continue
    elif isinstance(result, list):
        # Failed cumulative - retry original events individually
        for meta in result:
            if meta.retry_count < self._sending_pool.max_retries:
                self._sending_pool.append_with_retry(
                    meta.event,
                    meta.retry_count + 1
                )
    elif isinstance(result, EventMetadata):
        # Failed single event - retry
        if result.retry_count < self._sending_pool.max_retries:
            self._sending_pool.append_with_retry(
                result.event,
                result.retry_count + 1
            )

total_elapsed = (time.perf_counter() - start_time) * 1000
debug(
    f"Send time: {total_elapsed:.4f} ms for {sum(len(g) for g in groups.values())} events",
    message_logger=self._message_logger,
)
```

## Step 15: Update _add_to_processing() (lines 1899-1926)

**REPLACE:**
```python
# OLD:
def _add_to_processing(self, event: Event) -> bool:
    try:
        event.is_processing = True
        with self.__atomic_operation_for_processing_events():
            event_timestamp = event.timestamp.isoformat(sep=" ")
            self._processing_events_dict[event_timestamp] = event
            self._event_add_to_processing_debug(event)
        return True
    # ... error handling ...
```

**WITH:**
```python
# NEW:
def _add_to_processing(self, event: Event) -> bool:
    """Add event to processing queue"""
    try:
        event.is_processing = True
        self._processing_pool.append(event)
        self._event_add_to_processing_debug(event)
        return True
    except Exception as e:
        error(
            f"_add_to_processing: Error adding event to processing queue: {e}",
            message_logger=self._message_logger,
        )
        return False
```

## Step 16: Update _find_and_remove_processing_event() (lines 1928-1955)

**REPLACE:**
```python
# OLD:
def _find_and_remove_processing_event(self, event: Event) -> Event | None:
    try:
        timestamp_key = event.timestamp.isoformat(sep=" ")

        debug(
            f"Searching for event for remove in processing queue: id={event.id} event_type={event.event_type} timestamp={timestamp_key}",
            message_logger=self._message_logger,
        )

        with self.__atomic_operation_for_processing_events():
            event = self._processing_events_dict[timestamp_key]
            del self._processing_events_dict[timestamp_key]
            self._event_find_and_remove_debug(event)
            return event
    # ... error handling ...
```

**WITH:**
```python
# NEW:
def _find_and_remove_processing_event(self, event: Event) -> Event | None:
    """Find and remove event from processing queue"""
    try:
        debug(
            f"Searching for event to remove from processing queue: id={event.id} event_type={event.event_type} timestamp={event.timestamp}",
            message_logger=self._message_logger,
        )

        meta = self._processing_pool.pop_by_timestamp(event.timestamp)
        if meta:
            self._event_find_and_remove_debug(meta.event)
            return meta.event
        return None

    except Exception as e:
        error(
            f"Exception: _find_and_remove_processing_event: {e}",
            message_logger=self._message_logger,
        )
        return None
```

## Step 17: Update _event() method (lines 1727-1781)

**REPLACE lines 1772-1780:**
```python
# OLD:
try:
    with self.__atomic_operation_for_events_to_send():
        self.__events_to_send.append({"event": event, "retry_count": 0})
except TimeoutError as e:
    error(f"__event: {e}", message_logger=self._message_logger)
    return None
except Exception as e:
    error(f"__event: {e}", message_logger=self._message_logger)
    return None
```

**WITH:**
```python
# NEW:
try:
    self._sending_pool.append_with_retry(event, retry_count=0)
except Exception as e:
    error(f"_event: {e}", message_logger=self._message_logger)
    return None
```

## Step 18: Update _reply() method (lines 1787-1826)

**REPLACE lines 1816-1826:**
```python
# OLD:
try:
    with self.__atomic_operation_for_events_to_send():
        self.__events_to_send.append({"event": new_event, "retry_count": 0})
        if not new_event.is_system_event:
            debug(
                f"Added event to send queue: {new_event}",
                message_logger=self._message_logger,
            )
except TimeoutError as e:
    error(f"_reply: {e}", message_logger=self._message_logger)
    raise
```

**WITH:**
```python
# NEW:
try:
    self._sending_pool.append_with_retry(new_event, retry_count=0)
    if not new_event.is_system_event:
        debug(
            f"Added event to send queue: {new_event}",
            message_logger=self._message_logger,
        )
except Exception as e:
    error(f"_reply: {e}", message_logger=self._message_logger)
    raise
```

## Summary of Changes

### Removed:
- Old `EventPool` class (lines 48-70)
- 5 threading locks (replaced by EventPool internal locks)
- 4 context managers (`__atomic_*`)
- Manual queue management code
- Complex cumulative event unpacking logic

### Added:
- Import from `event_pool` module
- 3 EventPool instances with proper configuration
- `get_queue_stats()` method
- Type hints for queue size methods
- Better error handling in send logic
- Configurable timeouts (500ms instead of 25ms)
- Reasonable max_retries (3 instead of 100M)

### Benefits:
- **~200 lines of code removed**
- **No deadlock risk** (RLock handles recursion)
- **Better performance** (O(1) lookups)
- **Automatic cleanup** (old events removed)
- **Built-in stats** (monitoring ready)
- **Type safety** (EventMetadata vs dict)
- **Consistent API** (all queues behave the same)

## Testing Checklist

After migration, test:

- [ ] Incoming events are received and processed
- [ ] Events are added to processing queue correctly
- [ ] Events are sent successfully (single and cumulative)
- [ ] Retry logic works (max 3 retries)
- [ ] State save/load preserves queues
- [ ] Queue stats are accurate
- [ ] No deadlocks under load
- [ ] Old events are cleaned up automatically
- [ ] Overflow policy works (oldest dropped when full)
- [ ] FSM commands work in all states
