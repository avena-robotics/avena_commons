"""Przykłady urządzeń wirtualnych z różnymi strategiami obsługi błędów urządzeń fizycznych.

Ten moduł demonstruje różne podejścia do izolacji błędów:
1. SimpleFeeder - natychmiastowa eskalacja (domyślna, bezpieczna strategia)
2. RobustFeeder - retry logic z licznikiem prób
3. RedundantFeeder - fallback do zapasowego urządzenia
4. TolerantFeeder - ignorowanie przejściowych błędów

Cel:
- Pokazać jak nadpisać _on_physical_device_error() dla custom logiki
- Zademonstrować różne strategie recovery/retry
- Udokumentować best practices dla error isolation
"""

from avena_commons.event_listener import Event, Result
from avena_commons.io.virtual_device import VirtualDevice, VirtualDeviceState
from avena_commons.util.logger import debug, info, warning


class SimpleFeeder(VirtualDevice):
    """Przykład 1: Bezpieczna strategia - natychmiastowa eskalacja błędu.
    
    Używa domyślnej implementacji _on_physical_device_error(), która
    od razu przełącza VirtualDevice do stanu ERROR przy jakimkolwiek
    błędzie urządzenia fizycznego.
    
    Zalety:
    - Najprostsza implementacja
    - Maksymalne bezpieczeństwo
    - Natychmiastowe powiadomienie operatora
    
    Wady:
    - Brak tolerancji na przejściowe błędy
    - Potencjalnie częste alarmy
    
    Zastosowanie:
    - Systemy krytyczne bezpieczeństwa
    - Prototypowanie nowych urządzeń
    - Gdy pewność działania > dostępność
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._state = VirtualDeviceState.WORKING
        info(
            f"{self.device_name} - SimpleFeeder initialized (fail-fast strategy)",
            message_logger=self._message_logger,
        )

    def get_current_state(self):
        return self._state

    def _instant_execute_event(self, event: Event) -> Event:
        """Przykładowa implementacja - start/stop feedera."""
        action = event.event_type.split("_", 1)[1] if "_" in event.event_type else ""
        
        if action == "start":
            # Wywołaj metodę urządzenia fizycznego
            motor = self.devices.get("motor_driver_1")
            if motor and hasattr(motor, "run_jog"):
                motor.run_jog()
                event.result = Result(result="success")
            else:
                event.result = Result(result="error")
                event.result.error_message = "Motor driver not available"
        elif action == "stop":
            motor = self.devices.get("motor_driver_1")
            if motor and hasattr(motor, "stop"):
                motor.stop()
                event.result = Result(result="success")
            else:
                event.result = Result(result="error")
                event.result.error_message = "Motor driver not available"
        else:
            event.result = Result(result="error")
            event.result.error_message = f"Unknown action: {action}"
        
        return event

    def tick(self):
        """Okresowe sprawdzanie - watchdog i health check są automatyczne."""
        pass


class RobustFeeder(VirtualDevice):
    """Przykład 2: Strategia retry - tolerancja na przejściowe błędy.
    
    Nadpisuje _on_physical_device_error() aby implementować retry logic.
    Po N nieudanych próbach eskaluje do ERROR, wcześniej próbuje odzyskać.
    
    Zalety:
    - Tolerancja na chwilowe problemy komunikacji
    - Automatyczne recovery bez interwencji operatora
    - Mniej false-positive alarmów
    
    Wady:
    - Opóźnienie w wykryciu prawdziwego problemu
    - Wymaga dodatkowej logiki i stanu
    
    Zastosowanie:
    - Systemy produkcyjne z komunikacją przez sieć
    - Urządzenia z przejściowymi problemami (WiFi, RS485)
    - Gdy dostępność > natychmiastowe powiadomienie
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._state = VirtualDeviceState.WORKING
        self._retry_count = 0
        self._max_retries = 3
        self._error_device_name = None
        info(
            f"{self.device_name} - RobustFeeder initialized (retry strategy, max_retries={self._max_retries})",
            message_logger=self._message_logger,
        )

    def _on_physical_device_error(self, device_name: str, error_message: str) -> None:
        """Custom error handler z retry logic."""
        if self._error_device_name != device_name:
            # Nowy błąd na innym urządzeniu - reset licznika
            self._error_device_name = device_name
            self._retry_count = 0
        
        self._retry_count += 1
        
        if self._retry_count >= self._max_retries:
            # Po przekroczeniu limitu - eskaluj do ERROR
            warning(
                f"{self.device_name} - Escalating to ERROR after {self._retry_count} retries for device '{device_name}'",
                message_logger=self._message_logger,
            )
            self.set_state(VirtualDeviceState.ERROR)
            self._error_message = f"Device '{device_name}' error after {self._retry_count} retries: {error_message}"
        else:
            # Jeszcze są próby - loguj i czekaj na auto-recovery
            info(
                f"{self.device_name} - Device '{device_name}' error (retry {self._retry_count}/{self._max_retries}): {error_message}",
                message_logger=self._message_logger,
            )
            # Nie eskalujemy - czekamy aż PhysicalDevice sam się odzyska (clear_error)

    def get_current_state(self):
        return self._state

    def _instant_execute_event(self, event: Event) -> Event:
        """Przykładowa implementacja."""
        action = event.event_type.split("_", 1)[1] if "_" in event.event_type else ""
        
        if action == "start":
            motor = self.devices.get("motor_driver_1")
            if motor and hasattr(motor, "run_jog"):
                motor.run_jog()
                event.result = Result(result="success")
                # Reset retry counter on successful operation
                self._retry_count = 0
                self._error_device_name = None
            else:
                event.result = Result(result="error")
                event.result.error_message = "Motor driver not available"
        else:
            event.result = Result(result="error")
            event.result.error_message = f"Unknown action: {action}"
        
        return event

    def tick(self):
        """Okresowe sprawdzanie."""
        pass


