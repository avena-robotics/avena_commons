"""
Testy jednostkowe dla SendSmsToCustomerAction.

Testuje funkcjonalność wysyłania SMS-ów do klientów z danymi pobranymi
z triggera scenariusza orchestratora.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from avena_commons.orchestrator.actions.base_action import (
    ActionContext,
    ActionExecutionError,
)
from avena_commons.orchestrator.actions.send_sms_to_customer_action import (
    SendSmsToCustomerAction,
)


class TestSendSmsToCustomerAction:
    """Testy dla akcji send_sms_to_customer."""

    @pytest.fixture
    def action(self):
        """Fikstura z instancją akcji."""
        return SendSmsToCustomerAction()

    @pytest.fixture
    def mock_orchestrator(self):
        """Fikstura z mock orchestratora."""
        orch = MagicMock()
        orch._configuration = {
            "sms": {
                "enabled": True,
                "url": "https://api.multiinfo.plus",
                "login": "test_login",
                "password": "test_password",
                "serviceId": "12345",
                "source": "Avena",
                "max_length": 160,
            }
        }
        orch.should_skip_action_due_to_errors.return_value = False
        orch.get_action_error_count.return_value = 0
        orch.reset_action_error_count = MagicMock()
        orch.increment_action_error_count = MagicMock()
        return orch

    @pytest.fixture
    def mock_context(self, mock_orchestrator):
        """Fikstura z kontekstem akcji."""
        context = MagicMock(spec=ActionContext)
        context.orchestrator = mock_orchestrator
        context.message_logger = MagicMock()
        context.trigger_data = {
            "klienci_powiadomienia": [
                {
                    "id": 1,
                    "imie": "Jan",
                    "nazwisko": "Kowalski",
                    "telefon": "+48123456789",
                    "numer_zamowienia": "ZAM001",
                },
                {
                    "id": 2,
                    "imie": "Anna",
                    "nazwisko": "Nowak",
                    "telefon": "987654321",
                    "numer_zamowienia": "ZAM002",
                },
            ]
        }
        return context

    @pytest.fixture
    def action_config(self):
        """Fikstura z podstawową konfiguracją akcji."""
        return {
            "type": "send_sms_to_customer",
            "phone_field": "telefon",
            "text": "Szanowny/a {{ imie }} {{ nazwisko }}, Twoje zamówienie {{ numer_zamowienia }} jest gotowe.",
        }

    @pytest.mark.asyncio
    async def test_successful_sms_sending(self, action, mock_context, action_config):
        """Test pomyślnego wysłania SMS-ów."""
        with patch("requests.get") as mock_get:
            # Mock odpowiedzi HTTP (sukces MultiInfo Plus)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "0\n1234567890\n"
            mock_get.return_value = mock_response

            # Wykonaj akcję
            await action.execute(action_config, mock_context)

            # Sprawdź czy wywołano odpowiednią liczbę żądań (2 klientów)
            assert mock_get.call_count == 2

            # Sprawdź parametry pierwszego żądania
            first_call_args = mock_get.call_args_list[0]
            params = first_call_args[1]["params"]
            assert params["dest"] == "48123456789"
            assert "Jan Kowalski" in params["text"]
            assert "ZAM001" in params["text"]

            # Sprawdź parametry drugiego żądania
            second_call_args = mock_get.call_args_list[1]
            params = second_call_args[1]["params"]
            assert params["dest"] == "48987654321"
            assert "Anna Nowak" in params["text"]
            assert "ZAM002" in params["text"]

    @pytest.mark.asyncio
    async def test_sms_disabled_globally(self, action, mock_context, action_config):
        """Test gdy SMS jest globalnie wyłączony."""
        mock_context.orchestrator._configuration["sms"]["enabled"] = False

        # Wykonaj akcję - powinna zostać pominięta bez błędu
        await action.execute(action_config, mock_context)

        # Sprawdź czy nie było żądań HTTP
        with patch("requests.get") as mock_get:
            assert mock_get.call_count == 0

    @pytest.mark.asyncio
    async def test_missing_sms_configuration(self, action, mock_context, action_config):
        """Test braku konfiguracji SMS."""
        mock_context.orchestrator._configuration["sms"]["enabled"] = False

        # Akcja powinna zostać pominięta, nie ma błędu
        await action.execute(action_config, mock_context)

    @pytest.mark.asyncio
    async def test_missing_trigger_data(self, action, mock_context, action_config):
        """Test braku danych triggera."""
        mock_context.trigger_data = None

        with pytest.raises(ActionExecutionError) as exc_info:
            await action.execute(action_config, mock_context)

        assert "Brak danych trigger_data" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_empty_customer_list(self, action, mock_context, action_config):
        """Test pustej listy klientów."""
        mock_context.trigger_data = {"some_other_data": []}

        # Akcja powinna zgłosić błąd o braku listy rekordów
        with pytest.raises(ActionExecutionError) as exc_info:
            await action.execute(action_config, mock_context)

        assert "Nie znaleziono listy rekordów klientów" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_phone_field(self, action, mock_context, action_config):
        """Test braku pola z numerem telefonu."""
        # Usuń pole telefon z danych
        for customer in mock_context.trigger_data["klienci_powiadomienia"]:
            del customer["telefon"]

        # Akcja powinna zakończyć się bez błędu (warning o braku numerów)
        await action.execute(action_config, mock_context)

    @pytest.mark.asyncio
    async def test_auto_detect_phone_field(self, action, mock_context, action_config):
        """Test automatycznego wykrywania pola telefonu."""
        # Zmień nazwę pola telefonu
        for customer in mock_context.trigger_data["klienci_powiadomienia"]:
            customer["phone"] = customer.pop("telefon")

        # Usuń phone_field z konfiguracji
        del action_config["phone_field"]

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "0\n1234567890\n"
            mock_get.return_value = mock_response

            await action.execute(action_config, mock_context)

            # Sprawdź czy SMS został wysłany
            assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_sms_sending_failure(self, action, mock_context, action_config):
        """Test niepowodzenia wysyłki SMS."""
        with patch("requests.get") as mock_get:
            # Mock odpowiedzi HTTP (błąd)
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "ERROR: Invalid credentials"
            mock_get.return_value = mock_response

            with pytest.raises(ActionExecutionError) as exc_info:
                await action.execute(action_config, mock_context)

            assert "niepowodzenie wysyłki" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_ignore_errors_flag(self, action, mock_context, action_config):
        """Test flagi ignore_errors."""
        action_config["ignore_errors"] = True

        with patch("requests.get") as mock_get:
            # Mock odpowiedzi HTTP (błąd)
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "ERROR: Invalid credentials"
            mock_get.return_value = mock_response

            # Akcja powinna zakończyć się bez błędu mimo niepowodzenia wysyłki
            await action.execute(action_config, mock_context)

    @pytest.mark.asyncio
    async def test_phone_number_normalization(
        self, action, mock_context, action_config
    ):
        """Test normalizacji numerów telefonów."""
        # Zmień numery na różne formaty
        mock_context.trigger_data["klienci_powiadomienia"][0]["telefon"] = (
            "+48 123 456 789"
        )
        mock_context.trigger_data["klienci_powiadomienia"][1]["telefon"] = "987-654-321"

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "0\n1234567890\n"
            mock_get.return_value = mock_response

            await action.execute(action_config, mock_context)

            # Sprawdź czy numery zostały znormalizowane
            first_call_params = mock_get.call_args_list[0][1]["params"]
            second_call_params = mock_get.call_args_list[1][1]["params"]

            assert first_call_params["dest"] == "48123456789"
            assert second_call_params["dest"] == "48987654321"

    @pytest.mark.asyncio
    async def test_long_message_segmentation(self, action, mock_context, action_config):
        """Test segmentacji długich wiadomości."""
        # Ustaw krótki limit długości
        mock_context.orchestrator._configuration["sms"]["max_length"] = 50

        # Długa wiadomość
        action_config["text"] = (
            "To jest bardzo długa wiadomość SMS która przekroczy limit 50 znaków i zostanie podzielona na segmenty"
        )

        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "0\n1234567890\n"
            mock_get.return_value = mock_response

            await action.execute(action_config, mock_context)

            # Sprawdź czy wysłano więcej niż 2 żądania (2 klientów * więcej segmentów)
            assert mock_get.call_count > 2

    @pytest.mark.asyncio
    async def test_template_variables_resolution(
        self, action, mock_context, action_config
    ):
        """Test rozwiązywania zmiennych szablonu."""
        with patch("requests.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = "0\n1234567890\n"
            mock_get.return_value = mock_response

            await action.execute(action_config, mock_context)

            # Sprawdź czy zmienne zostały zastąpione w pierwszej wiadomości
            first_call_params = mock_get.call_args_list[0][1]["params"]
            text = first_call_params["text"]

            assert "Jan" in text
            assert "Kowalski" in text
            assert "ZAM001" in text
            assert "{{" not in text  # Nie powinno być nierozwiązanych zmiennych

    @pytest.mark.asyncio
    async def test_timeout_handling(self, action, mock_context, action_config):
        """Test obsługi timeout."""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout("Request timeout")

            with pytest.raises(ActionExecutionError):
                await action.execute(action_config, mock_context)

    def test_action_type_property(self, action):
        """Test właściwości action_type."""
        assert action.action_type == "send_sms_to_customer"
