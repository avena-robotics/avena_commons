import cv2
import numpy as np


def get_contour_centroid(contour):
    """
    Oblicza centroid (środek ciężkości) pojedynczego konturu.

    Funkcja implementuje bezpieczny algorytm obliczania centroidu
    używając momentów geometrycznych OpenCV. Zapewnia obsługę
    przypadków brzegowych i zwraca współrzędne w formacie [x, y].

    Zasada działania:
    ----------------
    1. **Obliczenie momentów**: Użycie OpenCV moments do wyznaczenia momentów geometrycznych
    2. **Walidacja obszaru**: Sprawdzenie czy kontur ma niezerowy obszar (M["m00"] != 0)
    3. **Obliczenie centroidu**: Podział momentów pierwszego rzędu przez moment zerowego rzędu
    4. **Konwersja typów**: Przekształcenie wyników na liczby całkowite

    Parametry:
    ----------
    contour : np.ndarray
        Kontur w formacie OpenCV (tablica punktów)

    Zwraca:
    -------
    np.ndarray or None
        Tablica [x, y] z współrzędnymi centroidu lub None jeśli kontur ma zerowy obszar

    Przykład:
    ---------
    >>> contour = np.array([[[100, 100]], [[200, 100]], [[150, 200]]])
    >>> centroid = get_contour_centroid(contour)
    >>> if centroid is not None:
    ...     print(f"Centroid: ({centroid[0]}, {centroid[1]})")

    Uwagi:
    ------
    - Używa momentów geometrycznych OpenCV dla dokładnych obliczeń
    - Zwraca None dla konturów o zerowym obszarze
    - Współrzędne są zwracane jako liczby całkowite
    - Funkcja jest bezpieczna i nie powoduje błędów dzielenia przez zero
    """
    M = cv2.moments(contour)
    if M["m00"] == 0:
        return None  # Avoid division by zero
    cX = int(M["m10"] / M["m00"])
    cY = int(M["m01"] / M["m00"])
    return np.array([cX, cY])