class RedundantFeeder(VirtualDevice):
    """Przykład 3: Strategia fallback - redundancja urządzeń.
    
    Posiada zapasowe urządzenie fizyczne. Gdy główne ma błąd,
    przełącza się automatycznie na backup.
    
    Zalety:
    - Ciągłość działania mimo awarii
    - Automatyczny failover
    - Wysoka dostępność
    
    Wady:
    - Wymaga dodatkowego hardware'u
    - Złożoność konfiguracji
    - Trudniejsze testowanie
    
    Zastosowanie:
    - Krytyczne procesy produkcyjne
    - Systemy 24/7
    - Gdy downtime jest niedopuszczalny
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._state = VirtualDeviceState.WORKING
        self._active_motor = "motor_driver_1"  # Primary
        self._backup_motor = "motor_driver_2"  # Backup
        self._failover_active = False
        info(
            f"{self.device_name} - RedundantFeeder initialized (primary={self._active_motor}, backup={self._backup_motor})",
            message_logger=self._message_logger,
        )

    def _on_physical_device_error(self, device_name: str, error_message: str) -> None:
        """Custom error handler z failover logic."""
        if device_name == self._active_motor and not self._failover_active:
            # Primary device ma błąd - przełącz na backup
            backup = self.devices.get(self._backup_motor)
            if backup:
                info(
                    f"{self.device_name} - Failover: switching from {self._active_motor} to {self._backup_motor}",
                    message_logger=self._message_logger,
                )
                self._active_motor, self._backup_motor = self._backup_motor, self._active_motor
                self._failover_active = True
                # Nie eskalujemy - mamy backup
            else:
                # Brak backup - eskaluj
                warning(
                    f"{self.device_name} - No backup available, escalating to ERROR",
                    message_logger=self._message_logger,
                )
                self.set_state(VirtualDeviceState.ERROR)
                self._error_message = f"Primary device '{device_name}' failed and no backup available: {error_message}"
        elif device_name == self._backup_motor and self._failover_active:
            # Backup device (obecnie aktywny) ma błąd - brak dalszych opcji
            warning(
                f"{self.device_name} - Backup device also failed, escalating to ERROR",
                message_logger=self._message_logger,
            )
            self.set_state(VirtualDeviceState.ERROR)
            self._error_message = f"Both primary and backup devices failed: {error_message}"
        else:
            # Inne urządzenie - loguj ale nie eskaluj
            debug(
                f"{self.device_name} - Non-critical device '{device_name}' error: {error_message}",
                message_logger=self._message_logger,
            )

    def get_current_state(self):
        return self._state

    def _instant_execute_event(self, event: Event) -> Event:
        """Używa aktywnego motora (po ewentualnym failover)."""
        action = event.event_type.split("_", 1)[1] if "_" in event.event_type else ""
        
        if action == "start":
            motor = self.devices.get(self._active_motor)
            if motor and hasattr(motor, "run_jog"):
                motor.run_jog()
                event.result = Result(result="success")
            else:
                event.result = Result(result="error")
                event.result.error_message = f"Active motor {self._active_motor} not available"
        else:
            event.result = Result(result="error")
            event.result.error_message = f"Unknown action: {action}"
        
        return event

    def tick(self):
        """Okresowe sprawdzanie i próba recovery primary device."""
        if self._failover_active:
            # Sprawdź czy primary device się odzyskał
            primary = self.devices.get(self._backup_motor)  # Po swap to jest primary
            if primary and hasattr(primary, "get_state"):
                from avena_commons.io.device import PhysicalDeviceState
                if primary.get_state() == PhysicalDeviceState.WORKING:
                    info(
                        f"{self.device_name} - Primary device recovered, switching back",
                        message_logger=self._message_logger,
                    )
                    # Przywróć oryginalną konfigurację
                    self._active_motor, self._backup_motor = self._backup_motor, self._active_motor
                    self._failover_active = False


class TolerantFeeder(VirtualDevice):
    """Przykład 4: Strategia tolerancji - graceful degradation.
    
    Ignoruje błędy urządzeń pomocniczych (np. czujniki),
    eskaluje tylko błędy urządzeń krytycznych (np. napędy).
    
    Zalety:
    - Ciągłość działania mimo częściowej awarii
    - Świadoma degradacja funkcjonalności
    - Optymalne balance bezpieczeństwo/dostępność
    
    Wady:
    - Wymaga klasyfikacji urządzeń (critical/non-critical)
    - Możliwa praca w trybie ograniczonym
    - Trudniejsze zarządzanie stanem
    
    Zastosowanie:
    - Systemy z wieloma czujnikami
    - Gdy niektóre funkcje są opcjonalne
    - Systemy z prioritetami operacji
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._state = VirtualDeviceState.WORKING
        # Klasyfikacja urządzeń
        self._critical_devices = {"motor_driver_1"}  # Błąd → ERROR
        self._non_critical_devices = {"sensor_1", "sensor_2"}  # Błąd → log only
        info(
            f"{self.device_name} - TolerantFeeder initialized (critical={self._critical_devices}, non-critical={self._non_critical_devices})",
            message_logger=self._message_logger,
        )

    def _on_physical_device_error(self, device_name: str, error_message: str) -> None:
        """Custom error handler z klasyfikacją urządzeń."""
        if device_name in self._critical_devices:
            # Urządzenie krytyczne - eskaluj
            warning(
                f"{self.device_name} - Critical device '{device_name}' error, escalating to ERROR",
                message_logger=self._message_logger,
            )
            self.set_state(VirtualDeviceState.ERROR)
            self._error_message = f"Critical device '{device_name}' error: {error_message}"
        elif device_name in self._non_critical_devices:
            # Urządzenie pomocnicze - loguj i kontynuuj
            info(
                f"{self.device_name} - Non-critical device '{device_name}' error, continuing with degraded functionality: {error_message}",
                message_logger=self._message_logger,
            )
            # Nie eskalujemy - system może działać bez tego urządzenia
        else:
            # Nieznane urządzenie - zachowawcza strategia: eskaluj
            warning(
                f"{self.device_name} - Unknown device '{device_name}' error, escalating to ERROR as safety measure",
                message_logger=self._message_logger,
            )
            self.set_state(VirtualDeviceState.ERROR)
            self._error_message = f"Unknown device '{device_name}' error: {error_message}"

    def get_current_state(self):
        return self._state

    def _instant_execute_event(self, event: Event) -> Event:
        """Przykładowa implementacja."""
        action = event.event_type.split("_", 1)[1] if "_" in event.event_type else ""
        
        if action == "start":
            motor = self.devices.get("motor_driver_1")
            if motor and hasattr(motor, "run_jog"):
                motor.run_jog()
                event.result = Result(result="success")
            else:
                event.result = Result(result="error")
                event.result.error_message = "Motor driver not available"
        else:
            event.result = Result(result="error")
            event.result.error_message = f"Unknown action: {action}"
        
        return event

    def tick(self):
        """Okresowe sprawdzanie."""
        pass


