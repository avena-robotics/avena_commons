#!/usr/bin/env python3
"""
Test komponentu Lynx API dla realnej transakcji.

Testuje funkcjonalność refund dla rzeczywistej transakcji
z podanymi parametrami: transaction_id: 2356298954, site_id: 2
"""

import asyncio
import os
import sys
from pathlib import Path

# Dodaj ścieżkę do modułów
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Załaduj zmienne z .env
try:
    from dotenv import load_dotenv
    # Plik .env jest w katalogu orchestrator
    env_path = Path(__file__).parent / '.env'
    load_dotenv(env_path)
    print(f"🔧 Załadowano .env z: {env_path}")
except ImportError:
    print("⚠️ python-dotenv nie zainstalowane, używam zmiennych systemowych")
except Exception as e:
    print(f"⚠️ Błąd ładowania .env: {e}")

from avena_commons.orchestrator.components.lynx_api_component import LynxAPIComponent


async def test_real_lynx_transaction():
    """
    Test refund dla realnej transakcji.
    
    Parametry testowe:
    - Transaction ID: 2356298954
    - Site ID: 2
    """
    
    print("🚀 Test komponentu Lynx API dla realnej transakcji")
    print("="*60)
    
    # Parametry rzeczywistej transakcji
    REAL_TRANSACTION_ID = 2356298954
    REAL_SITE_ID = int(os.getenv("SITE_ID", "2"))  # Z .env lub domyślnie 2
    
    # Sprawdź czy ACCESS_TOKEN jest dostępny
    access_token = os.getenv("ACCESS_TOKEN")
    if not access_token:
        print("❌ BŁĄD: Brak ACCESS_TOKEN w zmiennych środowiskowych")
        print("   Ustaw zmienną: export ACCESS_TOKEN='your_token_here'")
        return False
    
    print(f"✅ ACCESS_TOKEN znaleziony (pierwsze 10 znaków): {access_token[:10]}...")
    print(f"🎯 Transaction ID: {REAL_TRANSACTION_ID}")
    print(f"🏢 Site ID: {REAL_SITE_ID}")
    
    # Konfiguracja komponentu z rzeczywistymi danymi
    config = {
        "SITE_ID": str(REAL_SITE_ID),
        "ACCESS_TOKEN": access_token
    }
    
    # Utwórz komponent
    component = LynxAPIComponent(
        name="test_real_lynx_api",
        config=config
    )
    
    try:
        print("\n🔧 FAZA 1: Walidacja i inicjalizacja")
        print("-" * 40)
        
        # Test walidacji konfiguracji
        print("📋 Walidacja konfiguracji...")
        is_valid = component.validate_config()
        print(f"   {'✅' if is_valid else '❌'} Walidacja: {'OK' if is_valid else 'BŁĄD'}")
        
        if not is_valid:
            print("❌ Walidacja nieudana - przerywam test")
            return False
        
        # Test inicjalizacji
        print("⚙️  Inicjalizacja komponentu...")
        is_initialized = await component.initialize()
        print(f"   {'✅' if is_initialized else '❌'} Inicjalizacja: {'OK' if is_initialized else 'BŁĄD'}")
        
        if not is_initialized:
            print("❌ Inicjalizacja nieudana - przerywam test")
            return False
        
        # Test połączenia
        print("🔌 Test połączenia...")
        is_connected = await component.connect()
        print(f"   {'✅' if is_connected else '❌'} Połączenie: {'OK' if is_connected else 'BŁĄD'}")
        
        # Sprawdź status komponentu
        print("\n📊 FAZA 2: Status komponentu")
        print("-" * 40)
        status = component.get_status()
        print(f"📋 Status komponentu:")
        for key, value in status.items():
            print(f"   {key}: {value}")
        
        # Potwierdzenie przed wysłaniem żądania
        print(f"\n⚠️  UWAGA: Zamierzasz wysłać PRAWDZIWE żądanie refund!")
        print(f"   Transaction ID: {REAL_TRANSACTION_ID}")
        print(f"   Site ID: {REAL_SITE_ID}")
        print(f"   URL: {component.get_base_url()}/operational/v1/payment/refund-request")
        
        response = input("\nCzy kontynuować wysyłanie żądania refund? (tak/nie): ").strip().lower()
        
        if response not in ['tak', 'yes', 'y', 't']:
            print("❌ Test anulowany przez użytkownika")
            return False
        
        print("\n🚀 FAZA 3: Wysyłanie żądania refund")
        print("-" * 40)
        
        # Parametry żądania refund
        refund_params = {
            "transaction_id": REAL_TRANSACTION_ID,
            "refund_amount": 0,  # Domyślnie 0 - pełny refund
            "refund_reason": "Test refund z orchestratora - transakcja testowa",
            "refund_email_list": ""  # Opcjonalnie można dodać email
        }
        
        print("📝 Parametry żądania:")
        for key, value in refund_params.items():
            print(f"   {key}: {value}")
        
        # Wysyłanie żądania refund
        print(f"\n🚀 Wysyłanie żądania refund...")
        result = await component.send_refund_request(**refund_params)
        
        print(f"\n📋 WYNIK ŻĄDANIA:")
        print(f"   Success: {result.get('success')}")
        print(f"   Status Code: {result.get('status_code', 'brak')}")
        print(f"   Transaction ID: {result.get('transaction_id')}")
        
        if result.get('success'):
            print("✅ ŻĄDANIE REFUND WYSŁANE POMYŚLNIE!")
            print(f"📄 Odpowiedź z API:")
            response_data = result.get('response', {})
            for key, value in response_data.items():
                print(f"   {key}: {value}")
        else:
            print("❌ ŻĄDANIE REFUND NIEUDANE!")
            print(f"🔍 Błąd: {result.get('error', 'Nieznany błąd')}")
        
        # Test rozłączenia
        print(f"\n🔌 FAZA 4: Rozłączenie")
        print("-" * 40)
        is_disconnected = await component.disconnect()
        print(f"✅ Rozłączenie: {'OK' if is_disconnected else 'BŁĄD'}")
        
        print(f"\n{'🎉 TEST ZAKOŃCZONY POMYŚLNIE!' if result.get('success') else '⚠️ TEST ZAKOŃCZONY Z BŁĘDAMI'}")
        return result.get('success', False)
        
    except Exception as e:
        print(f"❌ BŁĄD PODCZAS TESTOWANIA: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_lynx_component_validation_only():
    """
    Test tylko walidacji i konfiguracji bez wysyłania żądania.
    """
    
    print("🔍 Test walidacji komponentu Lynx API")
    print("="*50)
    
    # Sprawdź czy ACCESS_TOKEN jest dostępny
    access_token = os.getenv("ACCESS_TOKEN")
    if not access_token:
        print("❌ BŁĄD: Brak ACCESS_TOKEN w zmiennych środowiskowych")
        print("   Ustaw zmienną: export ACCESS_TOKEN='your_token_here'")
        print("   lub podaj token jako argument")
        
        # Możliwość podania tokenu interaktywnie
        token_input = input("Podaj ACCESS_TOKEN (lub Enter aby pominąć): ").strip()
        if not token_input:
            return False
        access_token = token_input
    
    # Konfiguracja z rzeczywistymi danymi
    config = {
        "SITE_ID": "2",  # Rzeczywisty site_id
        "ACCESS_TOKEN": access_token
    }
    
    component = LynxAPIComponent(
        name="validation_test",
        config=config
    )
    
    try:
        # Test walidacji
        print("📋 Test walidacji konfiguracji...")
        is_valid = component.validate_config()
        print(f"   ✅ Walidacja: {'OK' if is_valid else 'BŁĄD'}")
        
        # Test inicjalizacji
        print("⚙️ Test inicjalizacji...")
        is_initialized = await component.initialize()
        print(f"   ✅ Inicjalizacja: {'OK' if is_initialized else 'BŁĄD'}")
        
        # Sprawdź status
        status = component.get_status()
        print(f"📊 Status komponentu:")
        for key, value in status.items():
            print(f"   {key}: {value}")
            
        return is_valid and is_initialized
        
    except Exception as e:
        print(f"❌ Błąd: {e}")
        return False


def main():
    """Główna funkcja testowa."""
    
    print("Lynx API Component - Test dla realnej transakcji")
    print("=" * 60)
    print("Transaction ID: 2356298954")
    print("Site ID: 2")
    print("=" * 60)
    
    print("\nWybierz typ testu:")
    print("1. Test pełny z wysyłaniem żądania refund")
    print("2. Test walidacji i konfiguracji tylko")
    print("3. Wyjście")
    
    choice = input("\nTwój wybór (1/2/3): ").strip()
    
    if choice == "1":
        result = asyncio.run(test_real_lynx_transaction())
    elif choice == "2":
        result = asyncio.run(test_lynx_component_validation_only())
    elif choice == "3":
        print("👋 Do widzenia!")
        return
    else:
        print("❌ Nieprawidłowy wybór")
        return
    
    print(f"\n{'✅ SUKCES' if result else '❌ PORAŻKA'}")


if __name__ == "__main__":
    main()
