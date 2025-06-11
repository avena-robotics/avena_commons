import importlib
import json
import traceback
from typing import Any, Dict, Optional

from avena_commons.event_listener.event import Event, Result
from avena_commons.event_listener.event_listener import (
    EventListener,
)
from avena_commons.util.logger import MessageLogger, debug, error, warning
from avena_commons.util.measure_time import MeasureTime


class IO_server(EventListener):
    def __init__(
        self,
        name: str,
        port: int,
        configuration_file: str,
        general_config_file: str,
        message_logger: MessageLogger | None = None,
        debug: bool = True,
    ):
        # TODO: mergowanie konfiguracji generycznej i lokalnych zmian w konfiguracji
        self._message_logger = message_logger
        self._debug = debug
        try:
            self._load_device_configuration(configuration_file, general_config_file)
            self.check_local_data_frequency: int = 50
            super().__init__(
                name=name,
                port=port,
                message_logger=self._message_logger,
                do_not_load_state=True,
            )
        except Exception as e:
            error(f"Initialisation error: {e}", message_logger=self._message_logger)

    async def _analyze_event(self, event: Event) -> Result:
        """
        Analyze and route incoming events to appropriate handlers.

        This method examines the source of each incoming event and routes it to the
        appropriate handler. Currently, it only processes events from 'munchies_algo' source.

        For 'munchies_algo' events, it calls the device_selector method to determine
        which virtual device should handle the event, and adds successfully matched
        events to the processing queue.

        Args:
            event (Event): Incoming event to process

        Returns:
            bool: True if event was successfully processed

        Raises:
            ValueError: If event source is invalid or not supported
        """
        if self._debug:
            debug(
                f"Analyzing event {event.event_type} from {event.source}",
                message_logger=self._message_logger,
            )
        match event.source:
            case "munchies_algo":
                add_to_processing = await self.device_selector(event)
                if add_to_processing:
                    self._add_to_processing(event)
                return True
            case _:
                raise ValueError(f"Invalid event source: {event.source}")

    async def device_selector(self, event: Event) -> bool:
        """
        Select the appropriate virtual device based on the event data and action type.

        This method extracts the device_id from the event data and parses the event_type
        to determine which virtual device should handle the event. It constructs the device name
        by combining the device prefix (extracted from event_type) with the device_id.

        If the corresponding virtual device exists and has an 'execute_event' method,
        the method will call it with the event data. If the device method returns an Event object,
        it will reply with that event. Otherwise, it adds the event to processing queue.

        Args:
            event (Event): Incoming event to process

        Returns:
            bool: True if action is going to be processed, False otherwise
        """
        device_id = event.data.get("device_id")
        if device_id is None:
            error(
                "Device ID not found in event data", message_logger=self._message_logger
            )
            return False

        # Extract device name and specific action from event_type
        event_type = event.event_type
        if not event_type:
            error(
                "Action type is missing in the event",
                message_logger=self._message_logger,
            )
            return False
        # Split event_type to extract device prefix and specific action
        parts = event_type.split("_", 1)  # Split at first underscore only
        if len(parts) < 2:
            error(
                f"Invalid event_type format: {event_type}. Expected format: device_action",
                message_logger=self._message_logger,
            )
            return False

        device_prefix = parts[0].lower()
        action = "execute_event"  # Default method to call on the device

        # Create device name by combining prefix with device_id
        device_name = f"{device_prefix}{device_id}"

        # Search directly for the device in virtual_devices dictionary
        if hasattr(self, "virtual_devices") and device_name in self.virtual_devices:
            device = self.virtual_devices[device_name]
            # Check if the specific action method exists on the device
            if hasattr(device, action) and callable(getattr(device, action)):
                try:
                    # Call the method with event data
                    event = getattr(device, action)(event)
                    if isinstance(event, Event):
                        # If the method returns an Event, we can safely reply that event
                        await self._reply(event)
                        return False  # Do not add to processing
                    return True  # Add to processing
                except Exception as e:
                    error(
                        f"Error calling method {action} on device {device_name}: {str(e)}",
                        message_logger=self._message_logger,
                    )
            else:
                error(
                    f"Method {action} not found on device {device_name}",
                    message_logger=self._message_logger,
                )
        else:
            error(
                f"Virtual device {device_name} not found",
                message_logger=self._message_logger,
            )

        return False  # move to processing False

    async def _check_local_data(self):
        """
        Process virtual devices and handle finished events.

        This method periodically checks all virtual devices, calls their tick() method if available,
        and processes any finished events. Key operations:

        1. Iterates through all virtual devices
        2. Calls tick() on each device (if method exists)
        3. Processes the 'finished_events' list for each device (if exists)
           - Removes finished events from the processing queue
           - Logs processing status

        Implementation details:
        - Uses defensive programming to handle missing attributes or methods
        - Catches and logs exceptions at the device level to prevent one failing device
          from affecting others
        - Error handling at multiple levels (device level and method level)
        """
        # debug(f"Checking local data begin ---", message_logger=self._message_logger)
        with MeasureTime(
            label="io - checking local data",
            max_execution_time=20.0,
            message_logger=self._message_logger,
        ):
            try:
                # Process all virtual devices
                if hasattr(self, "virtual_devices") and isinstance(
                    self.virtual_devices, dict
                ):
                    for device_name, device in self.virtual_devices.items():
                        if device is None:
                            continue

                            # Call the tick method if it exists
                        with MeasureTime(
                            label=f"io - tick({device_name})",
                            message_logger=self._message_logger,
                        ):
                            if hasattr(device, "tick") and callable(device.tick):
                                try:
                                    device.tick()
                                except Exception as e:
                                    error(
                                        f"Error calling tick() on virtual device {device_name}: {str(e)}, {traceback.format_exc()}",
                                        message_logger=self._message_logger,
                                    )

                            # Check if device has a finished events list and process any finished events
                        with MeasureTime(
                            label=f"io - finished_events({device_name})",
                            message_logger=self._message_logger,
                        ):
                            if hasattr(device, "finished_events") and callable(
                                device.finished_events
                            ):
                                list_of_events = device.finished_events()
                                if list_of_events:
                                    debug(
                                        f"Processing finished events for device {device_name}"
                                    )
                                    try:
                                        # Process finished events
                                        for event in list_of_events:
                                            if not isinstance(event, Event):
                                                error(
                                                    f"Finished event is not of type Event: {event}",
                                                    message_logger=self._message_logger,
                                                )
                                                continue
                                            # Find and remove the event from processing
                                            event: Event = (
                                                self._find_and_remove_processing_event(
                                                    event_type=event.event_type,
                                                    timestamp=event.timestamp,
                                                )
                                            )
                                            if event:
                                                await self._reply(event)
                                                if self._debug:
                                                    debug(
                                                        f"Processing event for device {device_name}: {event.event_type}",
                                                        message_logger=self._message_logger,
                                                    )
                                            else:
                                                if self._debug:
                                                    debug(
                                                        f"Event not found in processing: {event.event_type} for device: {device_name}",
                                                        message_logger=self._message_logger,
                                                    )
                                    except Exception as e:
                                        error(
                                            f"Error processing events for {device_name}: {str(e)}",
                                            message_logger=self._message_logger,
                                        )
            except Exception as e:
                error(
                    f"Error in _check_local_data: {str(e)}",
                    message_logger=self._message_logger,
                )
        # debug(f"Checking local data end ---", message_logger=self._message_logger)

    def _load_device_configuration(
        self, configuration_file: str, general_config_file: str = None
    ):
        """
        Load and process device configuration from JSON files, merging general and local configurations.

        This method loads both general (default) and local configuration files, merging them with
        local configuration taking precedence. It then initializes all buses, physical devices, and
        virtual devices based on the merged configuration.

        1. Parse the JSON configuration file
        2. First initialize all buses
        3. Then initialize all physical devices, passing bus references to devices
        4. Initialize virtual devices with references to physical devices based on "methods"

        The configuration structure follows this pattern:
        ```json
        {
            "bus": {
                "modbus_1": {
                    "class": "ModbusRTU",
                    "configuration": {}
                }
            },
            "device": {              # Physical devices definitions
                "device_name": {
                    "class": "motor_driver/DriverClass",
                    "configuration": {},
                    "bus": "modbus_1"      # Reference to parent bus
                }
            },
            "virtual_device": {      # Virtual devices with methods
                "feeder1": {
                    "class": "Feeder",
                    "methods": {           # Methods referencing physical devices
                        "method_name": {
                            "device": "device_name",
                            "method": "device_method"
                        }
                    }
                }
            }
        }
        ```

        This approach eliminates hardcoded device types, allowing the system to adapt
        to any structure in the configuration file based on the presence of specific attributes.

        Args:
            configuration_file (str): Path to the local JSON configuration file
            general_config_file (str, optional): Path to the general (default) configuration file

        Raises:
            FileNotFoundError: If a required configuration file doesn't exist
            ValueError: If a configuration file contains invalid JSON
            RuntimeError: If any device fails to initialize properly
            Exception: For any other error during configuration loading
        """
        if self._debug:
            debug(
                f"Loading configuration from general file: {general_config_file} and local file: {configuration_file}",
                message_logger=self._message_logger,
            )

        # Initialize device containers
        self.buses = {}
        self.physical_devices = {}
        self.virtual_devices = {}

        # Track initialization failures
        initialization_failures = []

        # Store device configurations by type for ordered initialization
        bus_configs = {}
        device_configs = {}
        virtual_device_configs = {}

        try:
            # Load and merge configurations
            merged_config = self._load_and_merge_configs(
                general_config_file, configuration_file
            )

            # Extract configuration sections by type
            bus_configs = merged_config.get("bus", {})
            device_configs = merged_config.get("device", {})
            virtual_device_configs = merged_config.get("virtual_device", {})

            # STEP 1: Initialize all buses
            if self._debug:
                debug(
                    f"Initializing {len(bus_configs)} buses",
                    message_logger=self._message_logger,
                )

            for bus_name, bus_config in bus_configs.items():
                if "class" not in bus_config:
                    warning(
                        f"Bus {bus_name} missing class definition, skipping",
                        message_logger=self._message_logger,
                    )
                    continue

                # Initialize the bus
                class_name = bus_config["class"]

                bus = self._init_class_from_config(
                    device_name=bus_name,
                    class_name=class_name,
                    folder_name="bus",
                    config=bus_config,  # Pass the full config
                )

                if bus:
                    self.buses[bus_name] = bus
                else:
                    initialization_failures.append(
                        f"Failed to initialize bus {bus_name}"
                    )

            debug(f"Buses: {self.buses}", message_logger=self._message_logger)

            # STEP 2: Initialize standalone physical devices
            if self._debug:
                debug(
                    f"Initializing {len(device_configs)} physical devices",
                    message_logger=self._message_logger,
                )

            for device_name, device_config in device_configs.items():
                if "class" not in device_config:
                    warning(
                        f"Device {device_name} missing class definition, skipping",
                        message_logger=self._message_logger,
                    )
                    continue

                # Get bus reference (if any)
                bus_name = device_config.get("bus")
                parent_bus = None

                if bus_name:
                    # Check if the referenced bus exists
                    if bus_name in self.buses:
                        parent_bus = self.buses[bus_name]
                    else:
                        warning(
                            f"Device {device_name} references non-existent bus {bus_name}",
                            message_logger=self._message_logger,
                        )

                # Create a copy of config without the bus reference
                device_init_config = {
                    k: v for k, v in device_config.items() if k != "bus"
                }

                # Initialize the device with parent_bus reference
                class_name = device_config["class"]

                device = self._init_class_from_config(
                    device_name=device_name,
                    class_name=class_name,
                    folder_name="device",
                    config=device_init_config,
                    parent=parent_bus,
                )

                if device:
                    # Store in physical_devices container
                    self.physical_devices[device_name] = device
                else:
                    initialization_failures.append(
                        f"Failed to initialize device {device_name}"
                    )

            # step 2.5: CONFIG BUS #TODO: Verify
            for bus_name, bus in self.buses.items():
                if hasattr(bus, "configure") and callable(bus.configure):
                    try:
                        bus.configure(self.physical_devices)
                    except Exception as e:
                        error(
                            f"Error configuring bus {bus_name}: {str(e)}",
                            message_logger=self._message_logger,
                        )
                        # print(traceback.format_exc())
                        error(
                            f"Traceback:\n{traceback.format_exc()}",
                            message_logger=self._message_logger,
                        )

                        raise

            # step 2.75: CHECK DEVICE CONNECTIONS #TODO: Verify
            for device_name, device in self.physical_devices.items():
                # if hasattr(device, "check_device_connection") and callable(device.check_device_connection):
                try:
                    device.check_device_connection()
                except Exception as e:
                    error(
                        f"Error checking device connection {device_name}: {str(e)}",
                        message_logger=self._message_logger,
                    )

            # STEP 3: Initialize virtual devices with references to physical devices
            if self._debug:
                debug(
                    f"Initializing {len(virtual_device_configs)} virtual devices",
                    message_logger=self._message_logger,
                )

            for (
                virtual_device_name,
                virtual_device_config,
            ) in virtual_device_configs.items():
                if "class" not in virtual_device_config:
                    warning(
                        f"Virtual device {virtual_device_name} missing class definition, skipping",
                        message_logger=self._message_logger,
                    )
                    continue

                # Prepare the device dictionary based on methods configuration
                referenced_devices = {}

                # Analyze methods to identify referenced physical devices
                if "methods" in virtual_device_config and isinstance(
                    virtual_device_config["methods"], dict
                ):
                    methods_config = virtual_device_config["methods"]

                    for method_name, method_config in methods_config.items():
                        if (
                            isinstance(method_config, dict)
                            and "device" in method_config
                        ):
                            device_name = method_config["device"]

                            # Find the referenced physical device
                            if device_name in self.physical_devices:
                                referenced_devices[device_name] = self.physical_devices[
                                    device_name
                                ]
                            elif device_name not in referenced_devices:
                                warning(
                                    f"Virtual device {virtual_device_name} references non-existent device {device_name}",
                                    message_logger=self._message_logger,
                                )

                # Add devices dictionary to configuration
                virtual_device_config["devices"] = referenced_devices

                # Initialize the virtual device
                class_name = virtual_device_config["class"]

                virtual_device = self._init_class_from_config(
                    device_name=virtual_device_name,
                    class_name=class_name,
                    folder_name="virtual_device",
                    config=virtual_device_config,
                )

                if virtual_device:
                    self.virtual_devices[virtual_device_name] = virtual_device
                else:
                    initialization_failures.append(
                        f"Failed to initialize virtual device {virtual_device_name}"
                    )

            # Check if any devices failed to initialize
            if initialization_failures:
                error_message = f"Configuration loading failed. The following devices could not be initialized: {initialization_failures}"
                error(error_message, message_logger=self._message_logger)
                raise RuntimeError(error_message)

            if self._debug:
                debug(
                    f"Configuration loaded successfully: {len(self.buses)} buses, {len(self.physical_devices)} physical devices, {len(self.virtual_devices)} virtual devices",
                    message_logger=self._message_logger,
                )

        except FileNotFoundError:
            error(f"Configuration file not found", message_logger=self._message_logger)
            raise FileNotFoundError(f"Configuration file not found")
        except json.JSONDecodeError as e:
            error(
                f"Invalid JSON in configuration file: {str(e)}",
                message_logger=self._message_logger,
            )
            raise ValueError(f"Invalid JSON in configuration file: {str(e)}")
        except RuntimeError:
            # Re-raise runtime errors (these are our initialization failures)
            error(traceback.format_exc(), message_logger=self._message_logger)
            raise RuntimeError
        except Exception as e:
            error(
                f"Error loading configuration: {str(e)}",
                message_logger=self._message_logger,
            )
            raise

    def _load_and_merge_configs(
        self, general_config_file: str, local_config_file: str
    ) -> dict:
        """
        Load and merge general and local configuration files.

        This method implements a deep merge strategy where:
        1. General configuration is loaded first as the base
        2. Local configuration is loaded and merged on top
        3. Local values override general values when there's a conflict
        4. For nested dictionaries, the merge is performed recursively

        Args:
            general_config_file (str): Path to the general (default) configuration file
            local_config_file (str): Path to the local configuration file with overrides

        Returns:
            dict: Merged configuration dictionary

        Raises:
            FileNotFoundError: If a required configuration file doesn't exist
            json.JSONDecodeError: If a configuration file contains invalid JSON
        """
        # Initialize with empty dictionary
        merged_config = {}

        # Load general configuration if provided
        if general_config_file:
            try:
                with open(general_config_file, "r") as f:
                    general_config = json.load(f)
                merged_config = general_config
                if self._debug:
                    debug(
                        f"Loaded general configuration from {general_config_file}",
                        message_logger=self._message_logger,
                    )
            except FileNotFoundError:
                warning(
                    f"General configuration file not found: {general_config_file}",
                    message_logger=self._message_logger,
                )
            except json.JSONDecodeError as e:
                error(
                    f"Invalid JSON in general configuration file: {str(e)}",
                    message_logger=self._message_logger,
                )
                raise

        # Load local configuration if provided
        if local_config_file:
            try:
                with open(local_config_file, "r") as f:
                    local_config = json.load(f)

                # Deep merge the configurations
                merged_config = self._deep_merge(merged_config, local_config)
                if self._debug:
                    debug(
                        f"Merged local configuration from {local_config_file}",
                        message_logger=self._message_logger,
                    )
            except FileNotFoundError:
                warning(
                    f"Local configuration file not found: {local_config_file}",
                    message_logger=self._message_logger,
                )
            except json.JSONDecodeError as e:
                error(
                    f"Invalid JSON in local configuration file: {str(e)}",
                    message_logger=self._message_logger,
                )
                raise

        return merged_config

    def _deep_merge(self, base_dict: dict, override_dict: dict) -> dict:
        """
        Recursively merge two dictionaries with nested structures.

        Args:
            base_dict (dict): Base dictionary to merge into
            override_dict (dict): Dictionary with values to override base

        Returns:
            dict: Merged dictionary
        """
        result = base_dict.copy()

        for key, value in override_dict.items():
            # If both values are dictionaries, recursively merge them
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                # Otherwise, override the value
                result[key] = value

        return result

    def _init_class_from_config(
        self,
        device_name: str,
        class_name: str,
        folder_name: str,
        config: Dict[str, Any],
        parent: Optional[Any] = None,
    ) -> Any:
        """
        Initialize a class from config using dynamic folder name.

        Args:
            class_name: Name of the class to instantiate (can include subfolder path like "test/Example")
            folder_name: Folder name to look for the class (from JSON structure)
            config: Configuration dictionary
            parent: Parent object (for nested items)

        Returns:
            Initialized instance or None if failed
        """
        try:
            # Check if class_name contains a path separator
            if "/" in class_name or "\\" in class_name:
                # Extract the actual class name from the path
                path_parts = class_name.replace("\\", "/").split("/")
                actual_class_name = path_parts[-1]  # Last part is the actual class name
                subfolder_path = "/".join(
                    path_parts[:-1]
                )  # Everything before is the subfolder path

                # Build the module path including subfolder
                test_module_path = (
                    f"lib.io.{folder_name}.{subfolder_path}.{actual_class_name.lower()}"
                )
                module_path = f"avena_commons.io.{folder_name}.{subfolder_path}.{actual_class_name.lower()}"

                if self._debug:
                    debug(
                        f"Importing {actual_class_name} from path {module_path}",
                        message_logger=self._message_logger,
                    )

                # Import module and get class
                try:
                    module = importlib.import_module(test_module_path)
                    device_class = getattr(module, actual_class_name)

                except (ImportError, AttributeError) as e:
                    try:
                        # Try importing from the main module path
                        module = importlib.import_module(module_path)
                        device_class = getattr(module, actual_class_name)

                    except (ImportError, AttributeError) as e:
                        error(
                            f"Failed to import {actual_class_name} from {module_path}: {str(e)}",
                            message_logger=self._message_logger,
                        )
                        return None
            else:
                # Standard case - no subfolder
                actual_class_name = class_name
                # Test module path
                test_module_path = f"lib.io.{folder_name}.{class_name.lower()}"
                # Build the module path
                module_path = f"avena_commons.io.{folder_name}.{class_name.lower()}"

                if self._debug:
                    debug(
                        f"Importing {class_name} from {test_module_path}",
                        message_logger=self._message_logger,
                    )

                # Import module and get class
                try:
                    module = importlib.import_module(test_module_path)
                    device_class = getattr(module, class_name)

                except (ImportError, AttributeError) as e:
                    try:
                        # Try importing from the module path
                        module = importlib.import_module(module_path)
                        device_class = getattr(module, class_name)

                    except (ImportError, AttributeError) as e:
                        error(
                            f"Failed to import {class_name} from {module_path}: {str(e)}",
                            message_logger=self._message_logger,
                        )
                        return None

            # Correctly determine device type based on folder_name and configuration structure
            is_bus = folder_name == "bus"
            is_virtual = folder_name == "virtual_device"
            is_physical = folder_name == "device"

            # Extract device configuration
            device_config = config.get("configuration", {})

            # Log the configuration being used for this device
            if self._debug:
                debug(
                    f"{device_name} - Initializing {actual_class_name} with configuration: {device_config}",
                    message_logger=self._message_logger,
                )

            # Prepare constructor parameters based on device type
            init_params = {}

            if is_virtual:
                init_params["device_name"] = device_name
                # For virtual devices, pass devices dictionary, methods from config, and message_logger
                init_params["devices"] = config.get("devices", {})
                init_params["methods"] = config.get("methods", {})
                init_params["message_logger"] = self._message_logger
                # Add configuration items directly as parameters for virtual devices too
                for key, value in device_config.items():
                    init_params[key] = value

                if self._debug:
                    debug(
                        f"{device_name} - Virtual device initialization with {len(init_params['devices'])} devices and {len(init_params['methods'])} methods",
                        message_logger=self._message_logger,
                    )

            elif is_physical or is_bus:
                # Add message_logger for both physical devices and buses
                init_params["message_logger"] = self._message_logger
                init_params["device_name"] = device_name

                # If we have a parent (bus), add it as 'bus' parameter (for physical devices on buses)
                if parent is not None:
                    init_params["bus"] = parent

                # Add all configuration items directly as parameters
                for key, value in device_config.items():
                    init_params[key] = value

            # Create instance with appropriate parameters
            device_instance = device_class(**init_params)

            # Set additional direct configuration properties for any JSON fields
            # that weren't part of the constructor parameters
            for key, value in config.items():
                if key not in [
                    "class",
                    "configuration",
                    "device",
                    "methods",
                    "devices",
                    "bus",
                ]:  # Skip special keys
                    if hasattr(device_instance, key) and not callable(
                        getattr(device_instance, key)
                    ):
                        try:
                            setattr(device_instance, key, value)
                            if self._debug:
                                debug(
                                    f"Set attribute {key}={value}",
                                    message_logger=self._message_logger,
                                )
                        except Exception as attr_error:
                            warning(
                                f"Could not set attribute {key}: {attr_error}",
                                message_logger=self._message_logger,
                            )

            if self._debug:
                debug(
                    f"Initialized {folder_name} device with class {actual_class_name}",
                    message_logger=self._message_logger,
                )

            return device_instance

        except Exception as e:
            error(
                f"Error initializing {folder_name} device with class {class_name}: {str(e)}",
                message_logger=self._message_logger,
            )
            error(traceback.format_exc(), message_logger=self._message_logger)
            return None
