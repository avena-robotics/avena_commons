"""
Moduł do tworzenia wzorców referencyjnych tagów wizyjnych.

Zasady działania:
--------------
Moduł implementuje proces tworzenia wzorców referencyjnych z obrazu tagu,
które są następnie używane do mapowania i rekonstrukcji tagów w obrazach
docelowych. Proces obejmuje wykrywanie konturów, filtrowanie i kategoryzację.

Pipeline przetwarzania:
1. Wykrycie konturów w obrazie tagu referencyjnego
2. Filtrowanie konturów według kryteriów jakościowych
3. Kategoryzacja konturów według typów geometrycznych
4. Tworzenie słownika z wszystkimi potrzebnymi danymi referencyjnymi

Zastosowania:
- Tworzenie wzorców do mapowania perspektywicznego
- Referencja dla algorytmów rekonstrukcji tagów
- Standaryzacja procesu analizy tagów wizyjnych
"""

import numpy as np

import avena_commons.vision.tag_reconstruction as tag_reconstruction


def create_reference_tag_shapes(
    tag_image: np.ndarray,
) -> dict:  # MARK: create reference tag shapes
    """
    Tworzy wzorce referencyjne tagów z obrazu wejściowego.

    Funkcja przetwarza obraz tagu referencyjnego, aby utworzyć wzorce
    geometryczne używane później do mapowania i rekonstrukcji tagów
    w obrazach docelowych.

    Zasada działania:
    ----------------
    1. Wykrycie wszystkich konturów w obrazie tagu
    2. Filtrowanie konturów według kryteriów jakościowych
    3. Kategoryzacja konturów według typów geometrycznych
    4. Zgromadzenie wszystkich danych w słowniku wyjściowym

    Parametry:
    ----------
    tag_image : np.ndarray
        Obraz tagu referencyjnego (skala szarości lub RGB)

    Zwraca:
    -------
    dict
        Słownik zawierający:
        - 'ref_cnts': skategoryzowane kontury referencyjne
        - 'cnts_dict': wszystkie wykryte kontury z metadanymi
        - 'image': oryginalny obraz tagu referencyjnego

    Przykład:
    ---------
    >>> ref_shapes = create_reference_tag_shapes(reference_tag_image)
    >>> contours = ref_shapes['ref_cnts']
    >>> all_contours = ref_shapes['cnts_dict']
    """
    contours = tag_reconstruction.find_contours(tag_image)
    cnts_dict = tag_reconstruction.filter_reference_contours(contours)
    ref_cnts = tag_reconstruction.list_of_contours_per_type(cnts_dict)

    output = {}
    output["ref_cnts"] = ref_cnts
    output["cnts_dict"] = cnts_dict
    output["image"] = tag_image

    return output
