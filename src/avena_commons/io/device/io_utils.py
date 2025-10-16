"""Funkcje pomocnicze do inicjalizacji urządzeń IO.

Udostępnia uproszczenia do dynamicznego tworzenia właściwości odczytu/zapisu
dla wejść cyfrowych (DI) i wyjść cyfrowych (DO) w klasach urządzeń. Dzięki temu
możliwe jest wygodne odwoływanie się do sygnałów jako `di0`, `di1`, ... oraz
`do0`, `do1`, ... zamiast stosowania wywołań metod z indeksami.
"""


def init_device_di(cls, first_index=0, count=16):
    """Inicjalizuje właściwości wejść cyfrowych (DI) dla klasy urządzenia.

    Na wskazanej klasie dynamicznie tworzy właściwości `di0`, `di1`, ... `diN`,
    które mapują się na wywołania metody `di(index)` obiektu. Ułatwia to
    odczyt stanu wejść cyfrowych bezpośrednio przez atrybuty.

    Args:
        cls: Klasa urządzenia, do której zostaną dodane właściwości.
        first_index (int): Indeks początkowy wejść cyfrowych (domyślnie 0).
        count (int): Liczba tworzonych wejść cyfrowych (domyślnie 16).
    """
    for i in range(count):

        def getter(self, idx=first_index + i):
            return self.di(idx)

        setattr(cls, f"di{first_index + i}", property(getter))


def init_device_do(cls, first_index=0, count=16):
    """Inicjalizuje właściwości wyjść cyfrowych (DO) dla klasy urządzenia.

    Na wskazanej klasie dynamicznie tworzy właściwości `do0`, `do1`, ... `doN`,
    które mapują się na wywołania metody `do(index)` obiektu (z obsługą zapisu).
    Ułatwia to odczyt i ustawianie stanu wyjść cyfrowych bezpośrednio przez atrybuty.

    Args:
        cls: Klasa urządzenia, do której zostaną dodane właściwości.
        first_index (int): Indeks początkowy wyjść cyfrowych (domyślnie 0).
        count (int): Liczba tworzonych wyjść cyfrowych (domyślnie 16).
    """
    for i in range(count):

        def getter(self, idx=first_index + i):
            return self.do(idx)

        def setter(self, value, idx=first_index + i):
            return self.do(idx, value)

        setattr(cls, f"do{first_index + i}", property(getter, setter))
