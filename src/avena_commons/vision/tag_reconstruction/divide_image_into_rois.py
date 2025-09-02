from typing import Any, Dict

import numpy as np

# Domyślna konfiguracja ROI
DEFAULT_ROI_CONFIG = {
    "horizontal_slice": (0.33, 0.66),
    "vertical_slice": (0.0, 1.0),
    "overlap_fraction": 0.2,
}


def divide_image_into_rois(
    image: np.ndarray, config: Dict[str, Any] = None
) -> list[Dict[str, Any]]:  # MARK: divide image into rois
    """
    Dzieli obraz na 4 nakładające się na siebie regiony zainteresowania (ROI)
    zgodnie z podaną konfiguracją.

    Funkcja implementuje zaawansowany algorytm segmentacji obrazu, który
    optymalizuje wykrywanie tagów wizyjnych poprzez podział na strategiczne
    regiony z nakładaniem się i rotacją korekcyjną.

    Zasada działania:
    ----------------
    1. **Sekcja główna**: Wycięcie centralnej części obrazu według konfiguracji
    2. **Podział kwadrantowy**: Utworzenie 4 ROI (TL, TR, BL, BR) z nakładaniem
    3. **Optymalizacja wymiarów**: Dostosowanie rozmiaru ROI do strategii detekcji
    4. **Rotacja korekcyjna**: Przypisanie odpowiedniej rotacji dla każdego ROI
    5. **Metadane**: Dodanie informacji o pozycji, rotacji i statusie przetwarzania

    Parametry:
    ----------
    image : np.ndarray
        Obraz wejściowy w formacie NumPy (RGB lub skala szarości)

    config : Dict[str, Any], optional
        Słownik konfiguracyjny zawierający:
        - 'horizontal_slice' (tuple): Procentowy zakres szerokości (domyślnie 0.33-0.66)
        - 'vertical_slice' (tuple): Procentowy zakres wysokości (domyślnie 0.0-1.0)
        - 'overlap_fraction' (float): Procent nakładania się ROI (domyślnie 0.2)

    Zwraca:
    -------
    list[Dict[str, Any]]
        Lista słowników, gdzie każdy reprezentuje jeden ROI i zawiera:
        - 'name' (str): Nazwa ROI (TL, TR, BL, BR)
        - 'roi_image' (np.ndarray): Wycięty fragment obrazu
        - 'origin' (tuple): Współrzędne (x, y) lewego górnego rogu ROI
        - 'warped_image' (np.ndarray): Obraz po transformacji (początkowo None)
        - 'does_it_contain_tag' (bool): Flaga obecności tagu (początkowo False)
        - 'tag_mask' (np.ndarray): Maska tagu (początkowo None)
        - 'correct_rotation' (int): Rotacja korekcyjna w stopniach

    Przykład:
    ---------
    >>> config = {
    ...     "horizontal_slice": (0.25, 0.75),
    ...     "vertical_slice": (0.0, 1.0),
    ...     "overlap_fraction": 0.15
    ... }
    >>> rois = divide_image_into_rois(image, config)
    >>> for roi in rois:
    ...     print(f"ROI {roi['name']}: {roi['roi_image'].shape}")
    """
    if config is None:
        config = DEFAULT_ROI_CONFIG.copy()

    h, w = image.shape[:2]

    # Etap 1: Wycięcie głównej sekcji na podstawie konfiguracji
    x_start = int(w * config.get("horizontal_slice", (0.33, 0.66))[0])
    x_end = int(w * config.get("horizontal_slice", (0.33, 0.66))[1])
    y_start = int(h * config.get("vertical_slice", (0.0, 1.0))[0])
    y_end = int(h * config.get("vertical_slice", (0.0, 1.0))[1])

    main_section = image[y_start:y_end, x_start:x_end]
    main_section_origin = (x_start, y_start)

    # Etap 2: Wykrojenie 4 nakładających się ROI z głównej sekcji
    mh, mw = main_section.shape[:2]
    overlap = config.get("overlap_fraction", 0.2)

    # Obliczenie wymiarów ROI, aby nachodziły na siebie
    roi_h = int(mh * (0.5 + overlap / 2))
    roi_w = int(mw * (0.5 + overlap / 2))

    # Zgodnie z poleceniem, wysokość ROI jest zmniejszana do 2/3.
    # Dla TL i TR przycinany jest dół, a dla BL i BR - góra.
    shorter_roi_h = int(roi_h * (2 / 3))

    # Definicje współrzędnych (x1, y1, x2, y2) wewnątrz `main_section`
    roi_definitions = {
        "TL": (0, 0, roi_w, shorter_roi_h, 90),
        "TR": (mw - roi_w, 0, mw, shorter_roi_h, -90),
        "BL": (0, mh - shorter_roi_h, roi_w, mh, 90),
        "BR": (mw - roi_w, mh - shorter_roi_h, mw, mh, -90),
    }

    rois = []
    for name, (r_x1, r_y1, r_x2, r_y2, correct_rotation) in roi_definitions.items():
        # Wycięcie obrazu ROI
        roi_image = main_section[r_y1:r_y2, r_x1:r_x2]

        # Obliczenie globalnych koordynatów
        global_origin_x = main_section_origin[0] + r_x1
        global_origin_y = main_section_origin[1] + r_y1

        rois.append({
            "name": name,
            "roi_image": roi_image,
            "origin": (global_origin_x, global_origin_y),
            "warped_image": None,
            "does_it_contain_tag": False,
            "tag_mask": None,
            "correct_rotation": correct_rotation,
        })

    return rois
