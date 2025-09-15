"""
Komponent email dla orchestratora.

Obsługuje wysyłanie e-maili przez SMTP. Centralizuje konfigurację
i funkcjonalności wspólne dla wszystkich akcji email. Wspiera podstawowe
uwierzytelnianie i TLS/STARTTLS.
"""

import os
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List

from avena_commons.util.logger import debug, error, info, warning


class EmailComponent:
    """
    Komponent do obsługi wysyłania e-maili przez SMTP.

    Centralizuje konfigurację SMTP i udostępnia metody pomocnicze dla akcji email.
    Obsługuje różne tryby bezpieczeństwa (TLS, STARTTLS) i uwierzytelnianie.

    Wymagane parametry w konfiguracji:
    - host: Serwer SMTP (np. smtp.office365.com)
    - port: Port SMTP (domyślnie 587)
    - username: Nazwa użytkownika SMTP
    - password: Hasło SMTP
    - from: Adres nadawcy (opcjonalnie, domyślnie username)
    - starttls: Czy używać STARTTLS (domyślnie True)
    - tls: Czy używać TLS (alternatywa dla STARTTLS, domyślnie False)
    - max_error_attempts: Maksymalna liczba kolejnych błędów przed wyłączeniem (domyślnie 0)
    """

    def __init__(self, name: str, config: Dict[str, Any], message_logger=None):
        """
        Inicjalizuje komponent email.

        Args:
            name: Nazwa komponentu
            config: Konfiguracja komponentu z orchestratora
            message_logger: Logger wiadomości
        """
        self.name = name
        self.config = config
        self._message_logger = message_logger
        self._is_initialized = False

        # Parametry konfiguracji
        self._host = ""
        self._port = 587
        self._username = ""
        self._password = ""
        self._mail_from = ""
        self._use_starttls = True
        self._use_tls = False
        self._max_error_attempts = 0

    def validate_config(self) -> bool:
        """
        Waliduje konfigurację komponentu email.

        Returns:
            True jeśli konfiguracja jest poprawna

        Raises:
            ValueError: Jeśli brakuje wymaganych parametrów
        """
        required_params = ["host", "username", "password"]
        missing_params = []

        for param in required_params:
            # Sprawdź w konfiguracji komponentu
            if param not in self.config or not self.config[param]:
                # Sprawdź w zmiennych środowiskowych (z prefiksem SMTP_)
                env_key = f"SMTP_{param.upper()}"
                if not os.getenv(env_key):
                    missing_params.append(param)

        if missing_params:
            raise ValueError(
                f"Komponent email '{self.name}': brakuje wymaganych parametrów: "
                f"{', '.join(missing_params)}. Sprawdź konfigurację lub zmienne środowiskowe."
            )

        # Waliduj port jako liczbę
        port = self.config.get("port") or os.getenv("SMTP_PORT", "587")
        try:
            int(port)
        except (ValueError, TypeError):
            raise ValueError(
                f"Komponent email '{self.name}': port musi być liczbą, otrzymano: {port}"
            )

        debug(
            f"✅ Walidacja konfiguracji komponentu email '{self.name}' pomyślna",
            message_logger=self._message_logger,
        )

        return True

    async def initialize(self) -> bool:
        """
        Inicjalizuje komponent email.

        Returns:
            True jeśli inicjalizacja przebiegła pomyślnie
        """
        try:
            self.validate_config()

            # Pobierz parametry z konfiguracji lub zmiennych środowiskowych
            self._host = (
                self.config.get("host") or os.getenv("SMTP_HOST") or ""
            ).strip()
            self._username = (
                self.config.get("username") or os.getenv("SMTP_USERNAME") or ""
            ).strip()
            self._password = (
                self.config.get("password") or os.getenv("SMTP_PASSWORD") or ""
            ).strip()

            # Port
            try:
                self._port = int(
                    self.config.get("port") or os.getenv("SMTP_PORT", "587")
                )
            except (ValueError, TypeError):
                self._port = 587

            # Adres nadawcy
            self._mail_from = (
                self.config.get("from") or os.getenv("SMTP_FROM") or self._username
            ).strip()

            # Parametry TLS
            self._use_starttls = bool(self.config.get("starttls", True))
            self._use_tls = bool(self.config.get("tls", False))

            # Parametry opcjonalne
            try:
                self._max_error_attempts = int(self.config.get("max_error_attempts", 0))
            except (ValueError, TypeError):
                self._max_error_attempts = 0

            self._is_initialized = True

            info(
                f"✅ Komponent email '{self.name}' zainicjalizowany pomyślnie",
                message_logger=self._message_logger,
            )

            return True

        except Exception as e:
            error(
                f"❌ Błąd inicjalizacji komponentu email '{self.name}': {e}",
                message_logger=self._message_logger,
            )
            return False

    async def health_check(self) -> bool:
        """
        Sprawdza stan zdrowia komponentu email.

        Returns:
            True jeśli komponent jest gotowy do pracy
        """
        if not self._is_initialized:
            return False

        # Opcjonalnie: spróbuj nawiązać połączenie SMTP jako test zdrowia
        try:
            if self._use_tls:
                with smtplib.SMTP_SSL(
                    host=self._host, port=self._port, timeout=5
                ) as smtp:
                    smtp.ehlo()
            else:
                with smtplib.SMTP(host=self._host, port=self._port, timeout=5) as smtp:
                    smtp.ehlo()
                    if self._use_starttls:
                        smtp.starttls()
                        smtp.ehlo()
            return True
        except Exception as e:
            warning(
                f"Health check komponentu email '{self.name}' nieudany: {e}",
                message_logger=self._message_logger,
            )
            return False

    @property
    def is_initialized(self) -> bool:
        """Zwraca True jeśli komponent jest zainicjalizowany."""
        return self._is_initialized

    @property
    def max_error_attempts(self) -> int:
        """Zwraca maksymalną liczbę kolejnych błędów."""
        return self._max_error_attempts

    def parse_recipients(self, to_field: Any) -> List[str]:
        """
        Parsuje pole odbiorców na listę adresów email.

        Args:
            to_field: Pole odbiorców (string lub lista)

        Returns:
            Lista adresów email

        Raises:
            ValueError: Jeśli lista odbiorców jest pusta
        """
        if not to_field:
            raise ValueError("Brak pola 'to' (lista adresów lub string)")

        recipients: List[str]
        if isinstance(to_field, list):
            recipients = [str(a).strip() for a in to_field if str(a).strip()]
        else:
            recipients = [str(to_field).strip()]

        if not recipients:
            raise ValueError("Lista adresów 'to' jest pusta po przetworzeniu")

        return recipients

    async def send_email(self, recipients: List[str], subject: str, body: str) -> bool:
        """
        Wysyła e-mail do listy odbiorców.

        Args:
            recipients: Lista adresów email
            subject: Temat wiadomości
            body: Treść wiadomości

        Returns:
            True jeśli wysyłka zakończona sukcesem

        Raises:
            RuntimeError: Jeśli komponent nie jest zainicjalizowany
            ValueError: Jeśli brakuje wymaganych danych
        """
        if not self._is_initialized:
            raise RuntimeError(
                f"Komponent email '{self.name}' nie jest zainicjalizowany"
            )

        if not recipients:
            raise ValueError("Lista odbiorców jest pusta")
        if not subject:
            raise ValueError("Brak tematu wiadomości")
        if not body:
            raise ValueError("Brak treści wiadomości")

        # Zbuduj wiadomość
        message = EmailMessage()
        message["From"] = self._mail_from
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(body)

        # Połączenie SMTP i wysyłka
        try:
            if self._use_tls:
                # SMTPS (implicit TLS), zwykle port 465
                with smtplib.SMTP_SSL(host=self._host, port=self._port) as smtp:
                    smtp.ehlo()
                    if self._username and self._password and smtp.has_extn("auth"):
                        smtp.login(self._username, self._password)
                    elif self._username and self._password:
                        warning(
                            f"Serwer SMTP '{self._host}' nie wspiera AUTH - pomijam logowanie",
                            message_logger=self._message_logger,
                        )
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(host=self._host, port=self._port) as smtp:
                    smtp.ehlo()
                    if self._use_starttls:
                        smtp.starttls()
                        smtp.ehlo()
                    if self._username and self._password and smtp.has_extn("auth"):
                        smtp.login(self._username, self._password)
                    elif self._username and self._password:
                        warning(
                            f"Serwer SMTP '{self._host}' nie wspiera AUTH - pomijam logowanie",
                            message_logger=self._message_logger,
                        )
                    smtp.send_message(message)

            info(
                f"📧 E-mail wysłany do {recipients} z tematem '{subject}'",
                message_logger=self._message_logger,
            )
            return True

        except smtplib.SMTPAuthenticationError as e:
            error(
                f"Błąd uwierzytelniania SMTP: {e}",
                message_logger=self._message_logger,
            )
            raise
        except smtplib.SMTPRecipientsRefused as e:
            error(
                f"Odbiorcy odrzuceni przez serwer SMTP: {e}",
                message_logger=self._message_logger,
            )
            raise
        except smtplib.SMTPException as e:
            error(
                f"Błąd SMTP: {e}",
                message_logger=self._message_logger,
            )
            raise
        except Exception as e:
            error(
                f"Nieoczekiwany błąd przy wysyłce e-mail: {e}",
                message_logger=self._message_logger,
            )
            raise

    def get_status(self) -> Dict[str, Any]:
        """
        Zwraca status komponentu email.

        Returns:
            Słownik ze statusem komponentu
        """
        return {
            "name": self.name,
            "type": "email",
            "initialized": self._is_initialized,
            "host": self._host if self._is_initialized else None,
            "port": self._port,
            "mail_from": self._mail_from if self._is_initialized else None,
            "use_starttls": self._use_starttls,
            "use_tls": self._use_tls,
            "max_error_attempts": self._max_error_attempts,
        }

    def to_dict(self) -> Dict[str, Any]:
        """
        Zwraca serializowalną reprezentację komponentu email do JSON.

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
            "component_type": "EmailComponent",
            "config": safe_config,
            "is_initialized": self._is_initialized,
            "host": self._host if self._is_initialized else None,
            "port": self._port,
            "username": self._username if self._is_initialized else None,
            "password": "***" if self._password else None,
            "mail_from": self._mail_from if self._is_initialized else None,
            "use_starttls": self._use_starttls,
            "use_tls": self._use_tls,
            "max_error_attempts": self._max_error_attempts,
            "status": self.get_status(),
        }
