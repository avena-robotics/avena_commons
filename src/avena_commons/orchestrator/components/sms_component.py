"""
Komponent SMS dla orchestratora.

Obsługuje wysyłanie SMS-ów przez MultiInfo Plus API (Api61).
Centralizuje konfigurację i funkcjonalności wspólne dla wszystkich akcji SMS.
Zawiera metody normalizacji numerów, segmentacji wiadomości i wysyłki SMS.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from avena_commons.util.logger import debug, error, info, warning


class SmsComponent:
    """
    Komponent do obsługi wysyłania SMS-ów przez MultiInfo Plus API.

    Centralizuje konfigurację SMS i udostępnia metody pomocnicze dla akcji.
    Obsługuje normalizację numerów telefonów, segmentację długich wiadomości
    i wysyłanie SMS-ów z obsługą błędów.

    Wymagane parametry w konfiguracji:
    - url: URL bazowy API SMS (np. https://api2.multiinfo.plus.pl/Api61/)
    - login: Login do API SMS
    - password: Hasło do API SMS
    - serviceId: ID usługi SMS
    - source: Nadawca SMS (np. "AVENA")
    - enabled: Czy SMS jest włączony (bool)
    - cert_path: Ścieżka do certyfikatu TLS (opcjonalnie)
    - max_length: Maksymalna długość segmentu SMS (domyślnie 160)
    - max_error_attempts: Maksymalna liczba kolejnych błędów przed wyłączeniem (domyślnie 0)
    """

    def __init__(self, name: str, config: Dict[str, Any], message_logger=None):
        """
        Inicjalizuje komponent SMS.

        Args:
            name: Nazwa komponentu
            config: Konfiguracja komponentu z orchestratora
            message_logger: Logger wiadomości
        """
        self.name = name
        self.config = config
        self._message_logger = message_logger
        self._is_initialized = False
        self._is_enabled = False

        # Parametry konfiguracji
        self._url_base = ""
        self._login = ""
        self._password = ""
        self._service_id = None
        self._source = ""
        self._cert_path = None
        self._max_length = 160
        self._max_error_attempts = 0

    def validate_config(self) -> bool:
        """
        Waliduje konfigurację komponentu SMS.

        Returns:
            True jeśli konfiguracja jest poprawna

        Raises:
            ValueError: Jeśli brakuje wymaganych parametrów
        """
        required_params = ["url", "login", "password", "serviceId", "source"]
        missing_params = []

        for param in required_params:
            # Sprawdź w konfiguracji komponentu
            if param not in self.config or not self.config[param]:
                # Sprawdź w zmiennych środowiskowych (z prefiksem SMS_)
                env_key = f"SMS_{param.upper()}"
                if not os.getenv(env_key):
                    missing_params.append(param)

        if missing_params:
            raise ValueError(
                f"Komponent SMS '{self.name}': brakuje wymaganych parametrów: "
                f"{', '.join(missing_params)}. Sprawdź konfigurację lub zmienne środowiskowe."
            )

        # Waliduj serviceId jako liczbę
        service_id = self.config.get("serviceId") or os.getenv("SMS_SERVICEID")
        try:
            int(service_id)
        except (ValueError, TypeError):
            raise ValueError(
                f"Komponent SMS '{self.name}': serviceId musi być liczbą, otrzymano: {service_id}"
            )

        debug(
            f"✅ Walidacja konfiguracji komponentu SMS '{self.name}' pomyślna",
            message_logger=self._message_logger,
        )

        return True

    async def initialize(self) -> bool:
        """
        Inicjalizuje komponent SMS.

        Returns:
            True jeśli inicjalizacja przebiegła pomyślnie
        """
        try:
            self.validate_config()

            # Pobierz parametry z konfiguracji lub zmiennych środowiskowych
            self._url_base = (
                self.config.get("url") or os.getenv("SMS_URL") or ""
            ).strip()
            self._login = (
                self.config.get("login") or os.getenv("SMS_LOGIN") or ""
            ).strip()
            self._password = (
                self.config.get("password") or os.getenv("SMS_PASSWORD") or ""
            ).strip()
            self._service_id = self.config.get("serviceId") or os.getenv(
                "SMS_SERVICEID"
            )
            self._source = (
                self.config.get("source") or os.getenv("SMS_SOURCE") or ""
            ).strip()
            self._cert_path = (
                self.config.get("cert_path") or os.getenv("SMS_CERT_PATH") or ""
            ).strip() or None

            # Parametry opcjonalne
            self._is_enabled = bool(self.config.get("enabled", False))
            try:
                self._max_length = int(self.config.get("max_length", 160))
            except (ValueError, TypeError):
                self._max_length = 160

            try:
                self._max_error_attempts = int(self.config.get("max_error_attempts", 0))
            except (ValueError, TypeError):
                self._max_error_attempts = 0

            self._is_initialized = True

            info(
                f"✅ Komponent SMS '{self.name}' zainicjalizowany pomyślnie",
                message_logger=self._message_logger,
            )

            return True

        except Exception as e:
            error(
                f"❌ Błąd inicjalizacji komponentu SMS '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            return False

    async def connect(self) -> bool:
        """
        Nawiązuje połączenie z serwisem SMS API.

        Returns:
            True jeśli połączenie zostało nawiązane pomyślnie
        """
        if not self._is_initialized:
            error(
                f"❌ Komponent SMS '{self.name}' nie jest zainicjalizowany",
                message_logger=self._message_logger,
            )
            return False

        if not self._is_enabled:
            info(
                f"ℹ️ Komponent SMS '{self.name}' jest wyłączony - pomijam nawiązywanie połączenia",
                message_logger=self._message_logger,
            )
            return True  # Uznajemy za sukces jeśli komponent jest wyłączony

        try:
            info(
                f"🔌 Sprawdzanie połączenia z API SMS: {self.name}",
                message_logger=self._message_logger,
            )

            # Test połączenia z API SMS przez prosty request
            test_url = (
                self._url_base.rstrip("/") + "/ping"
            )  # Próba ping endpointu (jeśli istnieje)

            try:
                # Spróbuj prostego requestu do API (z timeoutem)
                response = requests.head(
                    self._url_base.rstrip("/"), cert=self._cert_path, timeout=10
                )
                # Akceptuj różne kody odpowiedzi jako znak że serwer odpowiada
                if response.status_code < 500:  # Nie błąd serwera
                    info(
                        f"✅ Połączenie z API SMS '{self.name}' sprawdzone pomyślnie (status: {response.status_code})",
                        message_logger=self._message_logger,
                    )
                    return True
                else:
                    warning(
                        f"⚠️ API SMS '{self.name}' odpowiada błędem serwera (status: {response.status_code}), ale połączenie możliwe",
                        message_logger=self._message_logger,
                    )
                    return True  # Nawet błąd serwera oznacza że można się połączyć
            except requests.exceptions.Timeout:
                warning(
                    f"⚠️ Timeout przy sprawdzaniu połączenia z API SMS '{self.name}' - może być niedostępne",
                    message_logger=self._message_logger,
                )
                return False
            except requests.exceptions.ConnectionError:
                error(
                    f"❌ Nie można nawiązać połączenia z API SMS '{self.name}'",
                    message_logger=self._message_logger,
                )
                return False
            except requests.exceptions.RequestException as e:
                warning(
                    f"⚠️ Błąd przy sprawdzaniu połączenia z API SMS '{self.name}': {e}",
                    message_logger=self._message_logger,
                )
                return True  # Różne błędy HTTP mogą oznaczać że API działa

        except Exception as e:
            error(
                f"❌ Błąd połączenia z API SMS '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            return False

    async def disconnect(self) -> bool:
        """
        Rozłącza połączenie z serwisem SMS API.

        Dla komponentu SMS nie ma trwałego połączenia do rozłączenia,
        więc metoda zawsze zwraca True.

        Returns:
            True zawsze (metoda dla kompatybilności z interfejsem)
        """
        debug(
            f"🔌 Rozłączanie komponentu SMS '{self.name}' (brak trwałego połączenia)",
            message_logger=self._message_logger,
        )
        return True

    async def health_check(self) -> bool:
        """
        Sprawdza stan zdrowia komponentu SMS.

        Returns:
            True jeśli komponent jest gotowy do pracy
        """
        if not self._is_initialized:
            return False

        if not self._is_enabled:
            debug(
                f"Komponent SMS '{self.name}' jest wyłączony",
                message_logger=self._message_logger,
            )
            return False

        return True

    @property
    def is_initialized(self) -> bool:
        """Zwraca True jeśli komponent jest zainicjalizowany."""
        return self._is_initialized

    @property
    def is_enabled(self) -> bool:
        """Zwraca True jeśli SMS jest włączony."""
        return self._is_enabled

    @property
    def max_error_attempts(self) -> int:
        """Zwraca maksymalną liczbę kolejnych błędów."""
        return self._max_error_attempts

    def normalize_phone_number(self, number: str) -> str:
        """
        Normalizuje numer telefonu do formatu obsługiwanego przez API SMS.

        Args:
            number: Surowy numer telefonu

        Returns:
            Znormalizowany numer w formacie 48XXXXXXXXX
        """
        n = (number or "").strip()
        if n.startswith("+48"):
            n = n[1:]  # usuń '+' → '48...'
        n = n.replace(" ", "").replace("-", "")
        if not n.startswith("48") and len(n) == 9 and n.isdigit():
            n = f"48{n}"
        return n

    def split_text_into_segments(
        self, message: str, max_length: Optional[int] = None
    ) -> List[str]:
        """
        Dzieli długą wiadomość na segmenty o maksymalnej długości.

        Args:
            message: Wiadomość do podziału
            max_length: Maksymalna długość segmentu (domyślnie z konfiguracji)

        Returns:
            Lista segmentów wiadomości
        """
        if max_length is None:
            max_length = self._max_length

        if not message:
            return [""]
        if len(message) <= max_length:
            return [message]

        segments: List[str] = []
        start = 0
        while start < len(message):
            end = start + max_length
            segments.append(message[start:end])
            start = end
        return segments

    async def send_sms(
        self, recipients: List[str], message: str, ignore_errors: bool = False
    ) -> Tuple[bool, int, List[str]]:
        """
        Wysyła SMS do listy odbiorców.

        Args:
            recipients: Lista numerów telefonów
            message: Treść wiadomości
            ignore_errors: Czy ignorować błędy wysyłki

        Returns:
            Tuple (wszystkie_ok, liczba_wysłanych, lista_błędów)

        Raises:
            RuntimeError: Jeśli komponent nie jest zainicjalizowany lub włączony
        """
        if not self._is_initialized:
            raise RuntimeError(f"Komponent SMS '{self.name}' nie jest zainicjalizowany")

        if not self._is_enabled:
            warning(
                f"SMS globalnie wyłączony - pomijam wysyłkę",
                message_logger=self._message_logger,
            )
            return True, 0, []

        # Podziel wiadomość na segmenty
        segments = self.split_text_into_segments(message)
        endpoint = "sendsms.aspx"
        full_url = self._url_base.rstrip("/") + "/" + endpoint

        all_ok = True
        sent_count = 0
        errors = []

        for raw_dest in recipients:
            dest = self.normalize_phone_number(raw_dest)
            recipient_ok = True

            for idx, segment in enumerate(segments, start=1):
                try:
                    params = {
                        "login": self._login,
                        "password": self._password,
                        "serviceId": self._service_id,
                        "orig": self._source,
                        "dest": dest,
                        "text": segment,
                    }

                    response = requests.get(
                        full_url, params=params, cert=self._cert_path, timeout=30
                    )

                    # Ocena sukcesu (dostosowana do MultiInfo Plus)
                    ok, sms_id_info = self._evaluate_sms_response(response)

                    if ok:
                        info(
                            f"📱 SMS wysłany do {dest} (segment {idx}/{len(segments)})"
                            f"{(' (id: ' + sms_id_info + ')') if sms_id_info else ''}. "
                            f"Treść: {segment}",
                            message_logger=self._message_logger,
                        )
                    else:
                        recipient_ok = False
                        all_ok = False
                        error_msg = f"Niepowodzenie wysyłki do {dest} (segment {idx}/{len(segments)}): {response.status_code} - {response.text}"
                        errors.append(error_msg)
                        error(
                            error_msg,
                            message_logger=self._message_logger,
                        )
                        if not ignore_errors:
                            break

                except requests.exceptions.Timeout:
                    recipient_ok = False
                    all_ok = False
                    error_msg = (
                        f"Timeout wysyłki SMS do {dest} (segment {idx}/{len(segments)})"
                    )
                    errors.append(error_msg)
                    error(error_msg, message_logger=self._message_logger)
                    if not ignore_errors:
                        break

                except requests.exceptions.RequestException as e:
                    recipient_ok = False
                    all_ok = False
                    error_msg = f"Błąd HTTP przy wysyłce SMS do {dest} (segment {idx}/{len(segments)}): {e}"
                    errors.append(error_msg)
                    error(error_msg, message_logger=self._message_logger)
                    if not ignore_errors:
                        break

                except Exception as e:
                    recipient_ok = False
                    all_ok = False
                    error_msg = f"Nieoczekiwany błąd przy wysyłce SMS do {dest} (segment {idx}/{len(segments)}): {e}"
                    errors.append(error_msg)
                    error(error_msg, message_logger=self._message_logger)
                    if not ignore_errors:
                        break

            if recipient_ok:
                sent_count += 1

        info(
            f"Zakończono wysyłkę SMS - pomyślnie wysłano do {sent_count}/{len(recipients)} adresatów",
            message_logger=self._message_logger,
        )

        return all_ok, sent_count, errors

    def _evaluate_sms_response(
        self, response: requests.Response
    ) -> Tuple[bool, Optional[str]]:
        """
        Ocenia odpowiedź z API SMS i zwraca status oraz ID wiadomości.

        Args:
            response: Odpowiedź HTTP z API SMS

        Returns:
            Tuple (sukces, sms_id)
        """
        ok = False
        sms_id_info = None

        if response.status_code == 200:
            body = (response.text or "").strip()
            tokens = [t for t in body.replace(";", " ").split() if t]
            if tokens:
                first = tokens[0]
                if first.lstrip("-").isdigit():
                    try:
                        code_or_id = int(first)
                        if code_or_id >= 0:
                            ok = True
                            if len(tokens) > 1 and tokens[1].isdigit():
                                sms_id_info = tokens[1]
                            elif code_or_id > 0:
                                sms_id_info = str(code_or_id)
                    except ValueError:
                        ok = False
                elif "OK" in body.upper():
                    ok = True

        return ok, sms_id_info

    def get_status(self) -> Dict[str, Any]:
        """
        Zwraca status komponentu SMS.

        Returns:
            Słownik ze statusem komponentu
        """
        return {
            "name": self.name,
            "type": "sms",
            "initialized": self._is_initialized,
            "enabled": self._is_enabled,
            "url": self._url_base if self._is_initialized else None,
            "source": self._source if self._is_initialized else None,
            "max_length": self._max_length,
            "max_error_attempts": self._max_error_attempts,
        }

    def to_dict(self) -> Dict[str, Any]:
        """
        Zwraca serializowalną reprezentację komponentu SMS do JSON.

        Zawiera konfigurację i stan komponentu, ukrywając wrażliwe dane
        takie jak hasła przed serializacją.

        Returns:
            Słownik z ustawieniami i stanem komponentu gotowy do serializacji JSON
        """
        # Przygotuj bezpieczną kopię konfiguracji bez hasła
        safe_config = self.config.copy()
        if "password" in safe_config:
            safe_config["password"] = "***"

        return {
            "component_name": self.name,
            "component_type": "SmsComponent",
            "config": safe_config,
            "is_initialized": self._is_initialized,
            "is_enabled": self._is_enabled,
            "url_base": self._url_base if self._is_initialized else None,
            "login": self._login if self._is_initialized else None,
            "password": "***" if self._password else None,
            "service_id": self._service_id if self._is_initialized else None,
            "source": self._source if self._is_initialized else None,
            "cert_path": self._cert_path if self._is_initialized else None,
            "max_length": self._max_length,
            "max_error_attempts": self._max_error_attempts,
            "status": self.get_status(),
        }
