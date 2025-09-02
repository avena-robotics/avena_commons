# Przegląd Systemu IO Event Listener
::: avena_commons.io.io_event_listener
    options:
      members_order: source
      show_root_heading: true
      show_source: true

## Wprowadzenie

System Event Listener stanowi fundament architektury sterowanej zdarzeniami, umożliwiając płynną komunikację między różnymi komponentami poprzez mechanizm asynchronicznych zdarzeń. Zapewnia on stabilne i elastyczne środowisko dla przepływu informacji w systemie rozproszonym, gdzie różne komponenty mogą działać niezależnie, ale w skoordynowany sposób.

## Klasa bazowa EventListener

EventListener to klasa bazowa, która dostarcza kluczowe funkcjonalności dla wszystkich komponentów systemu zdolnych do odbierania i przetwarzania zdarzeń. Jej głównym zadaniem jest zarządzanie cyklem życia zdarzeń w systemie - od ich przyjęcia, przez analizę, przetwarzanie, aż po ewentualne przekazanie dalej.

### Kluczowe funkcjonalności

- **Wielowątkowa obsługa zdarzeń** - równoległe przetwarzanie wielu zdarzeń
- **Priorytetyzacja zdarzeń** - obsługa zdarzeń według ich ważności
- **Endpoints HTTP** - integracja z FastAPI umożliwiająca komunikację przez REST API
- **Trwałość stanu** - zachowywanie stanu między restartami systemu
- **Bezpieczna synchronizacja** - mechanizmy blokad dla operacji współbieżnych
- **Dynamiczna konfiguracja** - elastyczne dostosowywanie zachowania systemu

### Przepływ zdarzeń

Zdarzenia w systemie przechodzą przez kilka etapów:

1. **Przyjęcie** - zdarzenie trafia do systemu poprzez endpoint FastAPI
2. **Analiza** - system decyduje jak zdarzenie powinno być obsłużone
3. **Przetwarzanie** - wykonanie odpowiednich akcji związanych ze zdarzeniem
4. **Przekazanie** - opcjonalne przekierowanie zdarzenia do innych komponentów

Ten proces jest obsługiwany przez dedykowane wątki, które monitorują różne kolejki zdarzeń i reagują na zmiany w czasie rzeczywistym.

## Implementacja IO_server

IO_server rozszerza funkcjonalność bazowego EventListener, dodając specjalistyczne mechanizmy do zarządzania urządzeniami wejścia/wyjścia. Jego głównym zadaniem jest pośredniczenie między logiką biznesową a fizycznymi urządzeniami, takimi jak czujniki, silniki czy inne elementy wykonawcze.

