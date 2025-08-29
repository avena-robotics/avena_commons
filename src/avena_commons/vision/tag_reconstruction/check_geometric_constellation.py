"""
Moduł do walidacji geometrycznych konstelacji tagów wizyjnych.

Zasady działania:
--------------
Moduł implementuje algorytm walidacji poprawności geometrycznej konstelacji
tagów wizyjnych poprzez porównanie cech geometrycznych między układem
referencyjnym a układem wykrytym w scenie.

Algorytm walidacji:
------------------
1. **Porównanie liczby punktów**: Sprawdzenie czy liczba centroidów się zgadza
2. **Analiza odległości**: Porównanie względnych odległości między punktami
3. **Walidacja kątów**: Sprawdzenie kątów między trójkami punktów
4. **Normalizacja**: Standaryzacja cech geometrycznych dla porównania
5. **Tolerancja**: Uwzględnienie dopuszczalnych różnic w parametrach

Zastosowania:
- Walidacja poprawności wykrytych tagów wizyjnych
- Filtrowanie fałszywych detekcji
- Zapewnienie jakości rekonstrukcji tagów
- Kontrola poprawności mapowania perspektywicznego
"""

import numpy as np

import avena_commons.vision.tag_reconstruction as tag_reconstruction


def check_geometric_constellation(
    reference_centroids,
    scene_centroids,
    max_distance_ratio=0.3,
    max_angle_diff=15.0,
):
    """
    Sprawdza, czy układ centroidów w scenie odpowiada układowi referencyjnemu.

    Funkcja implementuje zaawansowany algorytm walidacji geometrycznej,
    który porównuje cechy geometryczne między układem referencyjnym a
    układem wykrytym w scenie, uwzględniając tolerancje na różnice.

    Zasada działania:
    ----------------
    1. **Walidacja liczby punktów**: Sprawdzenie czy liczba centroidów się zgadza
    2. **Obliczenie cech**: Wyznaczenie cech geometrycznych dla obu układów
    3. **Analiza odległości**: Porównanie względnych odległości między punktami
    4. **Walidacja kątów**: Sprawdzenie kątów między trójkami punktów
    5. **Normalizacja**: Standaryzacja cech dla niezależnego od skali porównania
    6. **Tolerancja**: Uwzględnienie dopuszczalnych różnic w parametrach

    Parametry:
    ----------
    reference_centroids : list or np.ndarray
        Lista centroidów z układu referencyjnego (wzorcowego)

    scene_centroids : list or np.ndarray
        Lista centroidów wykrytych w scenie

    max_distance_ratio : float, default=0.3
        Maksymalna dopuszczalna różnica w stosunku odległości (0.3 = 30%)

    max_angle_diff : float, default=15.0
        Maksymalna dopuszczalna różnica w kątach w stopniach

    Zwraca:
    -------
    bool
        True jeśli konstelacje są geometrycznie zgodne, False w przeciwnym przypadku

    Przykład:
    ---------
    >>> ref_centroids = [[100, 100], [200, 100], [150, 200]]
    >>> scene_centroids = [[105, 98], [198, 102], [152, 195]]
    >>> is_valid = check_geometric_constellation(ref_centroids, scene_centroids)
    >>> print(f"Konstelacja jest poprawna: {is_valid}")

    Uwagi:
    ------
    - Odległości są normalizowane przez największą odległość w każdym układzie
    - Kąty są porównywane tylko jeśli są dostępne w obu układach
    - Funkcja zwraca False jeśli nie można obliczyć cech geometrycznych
    - Tolerancje można dostosować do wymagań aplikacji
    """
    if len(reference_centroids) != len(scene_centroids):
        return False

    ref_features = tag_reconstruction.calculate_geometric_features(reference_centroids)
    scene_features = tag_reconstruction.calculate_geometric_features(scene_centroids)

    if ref_features is None or scene_features is None:
        return False

    # Sprawdź stosunek odległości
    ref_distances = ref_features["distances"]
    scene_distances = scene_features["distances"]

    # Normalizuj odległości przez największą odległość
    if np.max(ref_distances) > 0 and np.max(scene_distances) > 0:
        ref_distances_norm = ref_distances / np.max(ref_distances)
        scene_distances_norm = scene_distances / np.max(scene_distances)

        # Sprawdź różnice w odległościach
        distance_diff = np.abs(ref_distances_norm - scene_distances_norm)
        if np.max(distance_diff) > max_distance_ratio:
            return False

    # Sprawdź różnice w kątach (jeśli są dostępne)
    if len(ref_features["angles"]) > 0 and len(scene_features["angles"]) > 0:
        ref_angles = np.array(ref_features["angles"])
        scene_angles = np.array(scene_features["angles"])

        if len(ref_angles) == len(scene_angles):
            angle_diff = np.abs(ref_angles - scene_angles)
            if np.max(angle_diff) > max_angle_diff:
                return False

    return True
