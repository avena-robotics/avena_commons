"""
Moduł do filtrowania i grupowania konturów referencyjnych.

Zasady działania:
--------------
Moduł implementuje algorytm filtrowania i grupowania konturów
referencyjnych na podstawie podobieństwa kształtu. Proces obejmuje
sortowanie według obszaru, filtrowanie największych konturów i
grupowanie według podobieństwa geometrycznego.

Algorytm filtrowania:
--------------------
1. **Sortowanie według obszaru**: Kontury są sortowane malejąco według powierzchni
2. **Filtrowanie największych**: Usunięcie 2 największych konturów (prawdopodobnie tło)
3. **Grupowanie według podobieństwa**: Użycie cv2.matchShapes z progiem 0.05
4. **Przypisanie typów**: Każda grupa otrzymuje unikalny indeks typu
5. **Struktura wyjściowa**: Lista słowników z konturem i typem

Zastosowania:
- Filtrowanie konturów referencyjnych dla tagów wizyjnych
- Grupowanie podobnych kształtów w algorytmach wizyjnych
- Przygotowanie danych do mapowania perspektywicznego
- Standaryzacja konturów referencyjnych
"""

import cv2
import numpy as np


def filter_reference_contours(cnts: list[np.ndarray]) -> list[dict]:
    """
    Filtruje i grupuje kontury referencyjne według podobieństwa kształtu.

    Funkcja implementuje zaawansowany algorytm filtrowania, który
    sortuje kontury według obszaru, usuwa największe (prawdopodobnie tło)
    i grupuje pozostałe według podobieństwa kształtu używając OpenCV matchShapes.

    Zasada działania:
    ----------------
    1. **Sortowanie według obszaru**: Kontury są sortowane malejąco według powierzchni
    2. **Filtrowanie największych**: Usunięcie 2 największych konturów (prawdopodobnie tło)
    3. **Grupowanie według podobieństwa**: Użycie cv2.matchShapes z progiem 0.05
    4. **Przypisanie typów**: Każda grupa otrzymuje unikalny indeks typu
    5. **Struktura wyjściowa**: Lista słowników z konturem i typem

    Parametry:
    ----------
    cnts : list[np.ndarray]
        Lista konturów referencyjnych do przefiltrowania

    Zwraca:
    -------
    list[dict]
        Lista słowników, gdzie każdy zawiera:
        - 'cnt': kontur referencyjny
        - 'type': indeks typu (grupowania)

    Przykład:
    ---------
    >>> reference_contours = [cnt1, cnt2, cnt3, cnt4, cnt5]
    >>> filtered = filter_reference_contours(reference_contours)
    >>> for item in filtered:
    ...     print(f"Typ {item['type']}: kontur o obszarze {cv2.contourArea(item['cnt'])}")

    Uwagi:
    ------
    - Kontury są sortowane według obszaru (malejąco)
    - 2 największe kontury są automatycznie usuwane
    - Próg podobieństwa jest ustawiony na 0.05
    - Używa OpenCV CONTOURS_MATCH_I1 dla porównania kształtów
    - Każda grupa otrzymuje unikalny indeks typu
    """
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)
    cnts = cnts[2:]  # filter out 2 largest contours

    groups = []
    assigned = [False] * len(cnts)
    threshold = 0.05

    for i, cnt in enumerate(cnts):
        if assigned[i]:
            continue
        group = [i]
        assigned[i] = True
        for j in range(i + 1, len(cnts)):
            if not assigned[j]:
                similarity = cv2.matchShapes(cnt, cnts[j], cv2.CONTOURS_MATCH_I1, 0.0)
                if similarity < threshold:
                    group.append(j)
                    assigned[j] = True
        groups.append(group)

    result = []
    for type_idx, group in enumerate(groups):
        for idx in group:
            result.append({"cnt": cnts[idx], "type": type_idx})

    return result
