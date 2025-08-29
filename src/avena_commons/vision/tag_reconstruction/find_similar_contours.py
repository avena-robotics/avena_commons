"""
Moduł do znajdowania konturów podobnych do referencyjnych.

Zasady działania:
--------------
Moduł implementuje algorytm dopasowywania konturów w scenie do konturów
referencyjnych na podstawie podobieństwa kształtu. Używa funkcji OpenCV
matchShapes do obliczenia miary podobieństwa i klasyfikuje kontury
sceny według najlepszego dopasowania.

Algorytm dopasowywania:
----------------------
1. **Inicjalizacja**: Utworzenie list dla każdego konturu referencyjnego
2. **Iteracja po scenie**: Analiza każdego konturu w scenie
3. **Porównanie kształtów**: Obliczenie miary podobieństwa dla każdej pary
4. **Wybór najlepszego**: Identyfikacja konturu referencyjnego z najniższym wynikiem
5. **Walidacja progu**: Sprawdzenie czy wynik jest poniżej progu podobieństwa
6. **Klasyfikacja**: Przypisanie konturu sceny do odpowiedniej kategorii

Zastosowania:
- Identyfikacja tagów wizyjnych w obrazach
- Kategoryzacja konturów według wzorców referencyjnych
- Filtrowanie konturów według podobieństwa kształtu
- Przygotowanie danych do mapowania perspektywicznego
"""

import cv2
import numpy as np


def find_similar_contours(
    scene_contours: list[np.ndarray],
    reference_contours: list[np.ndarray],
    min_similarity_threshold: float = 0.1,
) -> list[np.ndarray]:
    """
    Znajduje kontury w scenie podobne do konturów referencyjnych.

    Funkcja implementuje algorytm dopasowywania konturów na podstawie
    podobieństwa kształtu. Każdy kontur sceny jest porównywany ze wszystkimi
    konturami referencyjnymi i klasyfikowany według najlepszego dopasowania.

    Zasada działania:
    ----------------
    1. **Inicjalizacja**: Utworzenie pustych list dla każdego konturu referencyjnego
    2. **Iteracja po scenie**: Analiza każdego konturu w scenie
    3. **Porównanie kształtów**: Obliczenie miary podobieństwa dla każdej pary konturów
    4. **Wybór najlepszego**: Identyfikacja konturu referencyjnego z najniższym wynikiem
    5. **Walidacja progu**: Sprawdzenie czy wynik jest poniżej progu podobieństwa
    6. **Klasyfikacja**: Przypisanie konturu sceny do odpowiedniej kategorii

    Parametry:
    ----------
    scene_contours : list[np.ndarray]
        Lista konturów wykrytych w scenie

    reference_contours : list[np.ndarray]
        Lista konturów referencyjnych (wzorcowych)

    min_similarity_threshold : float, default=0.1
        Maksymalny dopuszczalny wynik podobieństwa (niższy = lepsze dopasowanie)

    Zwraca:
    -------
    list[np.ndarray]
        Lista list, gdzie każda lista zawiera kontury sceny podobne do
        odpowiadającego konturu referencyjnego. Jeśli reference_cnts = [cnt1, cnt2, cnt3]
        i scene_cnts = [cnt1, cnt2, cnt3, cnt4, cnt5, cnt6], to wynik może wyglądać
        jak [[cnt1], [cnt2], [cnt3, cnt4, cnt5, cnt6]]

    Przykład:
    ---------
    >>> scene_contours = [scene_cnt1, scene_cnt2, scene_cnt3]
    >>> ref_contours = [ref_cnt1, ref_cnt2]
    >>> similar = find_similar_contours(scene_contours, ref_contours, 0.15)
    >>> print(f"Kontury podobne do ref_cnt1: {len(similar[0])}")
    >>> print(f"Kontury podobne do ref_cnt2: {len(similar[1])}")

    Uwagi:
    ------
    - Używa OpenCV matchShapes z metodą CONTOURS_MATCH_I3
    - Wynik 0.0 oznacza identyczne kształty
    - Niższy wynik = lepsze dopasowanie
    - Kontury niepodobne do żadnego referencyjnego są pomijane
    - W przypadku podobieństwa do wielu konturów wybierany jest najlepszy
    """
    similar_cnts = [[] for _ in reference_contours]

    for scene_cnt in scene_contours:
        # Przechowujemy najlepszy wynik i indeks konturu referencyjnego.
        # Zamiast wartości '1' używam `float('inf')` jako początkowy wynik,
        # co jest bezpieczniejszym podejściem.
        best_match = {"score": float("inf"), "index": None}

        for i, reference_cnt in enumerate(reference_contours):
            # Porównanie kształtów konturów
            score = cv2.matchShapes(
                reference_cnt, scene_cnt, cv2.CONTOURS_MATCH_I3, 0.0
            )

            if score < best_match["score"]:
                best_match["score"] = score

                # Sprawdzenie, czy wynik jest poniżej progu i czy jest to najlepszy
                # dotychczasowy wynik dla tego konturu ze sceny.
                if score < min_similarity_threshold:
                    best_match["score"] = score
                    best_match["index"] = (
                        i  # Przechowujemy indeks, a nie obiekt konturu
                    )

        # Jeśli znaleziono odpowiednie dopasowanie (indeks nie jest już None),
        # dodaj kontur ze sceny do odpowiedniej listy, używając zapisanego indeksu.

        if best_match["index"] is not None:
            similar_cnts[best_match["index"]].append(scene_cnt)

    return similar_cnts
