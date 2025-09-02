# Przegląd modułu Warehouse

## Wprowadzenie

`Warehouse` to warstwa logiki magazynowej wykorzystywana przez MUNCHIES ALGO do obsługi stanów magazynowych i wyznaczania waypointów dla robota. Odpowiada za:

- **wybór i aktualizację** pojemników z pudełkami i tackami pizz,
- **generowanie waypointów** pobrania/odłożenia (w tym nazwy z poziomem i tacką),
- **obliczenia pomocnicze** (np. rotacja pieca i QR dla danej tacki),
- **wspieranie sekwencji** przenoszenia pizzy do pieca oraz wydawania napojów.

Moduł operuje na tabeli `storage_item_slot` w bazie PostgreSQL i bazuje na konwencji nazw slotów:

- `SCFxx` – stosy z pustymi pudełkami (boxy),
- `SCPxx` – stosy z pizzami (tacki w pojemnikach po 4 szt.),
- `SCExx` – stosy na puste pudełka (odkładanie, prawa/lewa strona).

## Klasa Warehouse

```python
class Warehouse:
    """
    Zarządza operacjami magazynowymi systemu (stosy pizz, pudełka, napoje).

    Klasa odpowiada za wyznaczanie waypointów (pobranie/odłożenie),
    aktualizację stanów w tabeli `storage_item_slot` oraz obliczenia
    pomocnicze (np. rotacja pieca i QR) dla procesów wydawczych.
    """

    def __init__(
        self,
        db_connection: psycopg.Connection,
        aps_id: int,
        message_logger: MessageLogger | None = None,
    ):
        self.message_logger = message_logger
        self.db_connection = db_connection
        self.aps_id = aps_id
```

### Generowanie waypointów i nazewnictwo

Do jednolitego tworzenia nazw waypointów wykorzystywana jest metoda pomocnicza:

```python
def _generate_waypoint_name(
    self,
    stack_container_name: str,
    level: int,
    tray: int | None = None,
    over: bool = False,
) -> str:
    if tray is None:
        return f"{stack_container_name}L{str(level).rjust(2, '0')}"
    else:
        return (
            f"{stack_container_name}L{str(level).rjust(2, '0')}T{tray}_over"
            if over
            else f"{stack_container_name}L{str(level).rjust(2, '0')}T{tray}"
        )
```

## Logika wyboru pudełek (boxów)

### Pobranie pustego pudełka dla typu pizzy

```python
def _ask_for_empty_box_pickup_waypoint(self, pizza_type: int) -> str:
    with self.db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT * FROM storage_item_slot WHERE item_description_id = %s AND slot_name LIKE %s ORDER BY slot_name ASC",
            (pizza_type, "%SCP%"),
        )
        item_slot_product = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]

        box_stack_array = [("SCF" + x["slot_name"][3:5]) for x in item_slot_product]
        if box_stack_array:
            placeholders = ",".join(["%s"] * len(box_stack_array))
            cursor.execute(
                f"SELECT * FROM storage_item_slot WHERE slot_name IN ({placeholders}) ORDER BY slot_name ASC",
                box_stack_array,
            )
            item_slot_full = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]

    for tray_stack, container_stack in zip(item_slot_product, item_slot_full):
        if tray_stack["current_quantity"] > 0:
            level = container_stack["current_quantity"]
            return self._generate_waypoint_name(container_stack["slot_name"], level)
    raise Exception("Brak pudeł na stosie")
```

### Odkładanie pustego pudełka – wybór strony i miejsca

```python
def _put_down_waypoint(self, waypoint_name: str) -> str:
    # prawa strona dla < 8, lewa strona dla >= 8
    if 10 * int(waypoint_name[3]) + int(waypoint_name[4]) < 8:
        container_names = ["SCE01", "SCE02", "SCE03", "SCE04", "SCE05", "SCE06"]
    else:
        container_names = ["SCE07", "SCE08", "SCE09", "SCE10", "SCE11", "SCE12"]

    with self.db_connection.cursor() as cursor:
        placeholders = ",".join(["%s"] * len(container_names))
        cursor.execute(
            f"SELECT * FROM storage_item_slot WHERE slot_name IN ({placeholders})",
            container_names,
        )
        item_slots = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]

    item_slots = [s for s in item_slots if s["current_quantity"] < s["max_quantity"]]
    # preferuj slot z największym zapasem miejsca
    item_slot = max(item_slots, key=lambda x: (x["max_quantity"] - x["current_quantity"]))
    return self._generate_waypoint_name(item_slot["slot_name"], item_slot["current_quantity"] + 1)
```

## Rotacja pieca i QR dla tacek

Dla wybranych stosów i tacek można nadpisać domyślny obrót pieca `90°` i rotację QR `False`:

