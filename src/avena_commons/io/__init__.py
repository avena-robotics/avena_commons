"""
🔌 I/O Module - Industrial Communication & Device Management
================================================================

The IO module provides comprehensive support for industrial communication protocols,
device drivers, and I/O management. This module forms the backbone of hardware
interaction in the avena_commons ecosystem, enabling seamless integration with
various industrial devices and systems.

## 📦 Available Imports

### Communication Protocols (from .bus)
- **`bus`**: Complete bus protocol implementations including EtherCAT, ModbusRTU, and ModbusTCP

### Device Management (from .device)
- **`device`**: Device driver ecosystem with I/O modules, motor controllers, and sensors

### Event Processing (from .io_event_listener)
- **`IO_server`**: Asynchronous event-driven I/O processing engine

### Device Abstraction (from .virtual_device)
- **`VirtualDevice`**: Abstract base class template for virtual device interfaces to real hardware connected through buses

🚀 Core Components Overview
===========================

🌐 Bus Protocols (bus module)
-----------------------------
Industrial communication protocol implementations managed by IO_server:

• **EtherCAT**: Real-time EtherCAT protocol for automation

• **ModbusRTU**: Serial communication over RS485/RS232

• **ModbusTCP**: TCP/IP-based Modbus for Ethernet networks

Protocols are configured in JSON and automatically initialized by IO_server:
- Connection management and device discovery
- Real-time data exchange with connected devices
- Error handling and recovery mechanisms
- Performance optimization and cycle timing

🔧 Device Drivers (device module)
---------------------------------
Physical device drivers loaded through configuration and managed by IO_server:

**I/O Devices (8 types):**
- Digital/analog input/output modules
- Mixed I/O expansion units
- Safety I/O systems
- High-speed counter modules

**Motor Drivers (2 types):**
- Servo motor controllers with position feedback
- Stepper motor drivers with microstepping

**Sensors (8 types):**
- Temperature, pressure, flow sensors
- Position encoders and proximity switches
- Environmental monitoring devices

All devices are:
- Configured via JSON with bus protocol assignments
- Automatically connected and validated by IO_server
- Accessible through virtual device method mappings
- Monitored for connection status and errors

⚡ IO_server - Event Processing Engine
-------------------------------------
Central event-driven I/O management system that:
- Loads complete system configuration from JSON files
- Initializes and manages all buses, devices, and virtual devices
- Routes incoming events to appropriate virtual device handlers
- Processes device states asynchronously for optimal performance
- Provides real-time monitoring and error recovery
- Supports configuration merging (general + local overrides)

🖥️ VirtualDevice - Device Interface Template
---------------------------------------------
Abstract base class template for creating virtual device interfaces to real hardware:
- Configured in JSON with method mappings to physical devices
- Standardized interface for complex device operations
- Hardware abstraction layer managed by IO_server
- Event-driven control through IO_server routing
- Device state monitoring and lifecycle management

💡 Practical Usage Examples
===========================

IO_server Configuration-Based Setup:
```python
from avena_commons.io import IO_server

# Initialize IO_server with configuration files
# All buses, devices, and virtual devices are loaded from JSON config
server = IO_server(
    name="industrial_io_server",
    port=8080,
    configuration_file="local_config.json",
    general_config_file="default_config.json",
    debug=True
)

# Server automatically loads and manages:
# - Bus protocols (EtherCAT, ModbusRTU, ModbusTCP)
# - Physical devices (I/O modules, motor drivers, sensors)
# - Virtual devices (device interfaces with methods)
await server.start()
```

Configuration File Structure:
```json
{
    "bus": {
        "ethercat_master": {
            "class": "EtherCAT",
            "configuration": {
                "interface": "eth0",
                "cycle_time": 1000
            }
        },
        "modbus_serial": {
            "class": "ModbusRTU",
            "configuration": {
                "port": "/dev/ttyUSB0",
                "baudrate": 115200
            }
        }
    },
    "device": {
        "servo_drive_1": {
            "class": "motor_driver/ServoDriver",
            "bus": "ethercat_master",
            "configuration": {
                "slave_address": 1,
                "max_velocity": 3000
            }
        },
        "temp_sensor_1": {
            "class": "sensors/TemperatureSensor",
            "bus": "modbus_serial",
            "configuration": {
                "modbus_address": 10,
                "update_interval": 100
            }
        }
    },
    "virtual_device": {
        "feeder1": {
            "class": "Feeder",
            "methods": {
                "move_to_position": {
                    "device": "servo_drive_1",
                    "method": "move_absolute"
                },
                "get_temperature": {
                    "device": "temp_sensor_1",
                    "method": "read_value"
                }
            }
        }
    }
}
```

Event-Driven Device Control:
```python
# Send events to virtual devices through IO_server
from avena_commons.event_listener import Event

# Create event for virtual device
event = Event(
    source="munchies_algo",
    destination="localhost:8080",
    event_type="feeder_move_to_position",
    data={
        "device_id": "1",
        "position": 1500,
        "velocity": 2000
    }
)

# IO_server routes event to feeder1 virtual device
# which calls servo_drive_1.move_absolute(position=1500, velocity=2000)
await event_client.send_event(event)
```

🔄 Integration Patterns
=======================

**Configuration-Driven Architecture:**
IO_server manages the entire system through JSON configuration:
- Declarative device setup without manual initialization
- Automatic bus protocol assignment and device discovery
- Configuration merging for deployment flexibility
- Centralized error handling and device validation

**Event-Driven Device Control:**
All device interactions happen through IO_server event routing:
- Events sent to virtual device names (e.g., "feeder1")
- IO_server routes to appropriate physical device methods
- Asynchronous processing with automatic error recovery
- Real-time device state monitoring and lifecycle management

**Hierarchical Device Management:**
Three-layer architecture managed by IO_server:
- **Bus Layer**: Protocol implementations (EtherCAT, Modbus)
- **Device Layer**: Physical device drivers with bus assignments
- **Virtual Device Layer**: High-level interfaces with method mappings

**Configuration File Patterns:**
Flexible configuration structure supports:
- General configuration files for default settings
- Local configuration files for deployment-specific overrides
- Method mappings connecting virtual devices to physical operations
- Bus protocol assignments for automatic device connections

⚙️ Advanced Features
===================

• **Configuration Management**: JSON-based device setup with general and local file merging

• **Automatic Discovery**: IO_server discovers and validates all configured devices on startup

• **Event Routing**: Intelligent routing of events to virtual devices based on event_type patterns

• **Device Lifecycle**: Automatic initialization, connection validation, and error recovery

• **Real-time Monitoring**: Continuous device state checking through virtual device tick() methods

• **Error Isolation**: Device-level error handling prevents single failures from affecting the system

• **Method Mapping**: Flexible virtual device method definitions connecting to physical device operations

• **Hot Configuration**: Support for configuration changes without system restart (future enhancement)

This module is essential for industrial automation systems requiring robust I/O management
through configuration-driven setup and event-based device control. All device interactions
are managed centrally by IO_server, eliminating the need for direct bus or device manipulation.
"""

# =============================================================================
# Imports - Organized by Source Module
# =============================================================================

# Bus Protocol Implementations
# Device Drivers and Management
from . import (
    bus,  # from './bus' - Industrial communication protocols
    device,  # from './device' - Device driver ecosystem
)

# Event Processing Engine
from .io_event_listener import (
    IO_server,  # from './io_event_listener' - Asynchronous I/O processing
)

# Virtual Device Abstraction
from .virtual_device import (
    VirtualDevice,  # from './virtual_device' - Abstract device base class
)

# =============================================================================
# Public API Definition
# =============================================================================

__all__ = [
    # Communication Protocols
    "bus",  # Industrial bus protocols: EtherCAT, ModbusRTU, ModbusTCP
    # Device Management
    "device",  # Device drivers: I/O modules, motor controllers, sensors
    # Event Processing
    "IO_server",  # Asynchronous event-driven I/O processing engine
    # Device Abstraction
    "VirtualDevice",  # Abstract base class template for real device interfaces managed by IO_server
]
