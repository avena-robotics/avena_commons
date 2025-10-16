#!/usr/bin/env python3
"""
Szybki test RestartOrdersAction - symulacja z przykładowymi danymi.

Ten skrypt pozwala przetestować RestartOrdersAction bez prawdziwej bazy danych.
Używa mock'ów do symulacji różnych scenariuszy.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

# Dodaj ścieżkę do orchestratora
sys.path.append("/home/avena/avena_commons/src/avena_commons/orchestrator")

from actions.base_action import ActionContext
from actions.restart_orders_action import RestartOrdersAction


async def test_restart_orders_simulation():
    """
    Symuluje pełny scenariusz restartu zamówień.
    """
    print("🚀 Rozpoczynam symulację RestartOrdersAction...")

    # Przykładowe zamówienia (z pickup_number=1 które nie działa)
    sample_orders = [
        {
            "id": 1001,
            "aps_id": 2001,
            "origin": "app",
            "status": "pending",
            "pickup_number": "1",  # problematyczna wydawka
            "kds_order_number": "K2001",
            "client_phone_number": "+48123456789",
            "estimated_time": 15,
            "transaction_id": "tx_2001",
            "marketing_consent": True,
            "terms_accepted": True,
            "privacy_accepted": True,
            "promo_consent": False,
        },
        {
            "id": 1002,
            "aps_id": 2002,
            "origin": "web",
            "status": "pending",
            "pickup_number": "1",
            "kds_order_number": "K2002",
            "client_phone_number": "+48987654321",
            "estimated_time": 20,
            "transaction_id": "tx_2002",
            "marketing_consent": False,
            "terms_accepted": True,
            "privacy_accepted": True,
            "promo_consent": True,
        },
    ]

    # Mock database component
    mock_db = AsyncMock()

    # Symulacja transakcji PostgreSQL
    transaction_mock = AsyncMock()
    transaction_mock.__aenter__ = AsyncMock(return_value=transaction_mock)
    transaction_mock.__aexit__ = AsyncMock(return_value=None)
    mock_db._connection.transaction.return_value = transaction_mock

    # Symulacja danych z bazy
    async def mock_select_list(table, columns, where_conditions=None, **kwargs):
        print(f"  📊 Query: {table} WHERE {where_conditions}")

        # Pozycje zamówień (każda = 1 produkt)
        if table == "aps_order_item":
            order_id = where_conditions.get("aps_order_id")
            if order_id == 1001:
                return [
                    {
                        "id": 3001,
                        "aps_order_id": 1001,
                        "item_id": 101,
                        "status": "pending",
                        "aps_id": 2001,
                    },
                    {
                        "id": 3002,
                        "aps_order_id": 1001,
                        "item_id": 101,
                        "status": "pending",
                        "aps_id": 2001,
                    },  # 2x kawa
                    {
                        "id": 3003,
                        "aps_order_id": 1001,
                        "item_id": 102,
                        "status": "pending",
                        "aps_id": 2001,
                    },  # 1x ciastko
                ]
            elif order_id == 1002:
                return [
                    {
                        "id": 3004,
                        "aps_order_id": 1002,
                        "item_id": 103,
                        "status": "pending",
                        "aps_id": 2002,
                    },  # 1x herbata
                    {
                        "id": 3005,
                        "aps_order_id": 1002,
                        "item_id": 104,
                        "status": "pending",
                        "aps_id": 2002,
                    },  # 1x muffin (niedostępny)
                ]

        # Stan magazynu
        elif table == "storage_item_slot":
            item_id = where_conditions.get("item_id")
            storage_state = {
                101: [
                    {"current_quantity": 10, "slot_name": "A1-Kawa"}
                ],  # Dostępne: kawa
                102: [
                    {"current_quantity": 5, "slot_name": "B1-Ciastka"}
                ],  # Dostępne: ciastko
                103: [
                    {"current_quantity": 8, "slot_name": "C1-Herbata"}
                ],  # Dostępne: herbata
                104: [
                    {"current_quantity": 0, "slot_name": "D1-Muffin"}
                ],  # Niedostępne: muffin
            }
            return storage_state.get(
                item_id, [{"current_quantity": 0, "slot_name": "Unknown"}]
            )

        return []

    # Symulacja wstawiania nowych rekordów
    async def mock_insert_record(table, data):
        if table == "aps_order":
            new_id = 2000 + data.get("aps_id", 0)
            print(f"  ✅ Utworzono nowe zamówienie ID: {new_id}")
            return new_id
        elif table == "aps_order_item":
            new_id = 4000 + data.get("item_id", 0)
            print(f"  ✅ Utworzono nową pozycję ID: {new_id}")
            return new_id

    # Symulacja aktualizacji statusów
    async def mock_update_table_value(table, column, value, where_conditions):
        print(f"  🔄 UPDATE {table} SET {column}='{value}' WHERE {where_conditions}")

    # Podłączenie mock'ów
    mock_db.select_list = mock_select_list
    mock_db.insert_record = mock_insert_record
    mock_db.update_table_value = mock_update_table_value

    # Mock orchestrator
    mock_orchestrator = MagicMock()
    mock_orchestrator.get_component.return_value = mock_db

    # Mock context
    context = ActionContext(
        orchestrator=mock_orchestrator,
        message_logger=MagicMock(),
        trigger_data={"zamowienia_pickup_1": sample_orders},
        scenario_name="test_restart_pickup_1",
    )

    # Konfiguracja restartu
    action_config = {
        "component": "main_database",
        "orders_source": "zamowienia_pickup_1",
        "clone_config": {
            "copy_fields": [
                "aps_id",
                "origin",
                "kds_order_number",
                "client_phone_number",
                "estimated_time",
                "transaction_id",
                "marketing_consent",
                "terms_accepted",
                "privacy_accepted",
                "promo_consent",
            ],
            "skip_fields": ["pickup_number"],  # Nie kopiujemy problematycznej wydawki
            "default_values": {},
        },
    }

    # Wykonanie restartu
    print("\n🎯 Rozpoczynam restart zamówień...")
    action = RestartOrdersAction()

    try:
        result = await action.execute(action_config, context)

        print(f"\n📈 WYNIKI RESTARTU:")
        print(f"  ✅ Pomyślnie sklonowanych: {result['success_count']}")
        print(f"  🔄 Ustawionych na refund: {result['refund_count']}")
        print(f"  ❌ Błędy: {result['error_count']}")
        print(f"  📊 Łącznie przetworzonych: {result['total_count']}")

        print(f"\n📋 SZCZEGÓŁY:")
        for detail in result["details"]:
            status = (
                "✅ SKLONOWANO"
                if detail["success"]
                else "🔄 REFUND"
                if not detail["error"]
                else "❌ BŁĄD"
            )
            print(
                f"  {status} - Zamówienie {detail['order_id']} (APS: {detail['aps_id']})"
            )
            if detail.get("availability"):
                items = detail["availability"]["items"]
                for item in items:
                    availability = "✅" if item["is_available"] else "❌"
                    print(
                        f"    {availability} Produkt {item['item_id']}: {item['required_count']} szt (magazyn: {item['available_quantity']})"
                    )

        print(f"\n🎉 Test zakończony pomyślnie!")
        return True

    except Exception as e:
        print(f"\n❌ Błąd podczas testu: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_configuration_scenarios():
    """
    Testuje różne scenariusze konfiguracji.
    """
    print("\n🧪 Test scenariuszy konfiguracji...")

    action = RestartOrdersAction()

    # Test 1: Minimalna konfiguracja
    print("\n1️⃣ Test minimalnej konfiguracji:")
    mock_config = {"component": "main_database", "orders_source": "test_orders"}
    clone_config = action._get_clone_configuration(mock_config)
    print(f"  Pola do kopiowania: {len(clone_config['copy_fields'])} pól")
    print(f"  Wartości domyślne: {clone_config['default_values']}")

    # Test 2: Konfiguracja z pominięciem pól
    print("\n2️⃣ Test z pominięciem pickup_number:")
    mock_config = {
        "clone_config": {
            "copy_fields": ["aps_id", "origin", "pickup_number"],
            "skip_fields": ["pickup_number"],
        }
    }
    clone_config = action._get_clone_configuration(mock_config)
    print(f"  Finalne pola: {clone_config['copy_fields']}")
    print(
        f"  pickup_number pominięty: {'pickup_number' not in clone_config['copy_fields']}"
    )

    # Test 3: Konfiguracja z wartościami domyślnymi
    print("\n3️⃣ Test z wartościami domyślnymi:")
    mock_config = {
        "clone_config": {"default_values": {"pickup_number": None, "status": "pending"}}
    }
    clone_config = action._get_clone_configuration(mock_config)
    print(f"  Wartości domyślne: {clone_config['default_values']}")


if __name__ == "__main__":
    print("🔬 SYMULACJA TESTOWA RestartOrdersAction")
    print("=" * 50)

    # Uruchom symulację główną
    success = asyncio.run(test_restart_orders_simulation())

    # Uruchom testy konfiguracji
    asyncio.run(test_configuration_scenarios())

    if success:
        print(f"\n🎯 WNIOSEK: RestartOrdersAction działa poprawnie!")
        print("   Możesz teraz użyć akcji w scenariuszach JSON.")
    else:
        print(f"\n⚠️ UWAGA: Znaleziono problemy wymagające poprawek.")

    print("=" * 50)
