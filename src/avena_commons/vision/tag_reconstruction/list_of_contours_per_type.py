import numpy as np


def list_of_contours_per_type(cnts_dict: list[dict]) -> list[list[np.ndarray]]:
    """
    Zwraca listę konturów pogrupowanych według typu.

    Funkcja reorganizuje kontury z formatu słownikowego (gdzie każdy
    kontur ma przypisany typ) na format listowy, grupując je według
    indeksów typów. Jest to kluczowy element w przygotowaniu danych
    dla algorytmów mapowania perspektywicznego.

    Zasada działania:
    ----------------
    1. **Inicjalizacja**: Utworzenie pustych list dla każdego typu
    2. **Iteracja po słowniku**: Analiza każdego wpisu w słowniku konturów
    3. **Grupowanie według typu**: Przypisanie konturu do odpowiedniej listy
    4. **Struktura wyjściowa**: Lista list konturów pogrupowanych według typu

    Parametry:
    ----------
    cnts_dict : list[dict]
        Lista słowników, gdzie każdy zawiera:
        - 'cnt': kontur w formacie numpy array
        - 'type': indeks typu konturu

    Zwraca:
    -------
    list[list[np.ndarray]]
        Lista list, gdzie każda lista zawiera kontury danego typu.
        Indeks listy odpowiada indeksowi typu.

    Przykład:
    ---------
    >>> contours_dict = [
    ...     {'cnt': cnt1, 'type': 0},
    ...     {'cnt': cnt2, 'type': 1},
    ...     {'cnt': cnt3, 'type': 0},
    ...     {'cnt': cnt4, 'type': 2}
    ... ]
    >>> grouped = list_of_contours_per_type(contours_dict)
    >>> print(f"Typ 0: {len(grouped[0])} konturów")
    >>> print(f"Typ 1: {len(grouped[1])} konturów")
    >>> print(f"Typ 2: {len(grouped[2])} konturów")

    Uwagi:
    ------
    - Funkcja zakłada, że typy są kolejno numerowane od 0
    - Kontury są grupowane według indeksu typu
    - Struktura wyjściowa jest listą list dla łatwego dostępu
    - Jest to funkcja pomocnicza w pipeline'ie przetwarzania konturów
    """
    cnts_per_type = []
    current_type = 0
    for cnt_info in cnts_dict:
        type_idx = cnt_info["type"]
        if type_idx == current_type:
            cnts_per_type.append(cnt_info["cnt"])
            current_type += 1
    return cnts_per_type