```python
class IO_server(EventListener):
    """Komponent serwera IO odpowiedzialny za obsługę operacji wejścia/wyjścia oraz zdarzeń.

    Args:
        name (str): Nazwa serwera IO.
        port (int): Port serwera IO.
        configuration_file (str): Ścieżka do lokalnego pliku konfiguracji.
        general_config_file (str): Ścieżka do ogólnego (domyślnego) pliku konfiguracji.
        message_logger (MessageLogger | None): Logger wiadomości (opcjonalny).
        debug (bool): Czy wypisywać komunikaty debug (domyślnie True).
        load_state (bool): Czy wczytywać zapisany stan urządzeń (domyślnie True).
    """

    def __init__(
        self,
        name: str,
        port: int,
        configuration_file: str,
        general_config_file: str,
        message_logger: MessageLogger | None = None,
        debug: bool = True,
        load_state: bool = True,
    ):
        """Inicjalizuje serwer IO oraz przygotowuje podstawowy stan.

        Args:
            name (str): Nazwa serwera IO.
            port (int): Port serwera IO.
            configuration_file (str): Ścieżka do lokalnego pliku konfiguracji urządzeń.
            general_config_file (str): Ścieżka do ogólnego pliku konfiguracji.
            message_logger (MessageLogger | None): Logger wiadomości używany do logowania.
            debug (bool): Włącza/wyłącza komunikaty debug.
            load_state (bool): Włącza/wyłącza wczytywanie poprzedniego stanu urządzeń.
        """
        self._message_logger = message_logger
        self._debug = debug
        self._load_state = load_state
        # Pola stanu błędu IO
        self._error = False
        self._error_message = None

        try:
            # Zachowaj parametry do użycia podczas INITIALIZING
            self._name = name
            self._port = port
            self._configuration_file = configuration_file
            self._general_config_file = general_config_file
            self.check_local_data_frequency: int = 50
            super().__init__(
                name=name,
                port=port,
                message_logger=self._message_logger,
                load_state=self._load_state,
            )
        except Exception as e:
            error(f"Initialisation error: {e}", message_logger=self._message_logger)

    async def on_initializing(self):
        """
        FSM Callback: STOPPED → INITIALIZED
        Inicjalizacja komponentu IO Server oraz ustawienie stanu (bez wykonywania operacji urządzeń)
        """
        if self._debug:
            debug(
                "FSM: Initializing IO server",
                message_logger=self._message_logger,
            )
        try:
            # Wczytaj konfigurację urządzeń
            self._load_device_configuration(
                self._configuration_file, self._general_config_file
            )
            # Zbuduj słownik stanu dla aktualnej konfiguracji
            self._state = self._build_state_dict(
                self._name,
                self._port,
                self._configuration_file,
                self._general_config_file,
            )
        except Exception as e:
            error(
                f"Initialisation error during on_initializing: {e}",
                message_logger=self._message_logger,
            )
            raise

        if self._debug:
            debug(
                "FSM: IO server initialized (devices not started)",
                message_logger=self._message_logger,
            )
```

### System dynamicznej konfiguracji urządzeń

Jedną z kluczowych cech IO_server jest dynamiczny system konfiguracji urządzeń, który umożliwia:

- Definiowanie struktury urządzeń w pliku JSON bez konieczności modyfikacji kodu źródłowego
- Automatyczne ładowanie i inicjalizację urządzeń na podstawie konfiguracji
- Tworzenie hierarchii urządzeń (np. urządzenia na magistrali)
- Abstrahowanie złożoności sprzętowej za pomocą urządzeń wirtualnych

### Architektura konfiguracji

Plik konfiguracyjny systemu IO wykorzystuje przejrzystą strukturę hierarchiczną z trzema głównymi sekcjami:

- **bus** - definicje magistrali komunikacyjnych (np. Modbus, I2C)
- **device** - definicje fizycznych urządzeń podłączonych do systemu
- **virtual_device** - abstrakty wyższego poziomu, agregujące funkcje urządzeń fizycznych

Taka struktura pozwala na oddzielenie warstw abstrakcji i ułatwia zarządzanie złożonymi systemami sprzętowymi.

Przykładowy fragment rzeczywistej konfiguracji (wycinek z `event_driven_proof_of_concept/lib/munchies/constants/APS00_io_server_config.json`):

```json
{
  "bus": {
    "modbus_fast": {
      "class": "ModbusRTU",
      "configuration": {
        "serial_port": "/dev/ttyS4",
        "baudrate": 115200,
        "core": 1,
        "timeout_ms": 5,
        "trace_packet": false,
        "trace_pdu": false,
        "retry": 3
      }
    }
  },
  "device": {
    "TLC57R24V08_feedertacek_1": {
      "class": "motor_driver/TLC57R24V08",
      "configuration": { "address": 13, "configuration_type": 2 },
      "bus": "modbus_fast"
    }
  },
  "virtual_device": {
    "feeder1": {
      "class": "FeederTacek",
      "methods": {
        "run_jog": { "device": "TLC57R24V08_feedertacek_1", "method": "run_jog" },
        "stop": { "device": "TLC57R24V08_feedertacek_1", "method": "stop" },
        "read_sensor_1": { "device": "TLC57R24V08_feedertacek_1", "method": "di0" }
      }
    }
  }
}
```

## Proces ładowania konfiguracji

Proces inicjalizacji systemu IO obejmuje kilka kluczowych etapów, które zapewniają prawidłowe przygotowanie wszystkich komponentów sprzętowych:

