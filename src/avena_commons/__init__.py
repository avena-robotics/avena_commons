"""
# Avena Commons Library - Comprehensive Module Documentation

The `avena_commons` library is a comprehensive collection of utilities and modules designed for industrial automation, robotics, and system monitoring applications. This library provides a robust foundation for building complex control systems with real-time communication, configuration management, and monitoring capabilities.

## Module Overview

### 🎯 event_listener - Event-Driven Architecture
**Purpose**: Provides a comprehensive event-driven system for handling asynchronous operations and communication.

**Key Components**:
- `EventListener`: Main event processing engine
  - FastAPI-based HTTP server for event reception
  - Asynchronous event processing with priority queues
  - State management with graceful shutdown handling
  - Built-in logging and error management
- `Event`: Event data structure with priority and result handling
- `Result`: Standardized result format for event processing
- **Event Types**:
  - `IoAction`/`IoSignal`: I/O operations and signal handling
  - `KdsAction`: KDS (Kinematic Drive System) operations
  - `SupervisorMoveAction`: Robotic movement commands with waypoint navigation
  - `SupervisorGripperAction`: Gripper control operations
  - `SupervisorPumpAction`: Pump control operations

**How it works**: The event listener runs a FastAPI server that accepts HTTP requests containing event data. Events are queued by priority and processed asynchronously. The system supports complex robotic operations through specialized action types, each with their own parameter validation and execution logic.

**Use cases**: Robotic control systems, automated manufacturing, sensor data processing, system orchestration, real-time command execution.

---

### 💾 io - Input/Output Management
**Purpose**: Comprehensive I/O management system supporting multiple communication protocols and device types.

**Key Components**:
- **Bus Protocols**:
  - `EtherCAT`: Industrial Ethernet protocol support
  - `ModbusRTU`: Serial Modbus communication
  - `ModbusTCP`: TCP/IP Modbus communication
- **Device Categories**:
  - **I/O Devices**: Digital/analog input/output modules (R3, P7674, MA01, etc.)
  - **Motor Drivers**: Servo and stepper motor controllers (TLC57R24V08, DSR)
  - **Sensors**: Environmental and measurement sensors (URM14, WJ150, AS228P, etc.)
- `IO_server`: Event-driven I/O server for device management
- `VirtualDevice`: Simulation and testing support

**How it works**: The I/O system provides abstracted interfaces for various industrial communication protocols. Device drivers implement standardized interfaces while handling protocol-specific details. The IO_server coordinates device operations and provides centralized management.

**Use cases**: Industrial automation, sensor networks, motor control, data acquisition, device simulation, protocol bridging.

---

### 📝 config - Configuration Management
**Purpose**: Provides centralized configuration management for applications and controllers.

**Key Components**:
- `Config`: Base configuration class for reading/writing configuration files
  - Supports automatic file parsing and validation
  - Read-only and read-write modes
  - Automatic content cleanup and formatting
- `ControllerConfig`: Specialized configuration for controller applications
  - Extends base Config with controller-specific settings
  - Handles complex parameter validation and type conversion

**How it works**: The config module uses file-based configuration storage with automatic parsing. It provides a clean interface for managing application settings while ensuring data integrity through validation and controlled access patterns.

**Use cases**: Application settings, controller parameters, system configuration, environment-specific settings.

---

### 🔗 connection - Inter-Process Communication
**Purpose**: Provides high-performance inter-process communication using shared memory and semaphores.

**Key Components**:
- `AvenaComm`: Main communication class utilizing POSIX shared memory
  - Synchronized access using semaphores with configurable timeouts
  - Support for binary and pickle-based data serialization
  - Automatic buffer management and error handling
  - Thread-safe operations with lock acquisition tracking

**How it works**: Uses POSIX shared memory segments synchronized with named semaphores. Data is serialized (optionally with pickle) into memory buffers that multiple processes can access safely. Semaphores ensure atomic read/write operations and prevent race conditions.

**Use cases**: Real-time data sharing between processes, high-frequency sensor data exchange, control system communication, multi-process synchronization.

---

### 🔄 sequence - State Machine Management
**Purpose**: Provides robust state machine implementation for managing complex sequential operations.

**Key Components**:
- `Sequence`: Main sequence management class
  - Step-by-step execution with state tracking
  - Retry logic and error handling
  - Parameter passing between steps
- `SequenceStatus`: Complete sequence state information
- `SequenceStepStatus`: Individual step state tracking
- `StepState`: Enumeration of possible step states (PREPARE, EXECUTE, SUCCESS, etc.)

**How it works**: Sequences are defined as state machines where each step has a defined state (prepare, execute, success, error, etc.). The system tracks execution progress, handles retries, and manages data flow between steps. Steps can be conditional and support complex branching logic.

**Use cases**: Manufacturing processes, robotic task sequences, system initialization, multi-step operations, process automation.

---

### 📊 system_dashboard - Web-Based Monitoring
**Purpose**: Real-time web-based system monitoring and management interface.

**Key Components**:
- **Flask Web Application**: Multi-page dashboard with real-time updates
- **System Monitoring**: CPU, memory, disk usage with real-time charts
- **Process Monitoring**: Per-core CPU usage and top processes
- **Authentication**: Login/logout functionality with session management
- **AJAX Updates**: Dynamic content loading without page refresh
- **Responsive Design**: Mobile-friendly interface with modern styling

**How it works**: A Flask-based web server provides HTTP endpoints for both static pages and JSON data. JavaScript handles real-time updates via AJAX calls. Chart.js provides interactive visualizations. The system continuously monitors hardware resources and provides alerts when thresholds are exceeded.

**Use cases**: System administration, performance monitoring, remote diagnostics, operational dashboards, alert management.

---

### 🛠️ util - Utility Functions
**Purpose**: Comprehensive collection of utility functions and classes for common operations.

**Key Components**:
- **Mathematical Utilities**: Quaternion operations, matrix transformations, interpolation
- **Control Systems**: PID controllers, filters, smoothing algorithms
- **Logging System**: Multi-level logging with color support and file output
- **Performance Monitoring**:
  - `ControlLoop`: Precise timing control for real-time systems
  - `MeasureTime`: Code execution timing and profiling
  - `Monitor`: System resource monitoring
- **Data Structures**:
  - `LimitedQueue`: Memory-efficient bounded queues
  - `Quantizer`: Signal quantization and filtering
- **Threading**: `Worker` class for background task management

**How it works**: The util module provides building blocks used throughout the library. Mathematical functions handle 3D transformations and robotics calculations. The logging system provides structured output with multiple targets. Performance tools ensure real-time constraints are met in control applications.

**Use cases**: Real-time control loops, data processing, logging and debugging, mathematical computations, system optimization, background processing.

---

## Integration Patterns

The modules are designed to work together:

1. **Configuration → Event Listener**: Settings loaded from config drive event processing behavior
2. **Connection → I/O**: Shared memory enables high-speed data exchange between I/O processes
3. **Event Listener → Sequence**: Events trigger sequence execution with state management
4. **System Dashboard → All Modules**: Monitors and displays status from all system components
5. **Util → Everything**: Provides foundational utilities used across all modules

## Real-World Applications

- **Industrial Automation**: Complete control systems with I/O, sequencing, and monitoring
- **Robotics**: Multi-axis robot control with path planning and sensor integration
- **Manufacturing**: Process control with real-time monitoring and quality assurance
- **Research**: Experimental setups with data acquisition and analysis
- **System Administration**: Server monitoring and management tools

Feel free to explore each module's detailed documentation for implementation specifics and API references.
"""

from . import config, connection, event_listener, io, sequence, system_dashboard, util

__all__ = [
    "config",
    "connection",
    "event_listener",
    "io",
    "sequence",
    "system_dashboard",
    "util",
]
