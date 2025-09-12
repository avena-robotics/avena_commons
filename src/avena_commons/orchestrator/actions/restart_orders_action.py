"""
Akcja restartu zamówień APS z weryfikacją dostępności produktów.

Funkcjonalność:
- Sprawdza dostępność produktów w storage_item_slot (current_quantity >= liczba pozycji)
- Klonuje zamówienia z konfigurowalnymi polami (bez pickup_number)
- Aktualizuje statusy: canceled/paid/reserved/refund_pending
- Wykonuje wszystkie operacje w transakcjach atomowych

Wykorzystanie: restart zamówień z niesprawnych wydawek do działających.
"""

from collections import defaultdict
from typing import Any, Dict, List

from avena_commons.orchestrator.actions.base_action import (
    ActionExecutionError,
    BaseAction,
    ScenarioContext,
)
from avena_commons.util.logger import debug, error, info, warning


class RestartOrdersAction(BaseAction):
    """
    Akcja restartu zamówień APS z weryfikacją dostępności produktów.

    Dla każdego zamówienia z triggera:
    1. Sprawdza dostępność wszystkich pozycji w storage_item_slot
    2. SUCCESS: klonuje aps_order + aps_order_item + aktualizuje statusy
    3. FAILURE: ustawia status zamówienia na 'refund_pending'

    Każda pozycja aps_order_item reprezentuje 1 sztukę produktu.
    Wszystkie operacje wykonywane w transakcjach atomowych.
    """

    action_type = "restart_orders"

    async def execute(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> Dict[str, Any]:
        """
        Wykonuje restart zamówień z pełną weryfikacją dostępności.

        Args:
            action_config (Dict[str, Any]): Konfiguracja z polami:
                - component (str): nazwa komponentu DB (wymagane)
                - orders_source (str): klucz z listą zamówień z triggera
                - clone_config (Dict): konfiguracja klonowania pól
            context (ScenarioContext): Kontekst wykonania

        Returns:
            Dict[str, Any]: Podsumowanie: success_count, refund_count, total_count, details

        Raises:
            ActionExecutionError: W przypadku błędów konfiguracji lub wykonania
        """
        try:
            # 1. Walidacja i pobranie danych
            orders = self._get_orders_from_context(action_config, context)
            db_component = self._get_database_component(action_config, context)
            clone_config = self._get_clone_configuration(action_config)

            info(
                f"🔄 Rozpoczynam restart {len(orders)} zamówień APS",
                message_logger=context.message_logger,
            )

            results = {
                "success_count": 0,
                "refund_count": 0,
                "error_count": 0,
                "total_count": len(orders),
                "details": [],
            }

            # 2. Przetwarzanie każdego zamówienia
            for order in orders:
                try:
                    order_id = order.get("id")
                    aps_id = order.get("aps_id")

                    if not order_id or not aps_id:
                        warning(
                            f"Pomijam zamówienie z brakującymi danymi: {order}",
                            message_logger=context.message_logger,
                        )
                        continue

                    # Sprawdź dostępność wszystkich pozycji
                    availability_check = await self._check_order_items_availability(
                        db_component, order_id, aps_id
                    )

                    if availability_check["all_available"]:
                        # SUCCESS: klonuj zamówienie
                        new_order_id = await self._process_successful_restart(
                            db_component,
                            order,
                            availability_check,
                            clone_config,
                            context,
                        )
                        results["success_count"] += 1
                        results["details"].append({
                            "original_id": order_id,
                            "new_id": new_order_id,
                            "status": "success",
                            "action": "cloned",
                            "products_count": availability_check["total_positions"],
                        })

                        info(
                            f"✅ Zamówienie {order_id} sklonowane → nowe ID: {new_order_id}",
                            message_logger=context.message_logger,
                        )
                    else:
                        # FAILURE: refund_pending
                        await self._process_failed_restart(
                            db_component, order_id, context
                        )
                        results["refund_count"] += 1
                        results["details"].append({
                            "original_id": order_id,
                            "status": "refund_pending",
                            "reason": "products_unavailable",
                            "unavailable_items": availability_check[
                                "unavailable_items"
                            ],
                        })

                        warning(
                            f"❌ Zamówienie {order_id} → refund_pending (brak produktów: {availability_check['unavailable_items']})",
                            message_logger=context.message_logger,
                        )

                except Exception as e:
                    results["error_count"] += 1
                    results["details"].append({
                        "original_id": order.get("id"),
                        "status": "error",
                        "error": str(e),
                    })
                    error(
                        f"Błąd przetwarzania zamówienia {order}: {e}",
                        message_logger=context.message_logger,
                    )

            info(
                f"🏁 Restart zakończony. Sukces: {results['success_count']}, "
                f"Refund: {results['refund_count']}, Błędy: {results['error_count']}",
                message_logger=context.message_logger,
            )

            return results

        except ActionExecutionError:
            raise
        except Exception as e:
            error(
                f"restart_orders: Błąd wykonania akcji: {e}",
                message_logger=context.message_logger,
            )
            raise ActionExecutionError(
                self.action_type, f"Błąd wykonania akcji: {str(e)}", e
            )

    def _get_orders_from_context(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ) -> List[Dict[str, Any]]:
        """Pobiera listę zamówień z kontekstu triggera."""
        orders_source = action_config.get("orders_source")
        if not orders_source:
            raise ActionExecutionError(
                self.action_type, "Brak 'orders_source' w konfiguracji"
            )

        # Rozwiąż zmienne szablonowe
        orders_key = self._resolve_template_variables(orders_source, context)

        # Pobierz dane z trigger_data

        orders = context.context.get(orders_key)

        if not isinstance(orders, list):
            raise ActionExecutionError(
                self.action_type,
                f"Dane z '{orders_source}' nie są listą: {type(orders)}",
            )

        return orders

    def _get_database_component(
        self, action_config: Dict[str, Any], context: ScenarioContext
    ):
        """Pobiera komponent bazodanowy z orchestratora."""
        component_name = action_config.get("component")

        if not component_name:
            raise ActionExecutionError(
                self.action_type, "Brak 'component' w konfiguracji"
            )

        components = context.get("components", {})
        if component_name not in components:
            raise ActionExecutionError(
                self.action_type,
                f"Komponent bazodanowy '{component_name}' nie jest dostępny",
            )

        db_component = components[component_name]
        if not db_component.is_connected:
            raise ActionExecutionError(
                self.action_type,
                f"Komponent bazodanowy '{component_name}' nie jest połączony",
            )

        return db_component

    def _get_clone_configuration(self, action_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parsuje konfigurację klonowania z możliwością dostosowania pól.

        Returns:
            Dict z finalnymi polami do kopiowania i ustawieniami
        """
        clone_config = action_config.get("clone_config", {})

        # Domyślne pola do kopiowania (wszystkie oprócz technicznych)
        default_copy_fields = [
            "aps_id",
            "origin",
            "status",
            "kds_order_number",
            "client_phone_number",
            "estimated_time",
            "transaction_id",
            "marketing_consent",
            "terms_accepted",
            "privacy_accepted",
            "promo_consent",
        ]

        # Zawsze pomijane pola (techniczne)
        always_skip = ["id", "created_at", "updated_at"]

        # Pola do kopiowania (użytkownik może nadpisać)
        copy_fields = clone_config.get("copy_fields", default_copy_fields)

        # Dodatkowe pola do pominięcia (np. pickup_number)
        user_skip_fields = clone_config.get("skip_fields", [])

        # Finalna lista pól do kopiowania
        final_fields = [
            field
            for field in copy_fields
            if field not in always_skip and field not in user_skip_fields
        ]

        return {
            "copy_fields": final_fields,
            "default_values": clone_config.get("default_values", {}),
        }

    async def _check_order_items_availability(
        self, db_component, order_id: int, aps_id: int
    ) -> Dict[str, Any]:
        """
        Sprawdza dostępność produktów - każda pozycja aps_order_item = 1 sztuka.
        Grupuje pozycje po item_id i sprawdza czy current_quantity >= liczba pozycji.

        Args:
            db_component: komponent bazodanowy
            order_id: ID zamówienia
            aps_id: ID systemu APS

        Returns:
            Dict z informacjami o dostępności produktów
        """
        # Pobierz wszystkie pozycje zamówienia
        order_items = await db_component.fetch_records(
            table="aps_order_item",
            columns=["id", "aps_id", "item_id", "status"],
            where_conditions={"aps_order_id": order_id},
        )

        if not order_items:
            return {
                "all_available": False,
                "items": [],
                "unavailable_items": [],
                "total_positions": 0,
            }

        # Grupuj pozycje po item_id (zlicz ile razy występuje każdy produkt)
        item_counts = defaultdict(int)
        items_by_id = defaultdict(list)

        for item in order_items:
            item_id = item["item_id"]
            item_counts[item_id] += 1
            items_by_id[item_id].append(item)

        all_available = True
        unavailable_items = []
        items_details = []

        # Sprawdź dostępność każdego unikalnego produktu
        for item_id, required_count in item_counts.items():
            # Sprawdź dostępność w magazynie
            storage_check = await db_component.fetch_records(
                table="storage_item_slot",
                columns=["current_quantity", "max_quantity", "slot_name"],
                where_conditions={"aps_id": aps_id, "item_description_id": item_id},
            )

            available_quantity = 0
            slot_info = "brak slotu"
            if storage_check:
                available_quantity = storage_check[0]["current_quantity"]
                slot_info = storage_check[0].get("slot_name", "unknown")

            # Sprawdź czy dostępna ilość >= wymagana liczba pozycji
            item_available = available_quantity >= required_count

            if not item_available:
                all_available = False
                unavailable_items.append({
                    "item_id": item_id,
                    "required": required_count,
                    "available": available_quantity,
                    "slot": slot_info,
                })

            items_details.append({
                "item_id": item_id,
                "required_count": required_count,
                "available_quantity": available_quantity,
                "is_available": item_available,
                "slot_name": slot_info,
                "positions": items_by_id[item_id],  # wszystkie pozycje tego produktu
            })

        return {
            "all_available": all_available,
            "items": items_details,
            "unavailable_items": unavailable_items,
            "total_positions": len(order_items),
        }

    async def _process_successful_restart(
        self,
        db_component,
        order: Dict,
        availability_check: Dict,
        clone_config: Dict,
        context: ScenarioContext,
    ) -> int:
        """
        Przetwarza pomyślny restart: klonowanie zamówienia i pozycji.

        Args:
            db_component: komponent bazodanowy
            order: dane oryginalnego zamówienia
            availability_check: wyniki sprawdzania dostępności
            clone_config: konfiguracja klonowania
            context: kontekst wykonania

        Returns:
            int: ID nowo utworzonego zamówienia
        """
        debug(
            f"🔄 Klonowanie zamówienia {order['id']} z {availability_check['total_positions']} pozycjami",
            message_logger=context.message_logger,
        )

        async with db_component._connection.transaction():
            # 1. Sklonuj zamówienie aps_order
            new_order_id = await self._clone_aps_order(
                db_component, order, clone_config
            )

            # 2. Sklonuj wszystkie pozycje aps_order_item
            cloned_positions = 0
            for item_detail in availability_check["items"]:
                for position in item_detail["positions"]:
                    await self._clone_aps_order_item(
                        db_component, position["id"], new_order_id, order["aps_id"]
                    )
                    cloned_positions += 1

            # 3. Aktualizuj statusy (stałe, niekonfigurowalne)
            # STARE zamówienie: 'canceled' (pozycje pozostają niezmienione)
            await db_component.update_table_value(
                table="aps_order",
                column="status",
                value="canceled",
                where_conditions={"id": order["id"]},
            )

            # NOWE zamówienie: 'paid' (gotowe do realizacji)
            await db_component.update_table_value(
                table="aps_order",
                column="status",
                value="paid",
                where_conditions={"id": new_order_id},
            )

            # WSZYSTKIE pozycje NOWEGO zamówienia: 'reserved' (zarezerwowane produkty)
            await db_component.update_table_value(
                table="aps_order_item",
                column="status",
                value="reserved",
                where_conditions={"aps_order_id": new_order_id},
            )

            debug(
                f"✅ Sklonowano zamówienie {order['id']} → {new_order_id} z {cloned_positions} pozycjami",
                message_logger=context.message_logger,
            )

            return new_order_id

    async def _process_failed_restart(
        self, db_component, order_id: int, context: ScenarioContext
    ):
        """
        Przetwarza nieudany restart: tylko status zamówienia na 'refund_pending'.
        Pozycje zamówienia pozostają niezmienione.
        """
        await db_component.update_table_value(
            table="aps_order",
            column="status",
            value="refund_pending",
            where_conditions={"id": order_id},
        )
        # Pozycje zamówienia: NIE RUSZAMY

        debug(
            f"❌ Zamówienie {order_id} → status 'refund_pending'",
            message_logger=context.message_logger,
        )

    async def _clone_aps_order(
        self, db_component, order: Dict, clone_config: Dict
    ) -> int:
        """
        Klonuje rekord aps_order z konfigurowalnymi polami.

        Args:
            db_component: komponent bazodanowy
            order: dane oryginalnego zamówienia
            clone_config: konfiguracja klonowania

        Returns:
            int: ID nowo utworzonego zamówienia
        """
        # Pobierz tylko skonfigurowane pola z oryginalnego zamówienia
        fields_to_copy = clone_config["copy_fields"]

        original = await db_component.fetch_records(
            table="aps_order",
            columns=fields_to_copy,
            where_conditions={"id": order["id"]},
        )

        if not original:
            raise ValueError(f"Nie znaleziono zamówienia o ID {order['id']}")

        original_data = original[0]

        # Przygotuj wartości do INSERT
        insert_fields = list(fields_to_copy)
        insert_values = [original_data[field] for field in fields_to_copy]

        # Dodaj domyślne wartości z konfiguracji
        for field, value in clone_config.get("default_values", {}).items():
            if field not in insert_fields:
                insert_fields.append(field)
                insert_values.append(value)

        # Nadpisz status jeśli określono w konfiguracji
        if "status" in insert_fields:
            status_idx = insert_fields.index("status")
            insert_values[status_idx] = clone_config["new_status"]

        # Zbuduj zapytanie INSERT
        fields_str = ", ".join(insert_fields)
        placeholders = ", ".join([f"${i + 1}" for i in range(len(insert_values))])

        query = f"""
            INSERT INTO aps_order ({fields_str})
            VALUES ({placeholders})
            RETURNING id
        """

        async with db_component._conn_lock:
            new_id = await db_component._connection.fetchval(query, *insert_values)

        return new_id

    async def _clone_aps_order_item(
        self, db_component, original_item_id: int, new_order_id: int, aps_id: int
    ):
        """
        Klonuje pozycję zamówienia dla nowego zamówienia.

        Args:
            db_component: komponent bazodanowy
            original_item_id: ID oryginalnej pozycji
            new_order_id: ID nowego zamówienia
            aps_id: ID systemu APS
        """
        # Pobierz dane oryginalnej pozycji
        original_item = await db_component.fetch_records(
            table="aps_order_item",
            columns=["aps_id", "item_id", "status"],
            where_conditions={"id": original_item_id},
        )

        if not original_item:
            raise ValueError(f"Nie znaleziono pozycji o ID {original_item_id}")

        item_data = original_item[0]

        # INSERT nowej pozycji (bez created_at, updated_at - będą automatyczne)
        query = """
            INSERT INTO aps_order_item (aps_order_id, aps_id, item_id, status)
            VALUES ($1, $2, $3, $4)
        """

        async with db_component._conn_lock:
            await db_component._connection.execute(
                query, new_order_id, aps_id, item_data["item_id"], item_data["status"]
            )
