"""
Moduł do obliczania cech geometrycznych dla tagów wizyjnych.

Zasady działania:
--------------
Moduł ten implementuje algorytmy do analizy geometrycznej zbiorów punktów (centroidów)
wykrytych w obrazach wizyjnych. Główne funkcjonalności obejmują:

1. Obliczanie macierzy odległości między wszystkimi parami punktów
2. Analizę kątów między trójkami punktów (trójkąty)
3. Określanie cech opisowych jak centroid, bounding box i rozpiętość

Algorytm kątów:
- Dla każdej trójki punktów (i, j, k) obliczany jest kąt w wierzchołku j
- Używany jest iloczyn skalarny i normy wektorów do obliczenia kąta
- Kąty są konwertowane na stopnie dla lepszej interpretacji

Zastosowania:
- Analiza wzorców geometrycznych tagów QR/AR
- Walidacja poprawności wykrytych punktów
- Klasyfikacja kształtów i układów wizyjnych
"""

import numpy as np


def calculate_geometric_features(centroids):
    """
    Oblicza cechy geometryczne dla zbioru centroidów wykrytych w obrazie.

    Funkcja analizuje wzorce geometryczne między punktami, co jest kluczowe
    dla walidacji poprawności wykrytych tagów wizyjnych. Implementuje:

    - Macierz odległości: odległości euklidesowe między wszystkimi parami punktów
    - Analizę kątów: kąty między trójkami punktów tworzącymi trójkąty
    - Cechy opisowe: centroid, bounding box i rozpiętość przestrzenną

    Parametry:
    ----------
    centroids : list or np.ndarray
        Lista lub tablica punktów [x, y] reprezentujących centroidy tagów

    Zwraca:
    -------
    dict or None
        Słownik zawierający:
        - 'distances': macierz odległości między punktami
        - 'angles': lista kątów między trójkami punktów (w stopniach)
        - 'centroid': średni punkt wszystkich centroidów
        - 'bounding_box': (min_x, min_y), (max_x, max_y)
        - 'span': rozpiętość przestrzenna (szerokość, wysokość)

        Zwraca None jeśli mniej niż 2 punkty

    Przykład:
    ---------
    >>> centroids = [[100, 100], [200, 100], [150, 200]]
    >>> features = calculate_geometric_features(centroids)
    >>> print(f"Centroid: {features['centroid']}")
    >>> print(f"Liczba kątów: {len(features['angles'])}")
    """
    if len(centroids) < 2:
        return None

    centroids = np.array(centroids)

    # Oblicz macierz odległości
    distances = np.linalg.norm(centroids[:, None] - centroids[None, :], axis=2)

    # Oblicz kąty między parami punktów
    angles = []
    for i in range(len(centroids)):
        for j in range(i + 1, len(centroids)):
            for k in range(j + 1, len(centroids)):
                # Kąt między trzema punktami (i, j, k)
                v1 = centroids[i] - centroids[j]
                v2 = centroids[k] - centroids[j]

                # Oblicz kąt
                dot_product = np.dot(v1, v2)
                norms = np.linalg.norm(v1) * np.linalg.norm(v2)
                if norms > 0:
                    angle = np.arccos(np.clip(dot_product / norms, -1.0, 1.0))
                    angles.append(np.degrees(angle))

    return {
        "distances": distances,
        "angles": angles,
        "centroid": np.mean(centroids, axis=0),
        "bounding_box": (np.min(centroids, axis=0), np.max(centroids, axis=0)),
        "span": np.max(centroids, axis=0) - np.min(centroids, axis=0),
    }