### 1. Przygotowanie środowiska

Na początku system tworzy kontenery dla różnych typów urządzeń:
- Magistrale komunikacyjne
- Urządzenia fizyczne
- Urządzenia wirtualne

### 2. Wczytanie i analiza konfiguracji

System wczytuje plik JSON i segreguje zawartość według typów urządzeń. Każdy typ jest przetwarzany oddzielnie, ponieważ różne typy urządzeń wymagają różnych parametrów inicjalizacji i mogą mieć różne zależności.

### 3. Sekwencja inicjalizacji

Inicjalizacja przebiega w ściśle określonej kolejności:

1. **Magistrale (Buses)** - najpierw inicjalizowane są magistrale, ponieważ inne urządzenia mogą być od nich zależne. Przykładem jest magistrala Modbus, która stanowi medium komunikacyjne dla urządzeń podrzędnych.

2. **Urządzenia fizyczne (Physical Devices)** - następnie inicjalizowane są urządzenia fizyczne. Jeśli urządzenie wymaga połączenia z magistralą, otrzymuje referencję do odpowiedniego obiektu magistrali.

3. **Urządzenia wirtualne (Virtual Devices)** - na końcu tworzone są urządzenia wirtualne, które są abstrakcyjnymi warstwami nad urządzeniami fizycznymi. Ich zadaniem jest dostarczenie uproszczonego interfejsu dla złożonych operacji sprzętowych.

### 4. Dynamiczne tworzenie instancji

Dla każdego elementu konfiguracji system:

1. Odnajduje odpowiednią klasę przez dynamiczny import modułu
2. Tworzy instancję z odpowiednimi parametrami
3. Konfiguruje dodatkowe właściwości
4. Zapisuje referencję w odpowiednim kontenerze

Szczególną uwagę poświęcono obsłudze błędów - każdy nieudany import lub inicjalizacja są rejestrowane i nie przerywają całego procesu.

Przykładowa implementacja metody ładującej i inicjalizującej konfiguracje:

```python
def _load_device_configuration(
    self, configuration_file: str, general_config_file: str = None
):
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
                config=bus_config,
            )

            if bus:
                self.buses[bus_name] = bus
            else:
                initialization_failures.append(
                    f"Failed to initialize bus {bus_name}"
                )

        debug(f"Buses: {self.buses}", message_logger=self._message_logger)

        # STEP 1.1: Initial bus health check (fail-fast before devices)
        self._assert_bus_healthy(
            escalate_on_failure=True, during_initialization=True
        )

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
                if bus_name in self.buses:
                    parent_bus = self.buses[bus_name]
                else:
                    warning(
                        f"Device {device_name} references non-existent bus {bus_name}",
                        message_logger=self._message_logger,
                    )

            device_init_config = {k: v for k, v in device_config.items() if k != "bus"}

            class_name = device_config["class"]

            device = self._init_class_from_config(
                device_name=device_name,
                class_name=class_name,
                folder_name="device",
                config=device_init_config,
                parent=parent_bus,
            )

            if device:
                self.physical_devices[device_name] = device
            else:
                initialization_failures.append(
                    f"Failed to initialize device {device_name}"
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

            referenced_devices = {}
            if "methods" in virtual_device_config and isinstance(
                virtual_device_config["methods"], dict
            ):
                methods_config = virtual_device_config["methods"]
                for method_name, method_config in methods_config.items():
                    if isinstance(method_config, dict) and "device" in method_config:
                        device_name = method_config["device"]
                        if device_name in self.physical_devices:
                            referenced_devices[device_name] = self.physical_devices[
                                device_name
                            ]
                        elif device_name not in referenced_devices:
                            warning(
                                f"Virtual device {virtual_device_name} references non-existent device {device_name}",
                                message_logger=self._message_logger,
                            )

            virtual_device_config["devices"] = referenced_devices

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
        error(traceback.format_exc(), message_logger=self._message_logger)
        raise RuntimeError
    except Exception as e:
        error(
            f"Error loading configuration: {str(e)}",
            message_logger=self._message_logger,
        )
        raise
```

