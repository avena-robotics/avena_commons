import cv2
import numpy as np


def find_scenes_contours(image: np.ndarray) -> list[np.ndarray]:
    """
    Wykrywa kontury w obrazie sceny używając analizy komponentów połączonych.

    Funkcja implementuje algorytm wykrywania konturów, który identyfikuje
    spójne regiony w obrazie binarnym i ekstrahuje ich kontury. Jest to
    kluczowy element w pipeline'ie analizy obrazów sceny.

    Zasada działania:
    ----------------
    1. **Analiza komponentów**: Użycie cv2.connectedComponents do identyfikacji regionów
    2. **Filtrowanie tła**: Pominięcie komponentu tła (etykieta 0)
    3. **Tworzenie masek**: Generowanie masek binarnych dla każdego komponentu
    4. **Ekstrakcja konturów**: Wykrycie konturów z każdej maski
    5. **Agregacja wyników**: Połączenie wszystkich wykrytych konturów

    Parametry:
    ----------
    image : np.ndarray
        Obraz wejściowy (binarny lub w skali szarości)

    Zwraca:
    -------
    list[np.ndarray]
        Lista wykrytych konturów w formacie OpenCV

    Przykład:
    ---------
    >>> scene_image = preprocess_for_contours(input_image)
    >>> scene_contours = find_scenes_contours(scene_image)
    >>> print(f"Wykryto {len(scene_contours)} konturów w scenie")

    Uwagi:
    ------
    - Używa analizy komponentów połączonych z łącznością 4
    - Automatycznie pomija komponent tła (etykieta 0)
    - Kontury są zwracane w standardowym formacie OpenCV
    - Funkcja jest zoptymalizowana dla obrazów binarnych
    """
    num_labels, labels = cv2.connectedComponents(image, connectivity=4)
    scene_contours = []
    for lbl in range(1, num_labels):
        mask = np.uint8(labels == lbl) * 255
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        scene_contours.extend(cnts)
    return scene_contours
