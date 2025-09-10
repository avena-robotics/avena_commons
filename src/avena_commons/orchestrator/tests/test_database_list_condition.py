"""
Test dla nowego database_list_condition.

Testuje funkcjonalność pobierania listy rekordów z bazy danych
i udostępniania ich w kontekście scenariusza.
"""

import asyncio
from unittest.mock import AsyncMock

from ..conditions.database_list_condition import DatabaseListCondition


async def test_database_list_condition_basic():
    """
    Test podstawowej funkcjonalności DatabaseListCondition.
    """
    print("🧪 Test: DatabaseListCondition - podstawowa funkcjonalność")

    # Konfiguracja warunku
    config = {
        "component": "test_db",
        "table": "zamowienia",
        "columns": ["id", "numer_zamowienia", "stan_zamowienia"],
        "where": {
            "stan_zamowienia": "refund"
        },
        "result_key": "test_orders",
        "limit": 10
    }

    # Mock database component
    mock_db = AsyncMock()
    mock_db.is_connected = True
    mock_db.fetch_records = AsyncMock(return_value=[
        {"id": 1, "numer_zamowienia": "ORDER-001", "stan_zamowienia": "refund"},
        {"id": 2, "numer_zamowienia": "ORDER-002", "stan_zamowienia": "refund"},
    ])

    # Mock context
    context = {
        "components": {
            "test_db": mock_db
        },
        "trigger_data": {}
    }

    # Utwórz warunek
    condition = DatabaseListCondition(config)

    # Wykonaj test
    result = await condition.evaluate(context)

    # Sprawdź wyniki
    assert result is True, "Warunek powinien zwrócić True gdy znaleziono rekordy"
    
    # Sprawdź czy dane zostały zapisane w kontekście
    assert "test_orders" in context["trigger_data"], "Dane powinny być zapisane w trigger_data"
    assert len(context["trigger_data"]["test_orders"]) == 2, "Powinno być 2 rekordy"
    
    # Sprawdź wywołanie metody fetch_records
    mock_db.fetch_records.assert_called_once_with(
        table="zamowienia",
        columns=["id", "numer_zamowienia", "stan_zamowienia"],
        where_conditions={"stan_zamowienia": "refund"},
        limit=10,
        order_by=None
    )

    print("✅ Test podstawowej funkcjonalności zakończony pomyślnie")


async def test_database_list_condition_empty_result():
    """
    Test gdy brak wyników z bazy danych.
    """
    print("🧪 Test: DatabaseListCondition - brak wyników")

    config = {
        "component": "test_db",
        "table": "zamowienia",
        "columns": ["id"],
        "where": {
            "stan_zamowienia": "non_existent"
        },
        "result_key": "empty_orders"
    }

    # Mock database component zwracający pustą listę
    mock_db = AsyncMock()
    mock_db.is_connected = True
    mock_db.fetch_records = AsyncMock(return_value=[])

    context = {
        "components": {
            "test_db": mock_db
        },
        "trigger_data": {}
    }

    condition = DatabaseListCondition(config)
    result = await condition.evaluate(context)

    # Warunek powinien zwrócić False gdy brak rekordów
    assert result is False, "Warunek powinien zwrócić False gdy brak rekordów"
    
    # Dane powinny być zapisane jako pusta lista
    assert context["trigger_data"]["empty_orders"] == [], "Powinna być pusta lista"

    print("✅ Test braku wyników zakończony pomyślnie")


async def test_database_list_condition_validation():
    """
    Test walidacji konfiguracji.
    """
    print("🧪 Test: DatabaseListCondition - walidacja konfiguracji")

    # Test brakującego pola 'columns'
    try:
        config = {
            "component": "test_db",
            "table": "test_table",
            "where": {"id": 1}
            # Brakuje 'columns'
        }
        DatabaseListCondition(config)
        assert False, "Powinien rzucić wyjątek dla brakującego pola 'columns'"
    except ValueError as e:
        assert "columns" in str(e), "Błąd powinien dotyczyć pola 'columns'"

    # Test pustej listy columns
    try:
        config = {
            "component": "test_db", 
            "table": "test_table",
            "columns": [],  # Pusta lista
            "where": {"id": 1}
        }
        DatabaseListCondition(config)
        assert False, "Powinien rzucić wyjątek dla pustej listy columns"
    except ValueError as e:
        assert "niepust" in str(e).lower(), "Błąd powinien dotyczyć pustej listy"

    print("✅ Test walidacji konfiguracji zakończony pomyślnie")


async def run_all_tests():
    """Uruchom wszystkie testy."""
    print("🚀 Rozpoczynam testy DatabaseListCondition")
    
    await test_database_list_condition_basic()
    await test_database_list_condition_empty_result() 
    await test_database_list_condition_validation()
    
    print("🎉 Wszystkie testy zakończone pomyślnie!")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