# Dokumentacja w formie docstring dla użytkowników
"""
PODSUMOWANIE STRATEGII OBSŁUGI BŁĘDÓW:

1. **SimpleFeeder** - Domyślna (fail-fast)
   - Użyj gdy: Bezpieczeństwo > Dostępność
   - Implementacja: Brak nadpisania _on_physical_device_error()
   
2. **RobustFeeder** - Retry logic
   - Użyj gdy: Przejściowe błędy komunikacji są spodziewane
   - Implementacja: Licznik retry w _on_physical_device_error()
   
3. **RedundantFeeder** - Failover
   - Użyj gdy: Masz redundantne urządzenia hardware
   - Implementacja: Przełączanie active_motor w _on_physical_device_error()
   
4. **TolerantFeeder** - Graceful degradation
   - Użyj gdy: Część urządzeń jest opcjonalna
   - Implementacja: Klasyfikacja critical/non-critical w _on_physical_device_error()

BEST PRACTICES:

1. Zawsze loguj decyzje error handling (info/warning/error)
2. Reset liczników po udanych operacjach
3. Dokumentuj w docstring strategię użytą w klasie
4. Testuj scenariusze błędów przed wdrożeniem
5. Monitoruj częstość retry/failover w produkcji

ANTY-WZORCE:

❌ Ignorowanie błędów bez logowania
❌ Nieskończone retry bez limitu
❌ Brak rozróżnienia przejściowy/permanentny błąd
❌ Eskalacja błędów pomocniczych czujników jak krytycznych awarii napędów
"""