## Typowe przypadki użycia

Typowy scenariusz wykorzystania systemu IO obejmuje:

1. **Definicja magistrali** - np. Modbus RTU podłączony przez port szeregowy
2. **Konfiguracja sterowników urządzeń** - np. sterownik silnika z określonym adresem i typem konfiguracji
3. **Abstrakcja wysokiego poziomu** - np. "podajnik" łączący funkcje sterownika silnika i czujników

Po inicjalizacji system oferuje ujednolicony interfejs do kontrolowania urządzeń - aplikacja może wysyłać zdarzenia wysokiego poziomu (np. "uruchom podajnik"), a system IO tłumaczy je na niskopoziomowe operacje sprzętowe.

## Monitorowanie i cykl pracy

System implementuje mechanizm regularnego sprawdzania stanu urządzeń wirtualnych. W określonych odstępach czasu (domyślnie 100 razy na sekundę) wywoływana jest metoda `tick()` na każdym urządzeniu wirtualnym, co pozwala na:

- Regularną aktualizację stanu urządzenia
- Wykrywanie zmian i reagowanie na nie
- Symulację zachowań zależnych od czasu
- Generowanie zdarzeń na podstawie warunków

Przykładowa implementacja metody monitorującej i przetwarzającej dane lokalne:

```python
async def _check_local_data(self):
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
                                raise e

                        # Proactive error detection: if any virtual device reports ERROR, trigger IO FSM ON_ERROR
                        try:
                            if hasattr(device, "get_current_state") and callable(
                                device.get_current_state
                            ):
                                current_state = device.get_current_state()
                                if current_state == VirtualDeviceState.ERROR:
                                    # Zapisz źródło błędu
                                    self._error = True
                                    self._error_message = device._error_message
                                    if self.fsm_state not in {
                                        EventListenerState.ON_ERROR,
                                        EventListenerState.FAULT,
                                    }:
                                        error(
                                            f"Virtual device {device_name} in ERROR; switching IO FSM to ON_ERROR",
                                            message_logger=self._message_logger,
                                        )
                                        self._change_fsm_state(
                                            EventListenerState.ON_ERROR
                                        )
                                        return
                        except Exception as e:
                            error(
                                f"Error checking state for {device_name}: {str(e)}",
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
                                        original_event = event
                                        processed_event: Event = (
                                            self._find_and_remove_processing_event(
                                                event=event
                                            )
                                        )
                                        if processed_event:
                                            await self._reply(processed_event)
                                            if self._debug:
                                                debug(
                                                    f"Processing event for device {device_name}: {processed_event.event_type}",
                                                    message_logger=self._message_logger,
                                                )
                                        else:
                                            if self._debug:
                                                debug(
                                                    f"Event not found in processing: {original_event.event_type} for device: {device_name}",
                                                    message_logger=self._message_logger,
                                                )
                                except Exception as e:
                                    error(
                                        f"Error processing events for {device_name}: {str(e)}",
                                        message_logger=self._message_logger,
                                    )
                                    raise e
        except Exception as e:
            error(
                f"Error in _check_local_data: {str(e)}",
                message_logger=self._message_logger,
            )
            self._change_fsm_state(EventListenerState.ON_ERROR)
            return

        # Proaktywna detekcja błędów urządzeń fizycznych (eskalacja do ON_ERROR przy problemie ruchu)
        try:
            if hasattr(self, "physical_devices") and isinstance(
                self.physical_devices, dict
            ):
                for device_name, device in self.physical_devices.items():
                    if device is None:
                        continue
                    try:
                        dev_error = False
                        dev_error_message = None

                        if hasattr(device, "_error"):
                            try:
                                dev_error = bool(getattr(device, "_error"))
                            except Exception:
                                dev_error = False
                        if (
                            not dev_error
                            and hasattr(device, "to_dict")
                            and callable(device.to_dict)
                        ):
                            try:
                                d = device.to_dict() or {}
                                dev_error = bool(d.get("error", False))
                                dev_error_message = d.get("error_message")
                            except Exception:
                                pass
                        if dev_error_message is None and hasattr(
                            device, "_error_message"
                        ):
                            try:
                                dev_error_message = getattr(
                                    device, "_error_message"
                                )
                            except Exception:
                                dev_error_message = None

                        if dev_error:
                            self._error = True
                            self._error_message = f"{device_name}: {dev_error_message if dev_error_message else 'unknown device error'}"
                            error(
                                f"Detected physical device error → IO ON_ERROR: {self._error_message}",
                                message_logger=self._message_logger,
                            )
                            if self.fsm_state not in {
                                EventListenerState.ON_ERROR,
                                EventListenerState.FAULT,
                            }:
                                self._change_fsm_state(EventListenerState.ON_ERROR)
                                return
                    except Exception as dev_scan_exc:
                        warning(
                            f"Error while scanning physical device '{device_name}': {dev_scan_exc}",
                            message_logger=self._message_logger,
                        )
        except Exception as scan_exc:
            warning(
                f"Error while scanning physical devices: {scan_exc}",
                message_logger=self._message_logger,
            )

        # Proaktywny health-check magistral (eskalacja do ON_ERROR przy problemie)
        self._assert_bus_healthy(escalate_on_failure=True)
```

