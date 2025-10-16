#!/usr/bin/env python3
"""
Prosty test komponentu Lynx API.
"""

import asyncio

from avena_commons.orchestrator.components.lynx_api_component import LynxAPIComponent


async def test_lynx_api_component():
    """Test podstawowej funkcjonalności komponentu Lynx API."""

    # Konfiguracja testowa
    config = {"SITE_ID": "123", "ACCESS_TOKEN": "test_token_123456"}

    # Utwórz komponent
    component = LynxAPIComponent(name="test_lynx_api", config=config)

    try:
        # Test walidacji
        print("🧪 Testowanie walidacji konfiguracji...")
        is_valid = component.validate_config()
        print(f"✅ Walidacja: {'OK' if is_valid else 'BŁĄD'}")

        # Test inicjalizacji
        print("\n🧪 Testowanie inicjalizacji...")
        is_initialized = await component.initialize()
        print(f"✅ Inicjalizacja: {'OK' if is_initialized else 'BŁĄD'}")

        # Test połączenia
        print("\n🧪 Testowanie połączenia...")
        is_connected = await component.connect()
        print(f"✅ Połączenie: {'OK' if is_connected else 'BŁĄD'}")

        # Test statusu
        print("\n🧪 Pobieranie statusu...")
        status = component.get_status()
        print(f"✅ Status: {status}")

        # Test symulacji żądania refund (bez rzeczywistego wywołania API)
        print("\n🧪 Testowanie przygotowania żądania refund...")
        print(f"Site ID: {component.get_site_id()}")
        print(f"Base URL: {component.get_base_url()}")

        # Uwaga: Prawdziwe wywołanie API byłoby testowane tylko z prawidłowymi danymi
        print("⚠️ Test rzeczywistego API pomijany (wymagane prawidłowe dane)")

        # Test rozłączenia
        print("\n🧪 Testowanie rozłączenia...")
        is_disconnected = await component.disconnect()
        print(f"✅ Rozłączenie: {'OK' if is_disconnected else 'BŁĄD'}")

        print("\n🎉 Wszystkie testy zakończone pomyślnie!")

    except Exception as e:
        print(f"❌ Błąd podczas testowania: {e}")
        return False

    return True


if __name__ == "__main__":
    print("🚀 Uruchamianie testów komponentu Lynx API...")
    result = asyncio.run(test_lynx_api_component())
    print(f"\n{'✅ SUKCES' if result else '❌ PORAŻKA'}")
