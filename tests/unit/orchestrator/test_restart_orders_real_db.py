#!/usr/bin/env python3
"""
Test RestartOrdersAction z prawdziwą bazą danych (ostrożnie!).

UWAGA: Ten skrypt łączy się z prawdziwą bazą danych.
Używaj tylko w środowisku testowym!
"""

import asyncio
import json
import sys

# Dodaj ścieżkę do orchestratora
sys.path.append("/home/avena/avena_commons/src/avena_commons/orchestrator")

from orchestrator import EventListener


async def test_restart_orders_real_db():
    """
    Test z prawdziwą bazą danych - TYLKO dla środowiska testowego!
    """
    print("⚠️  UWAGA: Test z prawdziwą bazą danych!")
    print("🔍 Sprawdzam konfigurację orchestratora...")

    try:
        # Inicjalizuj orchestrator (będzie potrzebował pliku konfiguracyjnego)
        orchestrator = EventListener()

        # Sprawdź czy mamy komponent bazy danych
        db_component = orchestrator.get_component("main_database")
        if not db_component:
            print("❌ Brak komponentu main_database w konfiguracji")
            return False

        print("✅ Połączenie z bazą danych OK")

        # BEZPIECZNY TEST: tylko SELECT, żadnych zmian!
        print("\n🔍 Sprawdzam strukturę tabel...")

        # Test 1: Sprawdź tabelę aps_order
        sample_orders = await db_component.select_list(
            table="aps_order",
            columns=["id", "aps_id", "status", "pickup_number"],
            where_conditions={"status": "pending"},
            limit=3,
        )

        if sample_orders:
            print(f"✅ Znaleziono {len(sample_orders)} zamówień pending:")
            for order in sample_orders:
                print(
                    f"  - Zamówienie {order['id']}: APS={order['aps_id']}, wydawka={order['pickup_number']}"
                )
        else:
            print("ℹ️  Brak zamówień ze statusem 'pending'")

        # Test 2: Sprawdź tabelę aps_order_item
        if sample_orders:
            first_order_id = sample_orders[0]["id"]
            order_items = await db_component.select_list(
                table="aps_order_item",
                columns=["id", "item_id", "status"],
                where_conditions={"aps_order_id": first_order_id},
            )
            print(f"✅ Zamówienie {first_order_id} ma {len(order_items)} pozycji")

        # Test 3: Sprawdź tabelę storage_item_slot
        storage_items = await db_component.select_list(
            table="storage_item_slot",
            columns=["item_id", "current_quantity", "slot_name"],
            limit=5,
        )

        if storage_items:
            print(f"✅ Stan magazynu (przykładowe 5 pozycji):")
            for item in storage_items:
                print(
                    f"  - Produkt {item['item_id']}: {item['current_quantity']} szt w {item['slot_name']}"
                )

        print("\n🎯 ZALECENIE:")
        print("  1. Struktury tabel są OK - RestartOrdersAction powinno działać")
        print("  2. Przetestuj na pojedynczym zamówieniu najpierw")
        print("  3. Użyj scenariusza JSON z małą liczbą zamówień")

        return True

    except Exception as e:
        print(f"❌ Błąd podczas testu: {e}")
        print("💡 Możliwe przyczyny:")
        print("  - Brak pliku konfiguracyjnego orchestratora")
        print("  - Problemy z połączeniem do bazy")
        print("  - Nieprawidłowe uprawnienia")
        return False


async def create_test_scenario():
    """
    Tworzy bezpieczny scenariusz testowy z pojedynczym zamówieniem.
    """
    print("\n📝 Tworzę bezpieczny scenariusz testowy...")

    test_scenario = {
        "name": "Test restart pojedynczego zamówienia",
        "description": "Bezpieczny test RestartOrdersAction na jednym zamówieniu",
        "version": "1.0",
        "author": "Test",
        "priority": 50,
        "cooldown": 0,
        "trigger": {
            "type": "manual",
            "description": "Ręczny test restartu zamówienia",
            "conditions": {
                "database_list": {
                    "component": "main_database",
                    "table": "aps_order",
                    "columns": [
                        "id",
                        "aps_id",
                        "origin",
                        "status",
                        "pickup_number",
                        "kds_order_number",
                        "client_phone_number",
                        "estimated_time",
                    ],
                    "where": {"status": "pending", "pickup_number": "1"},
                    "result_key": "test_order",
                    "limit": 1,
                    "order_by": "id ASC",
                }
            },
        },
        "actions": [
            {
                "type": "log_event",
                "level": "info",
                "message": "🧪 Rozpoczynam TEST restartu 1 zamówienia",
                "description": "Log początkowy",
            },
            {
                "type": "logic_and",
                "conditions": [
                    {
                        "type": "database_list",
                        "component": "main_database",
                        "table": "aps_order",
                        "where": "LENGTH({{ trigger.test_order }}) > 0",
                        "result_key": "has_test_order",
                    }
                ],
                "true_actions": [
                    {
                        "type": "restart_orders",
                        "component": "main_database",
                        "orders_source": "{{ trigger.test_order }}",
                        "clone_config": {
                            "copy_fields": [
                                "aps_id",
                                "origin",
                                "kds_order_number",
                                "client_phone_number",
                                "estimated_time",
                            ],
                            "skip_fields": ["pickup_number"],
                            "default_values": {},
                        },
                        "description": "TEST restart pojedynczego zamówienia",
                    },
                    {
                        "type": "log_event",
                        "level": "success",
                        "message": "✅ TEST zakończony. Sklonowanych: {{ action_result.success_count }}, Refund: {{ action_result.refund_count }}",
                        "description": "Log końcowy",
                    },
                ],
                "false_actions": [
                    {
                        "type": "log_event",
                        "level": "warning",
                        "message": "⚠️ Brak zamówień do testowania",
                        "description": "Brak danych testowych",
                    }
                ],
            },
        ],
    }

    # Zapisz scenariusz testowy
    test_file = "/home/avena/avena_commons/src/avena_commons/orchestrator/scenarios/TEST_restart_single_order.json"

    with open(test_file, "w", encoding="utf-8") as f:
        json.dump(test_scenario, f, indent=2, ensure_ascii=False)

    print(f"✅ Utworzono scenariusz testowy: {test_file}")
    print("💡 Jak używać:")
    print("  1. Uruchom orchestrator")
    print("  2. Załaduj scenariusz TEST_restart_single_order.json")
    print("  3. Uruchom ręcznie trigger")
    print("  4. Sprawdź logi i wyniki w bazie")


if __name__ == "__main__":
    print("🔬 TEST RestartOrdersAction z prawdziwą bazą danych")
    print("=" * 60)
    print("⚠️  UŻYWAJ TYLKO W ŚRODOWISKU TESTOWYM!")

    response = input("\n❓ Czy chcesz kontynuować? (tak/nie): ").lower()

    if response in ["tak", "t", "yes", "y"]:
        print("\n🚀 Rozpoczynam test...")

        # Test połączenia z bazą
        success = asyncio.run(test_restart_orders_real_db())

        # Utwórz scenariusz testowy
        asyncio.run(create_test_scenario())

        if success:
            print(f"\n🎯 KOLEJNE KROKI:")
            print("  1. Użyj scenariusza TEST_restart_single_order.json")
            print("  2. Sprawdź logi orchestratora")
            print("  3. Zweryfikuj zmiany w bazie danych")
            print("  4. Po testach usuń scenariusz testowy")

    else:
        print("✋ Test anulowany. To dobra decyzja dla środowiska produkcyjnego!")

    print("=" * 60)
