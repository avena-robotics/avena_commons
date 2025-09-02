import numpy as np


def divide_image_into_roi(image: np.ndarray) -> list[dict]:
    """
    Wyodrębnia centralny region zainteresowania (ROI) z obrazu.

    Funkcja implementuje prostą strategię segmentacji polegającą na
    wycięciu centralnego obszaru obrazu z dodatkowym przesunięciem
    poziomym. Jest to alternatywa dla złożonego podziału na wiele ROI.

    Zasada działania:
    ----------------
    1. **Obliczenie wymiarów**: Określenie rozmiaru obrazu wejściowego
    2. **Centralne 50%**: Wycięcie środkowego obszaru (25%-75% w obu osiach)
    3. **Przesunięcie poziome**: Dodanie 300 pikseli do współrzędnej X
    4. **Struktura ROI**: Utworzenie słownika z metadanymi ROI
    5. **Lista wyjściowa**: Zwrócenie listy zawierającej jeden ROI

    Parametry:
    ----------
    image : np.ndarray
        Obraz wejściowy w formacie NumPy (RGB lub skala szarości)

    Zwraca:
    -------
    list[dict]
        Lista zawierająca jeden słownik ROI z polami:
        - 'name' (str): Nazwa ROI ("central")
        - 'roi_image' (np.ndarray): Wycięty centralny region
        - 'origin' (tuple): Współrzędne (x, y) lewego górnego rogu ROI
        - 'warped_image' (np.ndarray): Obraz po transformacji (początkowo None)
        - 'does_it_contain_tag' (bool): Flaga obecności tagu (początkowo False)
        - 'tag_mask' (np.ndarray): Maska tagu (początkowo None)
        - 'correct_rotation' (int): Rotacja korekcyjna (90 stopni)

    Przykład:
    ---------
    >>> rois = divide_image_into_roi(input_image)
    >>> central_roi = rois[0]
    >>> print(f"Central ROI: {central_roi['roi_image'].shape}")
    >>> print(f"Origin: {central_roi['origin']}")

    Uwagi:
    ------
    - ROI stanowi środkowe 50% obrazu w obu osiach
    - Dodatkowe przesunięcie o 300 pikseli w prawo
    - Rotacja korekcyjna ustawiona na 90 stopni
    """
    h, w = image.shape[:2]

    # Obliczanie współrzędnych dla centralnego 50%
    x_start = int(w * 0.25)
    x_end = int(w * 0.75)
    y_start = int(h * 0.25)
    y_end = int(h * 0.75)

    # Wycięcie i zwrócenie ROI
    roi_image = image[y_start:y_end, x_start + 300 : x_end]

    roi = {
        "name": "central",
        "roi_image": roi_image,
        "origin": (x_start + 300, y_start),
        "warped_image": None,
        "does_it_contain_tag": False,
        "tag_mask": None,
        "correct_rotation": 90,
    }

    rois = []
    rois.append(roi)

    return rois
