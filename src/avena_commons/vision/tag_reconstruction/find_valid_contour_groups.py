from itertools import product

import numpy as np

import avena_commons.vision.tag_reconstruction as tag_reconstruction


def find_valid_contour_groups(similar_cnts, ref_cnts, max_distance=100):
    """
    Znajduje grupy konturów, które spełniają relacje geometryczne.

    Funkcja implementuje algorytm identyfikacji grup konturów tworzących
    prawidłowe konstelacje geometryczne. Analizuje wszystkie możliwe
    kombinacje konturów i waliduje ich zgodność z układem referencyjnym.

    Zasada działania:
    ----------------
    1. **Ekstrakcja centroidów**: Obliczenie centroidów konturów referencyjnych
    2. **Walidacja dostępności**: Sprawdzenie czy każdy typ konturu jest dostępny
    3. **Generowanie kombinacji**: Utworzenie wszystkich możliwych kombinacji konturów
    4. **Analiza odległości**: Sprawdzenie maksymalnych odległości między centroidami
    5. **Walidacja geometryczna**: Sprawdzenie zgodności z układem referencyjnym
    6. **Ranking jakości**: Sortowanie grup według jakości dopasowania

    Parametry:
    ----------
    similar_cnts : list
        Lista list konturów, gdzie każda lista zawiera kontury podobne
        do odpowiadającego konturu referencyjnego

    ref_cnts : list
        Lista konturów referencyjnych (wzorcowych)

    max_distance : float, default=100
        Maksymalna dopuszczalna odległość między centroidami w pikselach

    Zwraca:
    -------
    list
        Lista słowników zawierających prawidłowe grupy konturów:
        - 'contours': krotka konturów tworzących konstelację
        - 'centroids': lista centroidów konturów w scenie
        - 'max_distance': maksymalna odległość między centroidami

    Przykład:
    ---------
    >>> similar_contours = [[cnt1, cnt2], [cnt3, cnt4], [cnt5, cnt6], [cnt7, cnt8]]
    >>> ref_contours = [ref_cnt1, ref_cnt2, ref_cnt3, ref_cnt4]
    >>> valid_groups = find_valid_contour_groups(similar_contours, ref_contours, 150)
    >>> for group in valid_groups:
    ...     print(f"Znaleziono grupę z {len(group['contours'])} konturami")

    Uwagi:
    ------
    - Funkcja wymaga przynajmniej jednego konturu każdego typu
    - Zwraca pustą listę jeśli brak konturów danego typu
    - Walidacja geometryczna używa funkcji check_geometric_constellation
    - Grupy są sortowane według maksymalnej odległości między centroidami
    """
    valid_groups = []

    # Oblicz centroidy konturów referencyjnych
    ref_centroids = []
    for cnt in ref_cnts:
        centroid = tag_reconstruction.get_contour_centroid(cnt)
        if centroid is not None:
            ref_centroids.append(centroid)

    # Upewnij się, że mamy przynajmniej jeden kontur każdego typu
    valid_similar_cnts = []
    for i, cnts in enumerate(similar_cnts):
        if len(cnts) > 0:
            valid_similar_cnts.append(cnts)
        else:
            # Jeśli brak konturów danego typu, nie możemy utworzyć konstelacji
            return []

    # Sprawdź wszystkie kombinacje
    for combination in product(*valid_similar_cnts):
        # Oblicz centroidy dla tej kombinacji
        scene_centroids = []
        for cnt in combination:
            centroid = tag_reconstruction.get_contour_centroid(cnt)
            if centroid is not None:
                scene_centroids.append(centroid)

        # Sprawdź, czy wszystkie centroidy są blisko siebie
        if len(scene_centroids) < 2:
            continue

        # Sprawdź maksymalne odległości między centroidami
        max_dist = 0
        for i in range(len(scene_centroids)):
            for j in range(i + 1, len(scene_centroids)):
                dist = np.linalg.norm(
                    np.array(scene_centroids[i]) - np.array(scene_centroids[j])
                )
                max_dist = max(max_dist, dist)

        if max_dist > max_distance:
            continue

        # Sprawdź konstelację geometryczną
        if tag_reconstruction.check_geometric_constellation(
            ref_centroids, scene_centroids
        ):
            valid_groups.append({
                "contours": combination,
                "centroids": scene_centroids,
                "max_distance": max_dist,
            })

    # Sortuj według jakości (najmniejsze odległości najpierw)
    # valid_groups.sort(key=lambda x: x["max_distance"])

    return valid_groups
