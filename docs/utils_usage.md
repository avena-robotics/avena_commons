# Utils Usage Guide for avena_commons.util

This document describes how to use the key measurement and logging tools available in the `avena_commons.util` package.

## 1. Catchtime - Simple execution time measurement

`Catchtime` is a lightweight context manager for quick measurement of code block execution time.

### Basic usage:

```python
from avena_commons.util.catchtime import Catchtime

# Measure execution time of a code block
with Catchtime() as timer:
    # Code to execute
    time.sleep(0.1)
    result = complex_calculation()

print(timer)  # Displays: "Execution time: 100.123456 ms"
```

### Characteristics:
- Very simple implementation
- Automatic result formatting in milliseconds
- Ideal for quick measurements during debugging
- No additional dependencies required

## 2. MeasureTime - Advanced measurement with logging

`MeasureTime` is an advanced time measurement tool with logging capabilities and overtime warnings.

### Basic usage as context manager:

```python
from avena_commons.util.measure_time import MeasureTime
from avena_commons.util.logger import MessageLogger

# Simple measurement with automatic logging
with MeasureTime("Database operation") as timer:
    database_query()
    
print(f"Execution time: {timer.elapsed:.2f}ms")
```

### Usage as decorator:

```python
@MeasureTime("Data processing", max_execution_time=500.0)
def process_data():
    # Function code
    heavy_computation()
    return result

# Function will be automatically measured
result = process_data()
```

### Configuration with logger:

```python
logger = MessageLogger("performance.log")

with MeasureTime(
    label="Critical operation",
    max_execution_time=200.0,  # Warning threshold in ms
    resolution=2,              # Display precision
    message_logger=logger
):
    critical_operation()
```

### Configuration parameters:
- `label`: Label describing the operation
- `max_execution_time`: Time threshold (ms) after which errors are displayed instead of debug messages
- `resolution`: Number of decimal places
- `print_info`: Whether to automatically log results
- `message_logger`: Logger for recording results

## 3. ControlLoop - Real-time loop management

`ControlLoop` is an advanced tool for creating regular execution loops with performance monitoring.

### Basic control loop:

```python
from avena_commons.util.control_loop import ControlLoop

# Loop executed every 50ms (20 Hz)
loop = ControlLoop("main_control", period=0.05)

while running:
    loop.loop_begin()
    
    # Code executed in loop
    sensor_data = read_sensors()
    control_output = control_algorithm(sensor_data)
    send_to_actuators(control_output)
    
    loop.loop_end()  # Automatically waits until end of period

# Display statistics
print(loop)  # MAIN_CONTROL, loops: 1000, overtime: 5, min: 45.2ms, max: 67.8ms, avg: 48.1ms
```

### Loop with data logging:

```python
loop = ControlLoop("data_acquisition", period=0.1)
data_logger = loop.logger("measurements.csv")

# Configure CSV headers
data_logger.store("timestamp")
data_logger.store("temperature") 
data_logger.store("pressure")
data_logger.end_row()

while collecting_data:
    loop.loop_begin()
    
    # Data collection
    temp = temperature_sensor.read()
    press = pressure_sensor.read()
    
    # Logging to CSV
    data_logger.store(time.time())
    data_logger.store(temp)
    data_logger.store(press)
    data_logger.end_row()
    
    loop.loop_end()
```

### Configuration with idle time utilization:

```python
# Loop that uses free time for log dumping
loop = ControlLoop(
    "optimized_loop",
    period=0.02,           # 50 Hz
    fill_idle_time=True,   # Use idle time
    warning_printer=True   # Overtime warnings
)

logger = loop.logger("high_freq_data.csv")

while True:
    loop.loop_begin()
    
    # Fast operations
    fast_processing()
    logger.store(get_measurement())
    logger.end_row()
    
    # Logs are automatically written during idle time
    loop.loop_end()
```

### ControlLoop parameters:
- `name`: Loop name (for identification in logs)
- `period`: Loop period in seconds
- `fill_idle_time`: Whether to use idle time for I/O operations
- `warning_printer`: Whether to display overtime warnings
- `message_logger`: Logger for recording warnings

## 4. Logger - Data logging system

The logging system consists of several components for different purposes.

