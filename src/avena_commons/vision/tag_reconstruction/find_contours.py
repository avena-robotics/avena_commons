import cv2
import numpy as np


def find_contours(image: np.ndarray) -> list[np.ndarray]:
    """
    Wykrywa kontury w obrazie używając zaawansowanego algorytmu binaryzacji i analizy komponentów.

    Funkcja implementuje dwuetapowy proces wykrywania konturów: najpierw
    stosuje binaryzację Otsu dla optymalnego progowania, a następnie
    analizuje komponenty połączone, aby wyodrębnić wysokiej jakości kontury.

    Zasada działania:
    ----------------
    1. **Walidacja wejścia**: Sprawdzenie czy obraz jest jednokanałowy (skala szarości)
    2. **Binaryzacja Otsu**: Automatyczne progowanie z optymalnym progiem
    3. **Analiza komponentów**: Identyfikacja spójnych regionów połączonych
    4. **Ekstrakcja konturów**: Wykrycie konturów dla każdego komponentu
    5. **Filtrowanie tła**: Pominięcie komponentu tła (etykieta 0)

    Parametry:
    ----------
    image : np.ndarray
        Obraz wejściowy w skali szarości (jednokanałowy)

    Zwraca:
    -------
    list[np.ndarray]
        Lista wykrytych konturów w formacie OpenCV

    Przykład:
    ---------
    >>> gray_image = cv2.imread('image.jpg', cv2.IMREAD_GRAYSCALE)
    >>> contours = find_contours(gray_image)
    >>> print(f"Wykryto {len(contours)} konturów")

    Uwagi:
    ------
    - Obraz wejściowy musi być jednokanałowy (skala szarości)
    - Binaryzacja Otsu automatycznie wybiera optymalny próg
    - Używa analizy komponentów połączonych dla lepszej jakości
    - Pomija komponent tła (etykieta 0) automatycznie
    - Kontury są zwracane w standardowym formacie OpenCV
    """
    if image.ndim != 2:
        raise ValueError("Input must be a single‑channel (grayscale) image array.")

    # Binarise automatically with Otsu
    _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    num_labels, labels = cv2.connectedComponents(
        binary, connectivity=4
    )  # labels: 0 .. num_labels‑1
    contours: list[np.ndarray] = []
    for lbl in range(1, num_labels):  # skip background 0
        mask = np.uint8(labels == lbl) * 255  # binary mask for this component
        cnts, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        contours.extend(cnts)
    return contours