## Obsługa zdarzeń

Gdy system otrzymuje zdarzenie, analizuje je pod kątem źródła i typu. Na podstawie tych informacji wybierana jest odpowiednia metoda obsługi. Obecnie system jest skonfigurowany głównie do obsługi zdarzeń z komponentu "munchies_algo", ale architektura pozwala na łatwe rozszerzenie o nowe źródła.

Przykładowe fragmenty obsługi i dystrybucji zdarzeń:

```python
async def _analyze_event(self, event: Event) -> Result:
    if self._debug:
        debug(
            f"Analyzing event {event.event_type} from {event.source}",
            message_logger=self._message_logger,
        )
    add_to_processing = await self.device_selector(event)
    if add_to_processing:
        self._add_to_processing(event)
    return True

async def device_selector(self, event: Event) -> bool:
    device_id = event.data.get("device_id")
    if device_id is None:
        error("Device ID not found in event data", message_logger=self._message_logger)
        return False

    event_type = event.event_type
    if not event_type:
        error("Action type is missing in the event", message_logger=self._message_logger)
        return False

    parts = event_type.split("_", 1)
    if len(parts) < 2:
        error(
            f"Invalid event_type format: {event_type}. Expected format: device_action",
            message_logger=self._message_logger,
        )
        return False

    device_prefix = parts[0].lower()
    action = "execute_event"
    device_name = f"{device_prefix}{device_id}"

    if hasattr(self, "virtual_devices") and device_name in self.virtual_devices:
        device = self.virtual_devices[device_name]
        if hasattr(device, action) and callable(getattr(device, action)):
            try:
                event = getattr(device, action)(event)
                if isinstance(event, Event):
                    await self._reply(event)
                    return False
                return True
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

    return False
```

## Przykład praktyczny

W dołączonym przykładzie konfiguracyjnym zdefiniowano:

- Magistralę Modbus RTU na porcie `/dev/ttyUSB0`
- Sterownik silnika TLO57R24V08 z określonym adresem i typem konfiguracji
- Urządzenie wirtualne "feeder1", które udostępnia wysokopoziomowe metody do sterowania podajnikiem

Ta konfiguracja pokazuje, jak system umożliwia abstrakcję złożoności sprzętowej - zamiast bezpośrednio obsługiwać rejestry Modbus, aplikacja może używać intuicyjnych metod jak `run()` czy `stop()`.

## Podsumowanie

System Event Listener, a w szczególności jego implementacja IO_server, zapewnia elastyczne i rozszerzalne środowisko do zarządzania komunikacją z urządzeniami sprzętowymi. Dzięki dynamicznemu ładowaniu konfiguracji, obsłudze zdarzeń i warstwom abstrakcji, umożliwia on tworzenie skalowalnych i łatwych w utrzymaniu systemów sterowania.