### MessageLogger - Message logging:

```python
from avena_commons.util.logger import MessageLogger, info, warning, error

# Creating message logger
msg_logger = MessageLogger(
    "application.log",
    clear_file=True,    # Whether to clear file at start
    debug=True,         # Whether to display debug messages
)

# Using global logging functions
info("Application started", message_logger=msg_logger)
warning("Low battery level warning", message_logger=msg_logger)
error("Database connection error", message_logger=msg_logger)

# Direct logger usage
msg_logger.debug("Detailed debug information")
msg_logger.info("General information")
```

### DataLogger - Structured data logging:

```python
from avena_commons.util.logger import DataLogger

# Logger for measurement data recording
data_logger = DataLogger("sensor_data.csv")

# Column headers
data_logger.store("time")
data_logger.store("sensor1")
data_logger.store("sensor2")
data_logger.store("status")
data_logger.end_row()
data_logger.dump_rows(1)

# Data recording in loop
for i in range(1000):
    data_logger.store(time.time())
    data_logger.store(sensor1.read())
    data_logger.store(sensor2.read())
    data_logger.store("OK")
    data_logger.end_row()
    data_logger.dump_rows(1) # Write every 1 row or more but less frequently

    time.sleep(0.1)
```

### Log file rotation:

```python
from avena_commons.util.logger import LoggerPolicyPeriod

# Logger with automatic hourly rotation
rotating_logger = MessageLogger(
    "rotating_app.log",
    period=LoggerPolicyPeriod.LAST_HOUR,  # Rotate every hour
    files_count=24,                       # Keep 24 files (24h history)
    create_symlinks=True                  # Create symbolic links
)
```

## 5. Integration examples

### Complete monitoring system:

```python
from avena_commons.util import ControlLoop, MeasureTime
from avena_commons.util.logger import MessageLogger

# System configuration
msg_logger = MessageLogger("system.log", debug=True)
control_loop = ControlLoop("monitor", period=1.0, fill_idle_time=True, message_logger=msg_logger)
data_logger = control_loop.logger("system_metrics.csv") # added to control loop, automatically executes dump during free time fill_idle_time=True

# Data headers
data_logger.store("timestamp")
data_logger.store("cpu_usage")
data_logger.store("memory_usage")
data_logger.store("disk_usage")
data_logger.end_row()

try:
    while True:
        control_loop.loop_begin()
        
        with MeasureTime("System metrics collection", message_logger=msg_logger):
            # System metrics collection
            cpu = get_cpu_usage()
            memory = get_memory_usage()
            disk = get_disk_usage()
            
            # Data recording
            data_logger.store(time.time())
            data_logger.store(cpu)
            data_logger.store(memory)
            data_logger.store(disk)
            data_logger.end_row()
        
        control_loop.loop_end()
        
except KeyboardInterrupt:
    print(f"\nLoop statistics: {control_loop}")
    msg_logger.info("System monitoring stopped")
```

### Function benchmarking:

```python
from avena_commons.util.measure_time import MeasureTime
from avena_commons.util.catchtime import Catchtime

@MeasureTime("Sorting algorithm", max_execution_time=100.0)
def sort_algorithm(data):
    return sorted(data)

# Comparing different algorithms
algorithms = [bubble_sort, quick_sort, merge_sort]
test_data = generate_test_data(10000)

for algorithm in algorithms:
    with Catchtime() as timer:
        result = algorithm(test_data.copy())
    print(f"{algorithm.__name__}: {timer}")
```

## Best practices

1. **Choosing the right tool:**
   - `Catchtime` - for quick, one-time measurements
   - `MeasureTime` - for regular monitoring with logging
   - `ControlLoop` - for real-time loops with data

2. **Logging configuration:**
   - Use file rotation for long-running applications
   - Set appropriate warning thresholds
   - Use different logging levels (debug, info, warning, error)

3. **Performance optimization:**
   - Set `fill_idle_time=True` in ControlLoop for better resource utilization when writing CSV data
   - Use appropriate loop periods
   - Monitor overtime statistics

4. **Error handling:**
   - Always check ControlLoop statistics after completion
   - Use try-except for graceful shutdown
   - Log errors with appropriate level of detail