```python
def get_stack_to_oven_rotation(self, stack_number: str, tray_number: str) -> tuple[int, bool]:
    default_oven_rotation = 90
    default_qr_rotation = False
    if stack_number in specific_stack_to_oven_rotation:
        if tray_number in specific_stack_to_oven_rotation[stack_number]:
            return (
                specific_stack_to_oven_rotation[stack_number][tray_number]["oven_rotation"],
                specific_stack_to_oven_rotation[stack_number][tray_number]["qr_rotation"],
            )
    return default_oven_rotation, default_qr_rotation
```

## Algorytmy pobierania pizzy (tacek)

### Sprawdzenie dostępności tacki (v1 i v2)

- **v1** – prosta kontrola spójności liczby tacek w pojemniku vs. liczba pudełek:

```python
def is_tray_available(self, pizza_type: int) -> bool:
    # ... pobranie stosów SCPxx i odpowiadających SCFxx ...
    for tray_stack, container_stack in zip(item_slot_product, item_slot_full):
        if tray_stack["current_quantity"] > 0:
            if (
                tray_stack["current_quantity"] / 4 <= container_stack["current_quantity"]
                and tray_stack["current_quantity"] / 4 + 1 > container_stack["current_quantity"]
            ):
                return True
    return False
```

- **v2** – priorytet dla rozpoczętych pojemników i sortowanie (remis po nazwie slotu):

```python
def _sort_stacks_by_container_priority_v2(self, pizza_stacks, box_stacks):
    # klucz: (rozpoczęty? 0:1, -liczba_pojemników, nazwa_slotu)
    # zapewnia kolejność: rozpoczęte → więcej pojemników → alfabetycznie
```

### Wyznaczanie waypointu pobrania tacki (v1 vs v2)

```python
def _ask_for_pizza_pickup_waypoint(self, pizza_type: int, box_first: bool) -> tuple[str, int, bool] | None:
    # ... wybór po SQL ORDER BY ... wyznaczenie tacki i waypointu ...

def _ask_for_pizza_pickup_waypoint_v2(self, pizza_type: int, box_first: bool) -> tuple[str, int, bool] | None:
    # ... to samo, ale po wcześniejszym sortowaniu _v2 ...
```

### Sekwencja przeniesienia pizzy do pieca (v1 vs v2)

- **v1** – w razie braku tacki najpierw pobierane jest pudełko (z domyślnej logiki), następnie tacka.
- **v2** – identyczny przepływ, ale z poprawką: pudełko jest brane z TEGO SAMEGO stosu co tacka.

```python
def seq_pizza_to_oven(self, pizza_type, current_pos) -> dict:
    # v1 – korzysta z is_tray_available i _ask_for_pizza_pickup_waypoint

def seq_pizza_to_oven_v2(self, pizza_type, current_pos) -> dict:
    # v2 – korzysta z is_tray_available_v2 oraz _ask_for_pizza_pickup_waypoint_v2
    #     + pobiera box z tego samego stosu co tacka
```

## Operacje aktualizujące stan magazynu

```python
def pickup_box_from_stack(self, waypoint: str) -> bool:
    # decrement current_quantity dla slotu SCFxx wskazanego w waypoint

def put_down_empty_box(self, waypoint: str, formated_time: str | None = None) -> None:
    # increment current_quantity dla slotu SCExx/SCFxx (zależnie od waypointu)

def remove_pizza_from_stack(self, waypoint: str, formated_time: str | None = None) -> None:
    # decrement current_quantity dla slotu SCPxx powiązanego z waypointem tacki

def place_tray_in_box(self, slot_name: str) -> None:
    # increment current_quantity dla slotu SCFxx
```

## Napoje – wybór i aktualizacja

```python
def ask_for_drink(self, item_description_id: int) -> str | None:
    # wybierz slot z maksymalną dostępnością; None, jeśli brak

def remove_drink(self, slot_name: str) -> None:
    # decrement current_quantity dla slotu napoju
```

## Integracja z innymi komponentami

- **MUNCHIES ALGO** (`munchies_algo`) wywołuje metody `Warehouse` przy budowaniu sekwencji dla produktów (por. rozdział „Sequence Handlers” w dokumentacji MUNCHIES).
- **IO Event Listener** odpowiada za wykonanie fizycznych akcji (ruchy robota, czujniki) – `Warehouse` dostarcza waypointy i decyzje logistyczne, które IO realizuje.
- **Orchestrator** może koordynować scenariusze, w ramach których MUNCHIES i IO korzystają z `Warehouse` jako źródła waypointów i stanów.

## Uwagi implementacyjne i dobre praktyki

- Operacje na DB są wykonywane w transakcjach poprzez `cursor` i `commit()` – unikaj długich transakcji i upewnij się, że połączenie DB jest współdzielone w obrębie komponentu.
- Zachowuj spójność między liczbą tacek a poziomami w pojemnikach (`4 szt./pojemnik`). Wersje metod `_v2` pomagają preferować rozpoczęte pojemniki i redukować fragmentację.
- Logowanie przez `MessageLogger` (`debug/info/error`) ułatwia diagnozę problemów i integrację z resztą systemu.

## Kod
:::: munchies.warehouse
    options:
      members_order: source
      show_root_heading: true
      show_source: true


