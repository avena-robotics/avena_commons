"""
Test dla RestartOrdersAction.

Testuje pełną funkcjonalność restartu zamówień APS z weryfikacją dostępności produktów.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Dodaj ścieżkę do sys.path aby umożliwić import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from actions.base_action import ActionContext, ActionExecutionError
from actions.restart_orders_action import RestartOrdersAction


class TestRestartOrdersAction(unittest.TestCase):
    """Testy dla RestartOrdersAction."""

    def setUp(self):
        """Przygotowanie do testów."""
        self.action = RestartOrdersAction()
        
        # Mock orchestrator
        self.mock_orchestrator = MagicMock()
        self.mock_orchestrator.get_component = MagicMock()
        
        # Mock message logger
        self.mock_logger = MagicMock()
        
        # Mock context
        self.context = ActionContext(
            orchestrator=self.mock_orchestrator,
            message_logger=self.mock_logger,
            trigger_data={"test_orders": self._get_sample_orders()},
            scenario_name="test_restart_orders"
        )

    def _get_sample_orders(self):
        """Zwraca przykładowe zamówienia do testów."""
        return [
            {
                "id": 101,
                "aps_id": 1001,
                "origin": "app",
                "status": "pending",
                "pickup_number": "1",
                "kds_order_number": "K001",
                "client_phone_number": "+48123456789",
                "estimated_time": 15,
                "transaction_id": "tx_001",
                "marketing_consent": True,
                "terms_accepted": True,
                "privacy_accepted": True,
                "promo_consent": False,
                "created_at": "2025-09-10 10:00:00",
                "updated_at": "2025-09-10 10:00:00"
            },
            {
                "id": 102,
                "aps_id": 1002,
                "origin": "web",
                "status": "pending",
                "pickup_number": "1",
                "kds_order_number": "K002",
                "client_phone_number": "+48987654321",
                "estimated_time": 20,
                "transaction_id": "tx_002",
                "marketing_consent": False,
                "terms_accepted": True,
                "privacy_accepted": True,
                "promo_consent": True,
                "created_at": "2025-09-10 10:05:00",
                "updated_at": "2025-09-10 10:05:00"
            }
        ]

    def _get_sample_order_items(self, order_id: int):
        """Zwraca przykładowe pozycje zamówienia."""
        if order_id == 101:
            return [
                {"id": 1001, "aps_order_id": 101, "item_id": 10, "status": "pending", "aps_id": 1001},
                {"id": 1002, "aps_order_id": 101, "item_id": 10, "status": "pending", "aps_id": 1001},
                {"id": 1003, "aps_order_id": 101, "item_id": 20, "status": "pending", "aps_id": 1001}
            ]
        elif order_id == 102:
            return [
                {"id": 1004, "aps_order_id": 102, "item_id": 30, "status": "pending", "aps_id": 1002},
                {"id": 1005, "aps_order_id": 102, "item_id": 30, "status": "pending", "aps_id": 1002}
            ]
        return []

    def _get_sample_storage_slots(self):
        """Zwraca przykładowy stan magazynu."""
        return {
            10: {"current_quantity": 5, "slot_name": "A1"},  # Dostępne (potrzebne: 2)
            20: {"current_quantity": 1, "slot_name": "B1"},  # Dostępne (potrzebne: 1)
            30: {"current_quantity": 1, "slot_name": "C1"},  # Niedostępne (potrzebne: 2)
        }

    async def test_successful_restart_with_available_products(self):
        """Test pomyślnego restartu z dostępnymi produktami."""
        
        # Mock database component
        mock_db = AsyncMock()
        mock_db._connection.transaction = AsyncMock()
        mock_db._connection.transaction.return_value.__aenter__ = AsyncMock()
        mock_db._connection.transaction.return_value.__aexit__ = AsyncMock()
        
        # Mock database queries
        async def mock_select_list(table, columns, where_conditions=None, **kwargs):
            if table == "aps_order_item" and where_conditions.get("aps_order_id") == 101:
                return self._get_sample_order_items(101)
            elif table == "storage_item_slot" and where_conditions.get("item_id") == 10:
                return [{"current_quantity": 5, "slot_name": "A1"}]
            elif table == "storage_item_slot" and where_conditions.get("item_id") == 20:
                return [{"current_quantity": 1, "slot_name": "B1"}]
            return []

        async def mock_insert_record(table, data):
            if table == "aps_order":
                return 201  # ID nowego zamówienia
            elif table == "aps_order_item":
                return 2001  # ID nowej pozycji
            return None

        mock_db.select_list = mock_select_list
        mock_db.insert_record = mock_insert_record
        mock_db.update_table_value = AsyncMock()
        
        self.mock_orchestrator.get_component.return_value = mock_db
        
        # Konfiguracja akcji
        action_config = {
            "component": "main_database",
            "orders_source": "test_orders",
            "clone_config": {
                "copy_fields": ["aps_id", "origin", "kds_order_number"],
                "skip_fields": ["pickup_number"],
                "default_values": {}
            }
        }
        
        # Wykonanie testu
        result = await self.action.execute(action_config, self.context)
        
        # Weryfikacja wyników
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(result["refund_count"], 0)
        self.assertEqual(result["total_count"], 2)
        self.assertGreater(len(result["details"]), 0)

    async def test_restart_with_unavailable_products(self):
        """Test restartu z niedostępnymi produktami (refund)."""
        
        # Mock database component
        mock_db = AsyncMock()
        mock_db._connection.transaction = AsyncMock()
        mock_db._connection.transaction.return_value.__aenter__ = AsyncMock()
        mock_db._connection.transaction.return_value.__aexit__ = AsyncMock()
        
        # Mock database queries - brak produktów w magazynie
        async def mock_select_list(table, columns, where_conditions=None, **kwargs):
            if table == "aps_order_item" and where_conditions.get("aps_order_id") == 102:
                return self._get_sample_order_items(102)
            elif table == "storage_item_slot" and where_conditions.get("item_id") == 30:
                return [{"current_quantity": 1, "slot_name": "C1"}]  # Za mało (potrzebne: 2)
            return []

        mock_db.select_list = mock_select_list
        mock_db.update_table_value = AsyncMock()
        
        self.mock_orchestrator.get_component.return_value = mock_db
        
        # Konfiguracja akcji
        action_config = {
            "component": "main_database",
            "orders_source": "test_orders",
            "clone_config": {
                "copy_fields": ["aps_id", "origin"],
                "skip_fields": [],
                "default_values": {}
            }
        }
        
        # Wykonanie testu
        result = await self.action.execute(action_config, self.context)
        
        # Weryfikacja wyników
        self.assertEqual(result["success_count"], 0)
        self.assertEqual(result["refund_count"], 1)
        self.assertEqual(result["total_count"], 2)

    async def test_configuration_validation(self):
        """Test walidacji konfiguracji akcji."""
        
        # Test brakującego component
        action_config = {
            "orders_source": "test_orders"
        }
        
        with self.assertRaises(ActionExecutionError) as cm:
            await self.action.execute(action_config, self.context)
        
        self.assertIn("component", str(cm.exception))

    async def test_empty_orders_source(self):
        """Test z pustą listą zamówień."""
        
        # Mock database component
        mock_db = AsyncMock()
        self.mock_orchestrator.get_component.return_value = mock_db
        
        # Pusty trigger data
        empty_context = ActionContext(
            orchestrator=self.mock_orchestrator,
            message_logger=self.mock_logger,
            trigger_data={"empty_orders": []},
            scenario_name="test_empty"
        )
        
        action_config = {
            "component": "main_database",
            "orders_source": "empty_orders",
            "clone_config": {}
        }
        
        # Wykonanie testu
        result = await self.action.execute(action_config, empty_context)
        
        # Weryfikacja wyników
        self.assertEqual(result["success_count"], 0)
        self.assertEqual(result["refund_count"], 0)
        self.assertEqual(result["total_count"], 0)

    def test_clone_configuration_parsing(self):
        """Test parsowania konfiguracji klonowania."""
        
        # Test domyślnej konfiguracji
        action_config = {}
        clone_config = self.action._get_clone_configuration(action_config)
        
        self.assertIn("copy_fields", clone_config)
        self.assertIn("default_values", clone_config)
        self.assertIsInstance(clone_config["copy_fields"], list)
        self.assertIsInstance(clone_config["default_values"], dict)

    def test_product_grouping_logic(self):
        """Test logiki grupowania produktów."""
        
        order_items = self._get_sample_order_items(101)
        
        # Grupowanie powinno dać: item_id 10 -> 2 sztuki, item_id 20 -> 1 sztuka
        items_by_id = {}
        for item in order_items:
            item_id = item["item_id"]
            if item_id not in items_by_id:
                items_by_id[item_id] = []
            items_by_id[item_id].append(item)
        
        self.assertEqual(len(items_by_id[10]), 2)  # 2 pozycje produktu 10
        self.assertEqual(len(items_by_id[20]), 1)  # 1 pozycja produktu 20


# Funkcje pomocnicze do uruchamiania testów
async def run_async_test(test_func):
    """Uruchamia asynchroniczny test."""
    test_instance = TestRestartOrdersAction()
    test_instance.setUp()
    await test_func(test_instance)


async def test_integration_basic():
    """Podstawowy test integracyjny."""
    print("🧪 Test podstawowy restart zamówień...")
    
    test_instance = TestRestartOrdersAction()
    test_instance.setUp()
    
    try:
        await test_instance.test_successful_restart_with_available_products()
        print("✅ Test pomyślnego restartu - PASSED")
    except Exception as e:
        print(f"❌ Test pomyślnego restartu - FAILED: {e}")
    
    try:
        await test_instance.test_restart_with_unavailable_products()
        print("✅ Test restartu z refund - PASSED")
    except Exception as e:
        print(f"❌ Test restartu z refund - FAILED: {e}")


async def test_configuration_validation():
    """Test walidacji konfiguracji."""
    print("🧪 Test walidacji konfiguracji...")
    
    test_instance = TestRestartOrdersAction()
    test_instance.setUp()
    
    try:
        await test_instance.test_configuration_validation()
        print("✅ Test walidacji konfiguracji - PASSED")
    except Exception as e:
        print(f"❌ Test walidacji konfiguracji - FAILED: {e}")


if __name__ == "__main__":
    """Uruchomienie testów."""
    print("🚀 Uruchamianie testów RestartOrdersAction...")
    
    # Uruchom testy asynchroniczne
    asyncio.run(test_integration_basic())
    asyncio.run(test_configuration_validation())
    
    print("🎯 Testy zakończone!")
