"""
# 🎯 Event Listener Module - Event-Driven Architecture

The `event_listener` module provides a comprehensive event-driven system for handling asynchronous operations and real-time communication between system components in industrial automation and robotics applications.

## 📦 Available Imports

### Core Classes (from .event_listener)
- **`Event`**: Main event data structure with priority, timestamps, and networking
- **`Result`**: Standardized result format for operation outcomes and error tracking

### Main Engine (from .event_listener)
- **`EventListener`**: FastAPI-based HTTP server for event processing
- **`EventListenerState`**: State enumeration (IDLE, INITIALIZED, RUNNING, ERROR)

### Type Definitions (from .types submodule)
- **`types`**: Complete submodule containing:
  - `IoAction`, `IoSignal` - Hardware I/O operations
  - `KdsAction` - Kiosk display system operations
  - `SupervisorMoveAction` - Multi-waypoint robotic movement
  - `SupervisorGripperAction` - Gripper control operations
  - `SupervisorPumpAction` - Gripper system management
  - `Waypoint`, `Path` - Navigation data structures

## 🔧 Key Components Overview

### EventListener - Main Event Processing Engine
- **FastAPI HTTP Server**: Receives events via REST API calls on configurable host/port
- **Asynchronous Processing**: Thread-safe event handling with concurrent processing
- **State Management**: Tracks system state using EventListenerState enum
- **Graceful Shutdown**: Proper cleanup and resource management
- **Persistence**: Automatic saving/loading of event queues and configuration

### Event - Event Data Structure
- **Source/Destination**: Network addressing with host/port information
- **Timestamps**: Automatic timestamping for tracking and debugging
- **Data Payload**: Flexible dictionary for event-specific information
- **Result Tracking**: Result object for operation outcomes
- **Processing Flags**: Thread-safe processing state management

### Result - Operation Outcome Tracking
- **Status Reporting**: Success/failure/error status with standardized format
- **Error Details**: Error codes and descriptive messages for debugging
- **Flexible Structure**: Optional fields for various result types

## 🚀 Basic Usage Example

```python
from avena_commons.event_listener import (
    EventListener, EventListenerState,  # Main engine
    Event, Result,                      # Core data structures
    types                              # Event type definitions
)

# Create and start event listener
listener = EventListener(name="robot_controller", port=8000)
listener.start()

# Create an event
event = Event(
    source="temperature_sensor",
    source_address="192.168.1.100",
    source_port=5001,
    destination="control_system",
    destination_address="192.168.1.200",
    destination_port=8000,
    event_type="sensor_reading",
    data={
        "temperature": 25.5,
        "humidity": 60.2,
        "sensor_id": "TEMP_01",
        "timestamp": "2025-06-10T10:30:00Z"
    }
)

# Check listener state
if listener.get_state() == EventListenerState.RUNNING:
    # Send event via HTTP POST to http://192.168.1.200:8000/event
    pass
```

## ⚙️ Advanced Features

- **Discovery Mode**: Automatic neighbor discovery for distributed systems
- **Retry Logic**: Configurable retry attempts for failed operations
- **Custom Frequencies**: Adjustable processing frequencies for different operations
- **Logging Integration**: Built-in logging with configurable message loggers
- **Configuration Management**: JSON-based configuration persistence
- **Thread Safety**: All operations designed for concurrent access

## 🎯 Use Cases

- **Industrial Automation**: Process control and monitoring systems
- **Robotics**: Multi-axis robot coordination and control
- **Sensor Networks**: Distributed sensor data collection and processing
- **Manufacturing**: Production line automation and quality control
- **System Integration**: Inter-service communication in microservice architectures
- **Real-time Monitoring**: Live system status and alert management

This module forms the communication backbone for complex automation systems, enabling reliable, prioritized, and traceable event processing across distributed components.
"""

# 📥 Explicit imports from submodules
from . import types  # Complete types submodule
from .event import Event, Result  # Core event structures
from .event_listener import EventListener, EventListenerState  # Main processing engine

# 🎯 Define public API - Available for import
__all__ = [
    # Core event data structures (from .event)
    "Event",  # Main event class with networking and priority
    "Result",  # Standardized operation result format
    # Main processing engine (from .event_listener)
    "EventListener",  # FastAPI-based HTTP server for events
    "EventListenerState",  # State enum: IDLE, INITIALIZED, RUNNING, ERROR
    # Specialized event types (from .types submodule)
    "types",  # Complete submodule containing IoAction, KdsAction, etc.
]
