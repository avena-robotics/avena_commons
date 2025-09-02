# Dokumentacja Wewnętrznej Logiki MUNCHIES ALGO

## Przegląd Systemu

System MUNCHIES ALGO to zaawansowany algorytm zarządzający automatycznym procesem przygotowywania i wydawania zamówień w systemie vendingowym. Opiera się na architekturze event-driven (zdarzeniowej) z asynchronicznym przetwarzaniem zdarzeń i stanami maszyn skończonych (FSM).

**Repozytorium**: [event_driven_proof_of_concept](https://github.com/avena-robotics/event_driven_proof_of_concept)

## Struktura Danych

### Główne Struktury Stanu

System przechowuje stan w słowniku `_state` zawierającym:

```python
_state = {
    "zamowienia_w_trakcie_realizacji": {},  # Dict[int, Order] - aktywne zamówienia
    "piec": Piec(piec_state=PiecState.NIEZNANY),  # Stan pieca
    "ups": UPS(ups_state=UPSState.NIEZNANY),  # Stan zasilania
    "kds": Kds(state=KdsState.UNINITIALIZED),  # Stan systemu wyświetlania
    "system_pieca": SystemPieca(),  # Manager torów pieca
    "system_wydawczy": SystemWydawczy(),  # Manager wydawek
    "roboty": {
        1: Robot(id=1, current_waypoint="OI___normal"),
        2: Robot(id=2, current_waypoint="default")
    }
}
```

### Kluczowe Typy Danych

#### Order (Zamówienie)
```python
class Order(BaseModel):
    id: int
    origin: str
    pickup_number: Optional[int] = None
    kds_order_number: Optional[int] = None
    status: str
    products: List[Item] = []
    can_dispence_souces: Optional[bool] = False
    start_timestamp: Optional[str] = None
```

#### Item (Produkt)
```python
class Item(BaseModel):
    id: int
    item_id: int
    item_category: dict[str, str]  # {"item_category": "drink" | "snack" | "sauce"}
    status: str
    aps_id: int
    aps_order_id: int
    pole_wydawki: Optional[int] = None
    sekwencja: Optional[Sequence] = None
    handler: Optional[BaseModel] = None
```

#### TorPieca (Tor Pieca)
```python
class TorPieca(BaseModel):
    id: int
    entry_is_free: bool = True
    exit_is_free: bool = True
    pola: List[Optional[int]] = [None, None, None, None, None]
    entry_block_timestamp: Optional[datetime] = None
    entry_block_duration_seconds: float = 5.0
```

#### Wydawka (Dispenser)
```python
class Wydawka(BaseModel):
    id: int
    feeder: FeederTacek         # Feeder tacek
    komora_odbiorcza: KomoraOdbiorcza  # Komora odbiorcza
    tor_wydawki: TorWydawki     # Tor z 10 polami (bufor FIFO)
    feedery_sosow: List[FeederSosow]   # Feedery sosów
    _fsm: KomoraOdbiorczaState  # Stan FSM
    last_placing_place: int = 8  # Ostatnie miejsce układania
```

## Główne Klasy i Funkcje

### MunchiesAlgo (Rdzeń Systemu)

**Lokalizacja**: `lib/munchies/munchies_algo.py`

Główna klasa dziedzicząca po `EventListener`, zarządzająca całym systemem.

#### Kluczowe Metody:

```python
async def _analyze_event(self, event: Event) -> bool:
    """
    Analizuje i kieruje eventy do odpowiednich handlerów.
    Routing: supervisor_1/2 -> __supervisor_handler
             io -> __io_handler
             kds -> __kds_handler
    """

async def _check_local_data(self):
    """
    Główna pętla systemu (10Hz). Przetwarza:
    - Sekwencje produktów
    - Logikę zamówień (rozpoczynanie/kończenie)
    - Stany urządzeń (piec, wydawki)
    - Inicjalizację systemów
    """

def __znajdz_produkt_w_zamowieniach(self, produkt_id: int) -> Item:
    """Znajduje produkt w aktywnych zamówieniach po ID"""

async def __przetwarzaj_sekwencje_produktu(self, produkt: Item):
    """Przetwarza sekwencję dla danego produktu"""
```

### SystemPieca (Manager Pieca)

**Lokalizacja**: `lib/munchies/system_pieca.py`

Zarządza 3 torami pieca z kolejkami FIFO.

```python
class SystemPieca(BaseModel):
    tory_pieca: Dict[int, TorPieca] = {
        1: TorPieca(id=1), 2: TorPieca(id=2), 3: TorPieca(id=3)
    }
    
    def enqueue(self, numer_toru: int, produkt: Item) -> bool:
        """Dodaje produkt do kolejki toru"""
    
    def dequeue(self, numer_toru: int) -> Optional[int]:
        """Usuwa produkt z kolejki toru"""
    
    def set_entry_is_free(self, numer_toru: int, value: bool, delay_seconds: float = 5):
        """Ustawia stan wejścia z opcjonalnym opóźnieniem"""

    def set_exit_is_free(self, numer_toru: int, value: bool):
        """Ustawia stan wyjścia toru pieca"""

    def peek(self, numer_toru: int) -> Optional[int]:
        """Podgląd pierwszego produktu w kolejce (bez usuwania)"""

    def unblock_entry_if_time_elapsed(self, numer_toru: int) -> bool:
        """Automatyczne odblokowanie wejścia po upływie zadanego czasu"""

    def oblozenie_pieca(self, numer_toru: int) -> float:
        """Zwraca ułamek zajętości kolejki 0..1"""
```

### SystemWydawczy (Manager Wydawek)

**Lokalizacja**: `lib/munchies/system_wydawczy.py`

Zarządza 3 wydawkami z 10-polowymi torami.

```python
class SystemWydawczy(BaseModel):
    wydawka: Dict[int, Wydawka] = {}
    
    def czy_wydawka_dostepna_do_nowego_produktu(self, numer_wydawki: int) -> bool:
        """Sprawdza dostępność wydawki dla nowego produktu"""
    
    def rezerwuje_pole_wydawki_dla_produktu(self, numer_wydawki: int, nr_pola: int, 
                                           produkt_id: int, order_id: int) -> bool:
        """Rezerwuje pole na wydawce dla produktu"""
    
    def rozpocznij_nowe_zamowienie_jezeli_to_mozliwe(self):
        """Rozpoczyna nowe zamówienie jeśli warunki spełnione"""
```

### OrdersManager (Manager Zamówień)

**Lokalizacja**: `lib/munchies/orders_manager.py`

Obsługuje interakcje z bazą danych PostgreSQL.

```python
class OrdersManager:
    def fetch_orders_with_status(self, status: OrderStatus) -> List[Order]:
        """Pobiera zamówienia o określonym statusie"""
    
    def change_order_status(self, order_id: str, status: OrderStatus, 
                           conveyor: int = None, eta: int = None) -> bool:
        """Zmienia status zamówienia"""
    
    def change_product_status(self, product: Item, status: ProductStatus) -> Item:
        """Zmienia status produktu"""
```

### Sequence Handlers (Obsługa Sekwencji)

**Lokalizacja**: `lib/munchies/sequence_handlers/`

Każdy typ produktu ma dedykowany handler sekwencji:

#### KladzenieProduktuNaPiecHandler
```python
class SekwencjaKladzenieProduktuNaPiec(IntEnum):
    POLOZENIE_TACKI_NA_POLE_WYDAWKI = 1
    USTALENIE_PARAMETROW = 2
    WYKONANIE_RUCHU_NAD_PUSTY_POJEMNIK = 3
    WYKONANIE_ZDJECIA_POJEMNIKA = 4
    WLACZENIE_POMPY_1 = 5
    # ... kolejne kroki
```

#### OdbiorNapojuZMagazynuHandler
```python
class SekwencjaOdbioruNapojuZMagazynu(IntEnum):
    USTALENIE_PARAMETROW = 1
    WYKONANIE_RUCHU_DOJAZD_DO_MAGAZYNU = 2
    WLACZENIE_POMPY = 3
    # ... kolejne kroki
```

## Kolejka Zdarzeń

### Architektura Event-Driven

System używa asynchronicznej kolejki zdarzeń z następującymi źródłami:

1. **Supervisor Events** (Roboty):
   - `move_l` - ruch robota po ścieżce
   - `pump_on` / `pump_off` - sterowanie pompą
   - `take_photo_box` - zdjęcie boxa
   - `take_photo_qr` - zdjęcie QR

2. **IO Events** (Czujniki/Urządzenia):
   - `oven_start/restart` - sterowanie piecem
   - `oven_sensor_state` - sygnały z czujników pieca (OIC/OOC)
   - `chamber_initialize` - inicjalizacja komory
   - `wydawka_move` - ruch wydawki
   - `sauce_run` - wydanie saszetki sosu z feedera
   - `sauce_rebase` - rebase/kalibracja feedera sosu
   - `sauce_is_present` - czujnik obecności saszetki w komorze

3. **KDS Events** (System Wyświetlania):
   - `order_update` - aktualizacja statusu zamówienia
   - `send_sms_notification` - powiadomienia SMS

### Przetwarzanie Zdarzeń

```python
async def _analyze_event(self, event: Event) -> bool:
    match event.source.lower():
        case "supervisor_1":
            return await self.__supervisor_handler(1, event)
        case "supervisor_2":
            return await self.__supervisor_handler(2, event)
        case "io":
            return await self.__io_handler(event)
        case "kds":
            return await self.__kds_handler(event)
```

### Wysyłanie Zdarzeń

```python
async def _send_event_to_supervisor(self, supervisor_number: int, event_type: str, 
                                   data: Dict, maximum_processing_time: float = 20):
    """Wysyła event do supervisora z timeoutem"""

async def _send_event_to_io(self, event_type: str, data: Dict, 
                           maximum_processing_time: float = 3):
    """Wysyła event do systemu IO"""
```

### Mapowanie ID feederów sosów

- `device_id` dla sosów jest kodowany jako liczba dwucyfrowa: `xy`, gdzie `x = wydawka_id (1..3)`, `y = feeder_id (1..3)`.
- Przykłady: `11, 12, 13` (wydawka 1), `21, 22, 23` (wydawka 2), `31, 32, 33` (wydawka 3).
- Alternatywnie obsługiwany jest stary schemat: `device_id = wydawka_id`, `subdevice_id = feeder_id`.

## Obsługa Wyjątków

### Strategia Obsługi Błędów

1. **Try-Catch na Wysokim Poziomie**:
```python
async def _check_local_data(self):
    try:
        # Główna logika
        pass
    except Exception as e:
        error(f"Error in check_local_data: {str(e)}", message_logger=self._message_logger)
        error(traceback.format_exc(), message_logger=self._message_logger)
```

2. **Timeouty na Eventach**:
```python
event = await self._send_event_to_supervisor(
    supervisor_number=1,
    event_type="move_l",
    data=data,
    maximum_processing_time=20  # Timeout 20s
)
```

3. **Stany Awaryjne**:
```python
# Przy błędzie - powrót do stanu NIEZNANY
if not event.result or event.result.result != "success":
    self._state["piec"].piec_state = PiecState.NIEZNANY
```

4. **Walidacja Danych**:
```python
if not all([db_host, db_name, db_user, db_password]):
    raise ValueError("Brak wymaganych parametrów połączenia z bazą danych")
```

### Logowanie Błędów

```python
# Strukturalne logowanie z MessageLogger
error(f"Błąd podczas ruchu wydawki {event.data['device_id']}", 
      message_logger=self._message_logger)

# Logowanie z traceback
error(traceback.format_exc(), message_logger=self._message_logger)
```

## Przykłady Kodu

### Przykład 1: Przetwarzanie Zamówienia

```python
# W pętli _check_local_data - logika inicjacji/kończenia zamówień odbywa się w SystemWydawczy
self._state["system_wydawczy"].rozpocznij_nowe_zamowienie_jezeli_to_mozliwe()
self._state["system_wydawczy"].zakoncz_zamowienie_jezeli_to_mozliwe()
```

### Przykład 2: Obsługa Sekwencji Produktu

```python
# Tworzenie sekwencji dla przekąski
if produkt.get_item_category() == "snack":
    produkt.sekwencja = Sequence(
        produkt_id=produkt.id, 
        enum_class=SekwencjaKladzenieProduktuNaPiec
    )
    
    produkt.handler = KladzenieProduktuNaPiecHandler(
        db_connection=self.db_connection,
        warehouse=self.warehouse,
        path_generator=self.path_generator,
        orders_manager=self.orders_manager,
        state=self._state,
        configuration=self._configuration,
        event_callback=self
    )
    
    # Przetwarzanie sekwencji
    await self.__przetwarzaj_sekwencje_produktu(produkt)
```

### Przykład 3: Obsługa Czujników Pieca

```python
case "oven_sensor_state":
    signal_name = event.data["signal_name"][:3]
    signal_id = int(event.data["signal_name"][-1])
    
    match signal_name:
        case "OIC":  # Wejście zajęte
            if event.data["signal_value"]:
                delay_seconds = self._configuration.get("oven_entry_block_delay_seconds", 30.0)
                self._state["system_pieca"].set_entry_is_free(
                    signal_id, False, delay_seconds=delay_seconds
                )
                
                # Dodaj produkt do kolejki
                produkt = self.__znajdz_produkt_w_zamowieniach(event.id)
                result = self._state["system_pieca"].enqueue(signal_id, produkt)
                
        case "OOC":  # Wyjście zajęte - produkt gotowy
            if event.data["signal_value"]:
                self._state["system_pieca"].set_exit_is_free(signal_id, False)
                # Uruchom sekwencję odbioru
```

## Konfiguracja Systemu

### Domyślna Konfiguracja

```python
_default_configuration = {
    "wydawka_1_enabled": True,
    "wydawka_2_enabled": True, 
    "wydawka_3_enabled": True,
    "robot_1_max_speed": 100,
    "robot_2_max_speed": 100,
    "box_test_move_height": 60,
    "box_photo_height": 600,
    "qr_photo_height": 300,
    "offset_between_orders": 1,
    "oven_entry_block_delay_seconds": 30.0,
    "oven_sensor_timeout": 10.0,
    "error_code_2_timer_timeout": 30
}
```

### Zmienne Środowiskowe

```bash
DB_HOST=localhost
DB_NAME=munchies_db
DB_USER=postgres
DB_PASSWORD=password
MUNCHIES_ALGO_LISTENER_PORT=8001
SUPERVISOR_1_LISTENER_PORT=8002
IO_LISTENER_PORT=8003
KDS_LISTENER_PORT=8004
```

## Podsumowanie

System MUNCHIES ALGO to złożony system event-driven z asynchronicznym przetwarzaniem. Mimo funkcjonalności, wymaga refaktoringu dla lepszej modularności i testowalności. Proponowane zmiany zachowują funkcjonalność, ale poprawiają architekturę i czytelność kodu.

## Kod
::: munchies.munchies_algo
    options:
      members_order: source
      show_root_heading: true
      show_source: true
