"""
AI: Warunek orchestratora sprawdzający błędy urządzeń wirtualnych.
Wejście: client, device_pattern, extract_id_to, extract_physical_device_to, extract_error_message_to.
Wyjście: bool (True jeśli urządzenie pasujące do wzorca jest w błędzie) + ekstrahowane dane do kontekstu.
"""

import re

from ..base.base_condition import BaseCondition


class VirtualDeviceErrorCondition(BaseCondition):
    """Sprawdza czy urządzenia wirtualne pasujące do wzorca są w błędzie.

    Warunek pozwala na wykrywanie błędów urządzeń wirtualnych na podstawie wzorca nazwy
    oraz opcjonalne wyekstrahowanie szczegółowych informacji do kontekstu scenariusza.

    Args:
        config (dict): Konfiguracja warunku zawierająca:
            - client (str): Nazwa klienta IO w orchestratorze.
            - device_pattern (str): Wzorzec nazwy urządzenia (np. "feeder", "chamber").
            - extract_id_to (str, optional): Nazwa zmiennej kontekstu dla ID urządzenia wirtualnego.
            - extract_physical_device_to (str, optional): Nazwa zmiennej kontekstu dla nazwy urządzenia fizycznego.
            - extract_error_message_to (str, optional): Nazwa zmiennej kontekstu dla wiadomości błędu.
            - extract_device_type_to (str, optional): Nazwa zmiennej kontekstu dla typu urządzenia fizycznego.

    Returns:
        bool: True jeśli znaleziono urządzenie pasujące do wzorca w stanie ERROR.

    Raises:
        ValueError: Gdy brak wymaganych parametrów client lub device_pattern.

    Examples:
        Przykład konfiguracji warunku w scenariuszu JSON:
        ```json
        {
          "trigger": {
            "conditions": {
              "virtual_device_error": {
                "client": "io",
                "device_pattern": "feeder",
                "extract_id_to": "wydawka_id",
                "extract_physical_device_to": "physical_device_name",
                "extract_error_message_to": "error_message",
                "extract_device_type_to": "device_type"
              }
            }
          }
        }
        ```

        Dla urządzenia "feeder1" w błędzie spowodowanym przez "sterownik_modbus":
        - Warunek zwróci True
        - context.wydawka_id = "1"
        - context.physical_device_name = "sterownik_modbus"
        - context.error_message = "Communication timeout"
        - context.device_type = "TLC57R24V08"
    """

    async def evaluate(self, context) -> bool:
        """Ewaluuje warunek sprawdzając błędy urządzeń wirtualnych.

        Args:
            context: Kontekst scenariusza zawierający clients (dane z IO) i context (zmienne).

        Returns:
            bool: True jeśli znaleziono urządzenie pasujące do wzorca w błędzie, False w przeciwnym razie.
        """
        client_name = self.config.get("client")
        device_pattern = self.config.get("device_pattern")
        extract_id_to = self.config.get("extract_id_to")
        extract_physical_device_to = self.config.get("extract_physical_device_to")
        extract_error_message_to = self.config.get("extract_error_message_to")
        extract_device_type_to = self.config.get("extract_device_type_to")

        if not client_name or not device_pattern:
            return False

        client_data = context.clients.get(client_name, {})
        client_state = client_data.get("state", {})
        io_server = client_state.get("io_server", {})
        failed_devices = io_server.get("failed_virtual_devices", {})

        for device_name, device_info in failed_devices.items():
            if device_pattern in device_name:
                # Ekstrahuj ID urządzenia wirtualnego (np. "feeder1" -> "1")
                if extract_id_to and hasattr(context, "set"):
                    match = re.search(r"(\d+)$", device_name)
                    if match:
                        context.set(extract_id_to, match.group(1))

                # Ekstrahuj informacje o urządzeniach fizycznych
                failed_physical = device_info.get("failed_physical_devices", {})

                if failed_physical:
                    # Pobierz pierwsze urządzenie fizyczne (lub można wszystkie)
                    first_physical_name = next(iter(failed_physical.keys()), None)

                    if first_physical_name:
                        physical_info = failed_physical[first_physical_name]

                        # Ekstrahuj nazwę urządzenia fizycznego
                        if extract_physical_device_to and hasattr(context, "set"):
                            context.set(extract_physical_device_to, first_physical_name)

                        # Ekstrahuj wiadomość błędu z urządzenia fizycznego
                        if extract_error_message_to and hasattr(context, "set"):
                            error_msg = physical_info.get(
                                "error_message", "Unknown error"
                            )
                            context.set(extract_error_message_to, error_msg)

                        # Ekstrahuj typ urządzenia fizycznego
                        if extract_device_type_to and hasattr(context, "set"):
                            device_type = physical_info.get("device_type", "Unknown")
                            context.set(extract_device_type_to, device_type)

                return True

        return False
