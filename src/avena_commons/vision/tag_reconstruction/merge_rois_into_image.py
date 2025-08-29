"""
Moduł do łączenia przetworzonych ROI z powrotem na obraz bazowy.

Zasady działania:
--------------
Moduł implementuje algorytm inteligentnego łączenia przetworzonych regionów
zainteresowania (ROI) z powrotem na obraz bazowy. Proces wykorzystuje maski
tagów jako szablony do precyzyjnego wklejania zrekonstruowanych tagów.

Strategia łączenia:
------------------
1. **Walidacja ROI**: Sprawdzenie czy ROI zawiera przetworzony tag
2. **Filtrowanie rozmiaru**: Odrzucenie ROI z maską mniejszą niż 10000 pikseli
3. **Przycinanie do granic**: Dostosowanie ROI do wymiarów obrazu bazowego
4. **Kopiowanie z maską**: Precyzyjne wklejanie używając maski tagu
5. **Aktualizacja canvas**: Modyfikacja obrazu bazowego w miejscu

Zastosowania:
- Integracja przetworzonych tagów wizyjnych z obrazem oryginalnym
- Zachowanie jakości obrazu w obszarach bez tagów
- Precyzyjne mapowanie zrekonstruowanych elementów
- Finalizacja procesu rekonstrukcji tagów
"""

from typing import Dict, List

import cv2
import numpy as np


def merge_rois_into_image(base: np.ndarray, rois: List[Dict]) -> np.ndarray:
    """
    Łączy przetworzone ROI z powrotem na obraz bazowy używając masek tagów jako szablonów.

    Funkcja implementuje inteligentny algorytm łączenia, który precyzyjnie
    wkleja zrekonstruowane tagi wizyjne na obraz bazowy, zachowując jakość
    oryginalnego obrazu w obszarach bez tagów.

    Zasada działania:
    ----------------
    1. **Walidacja ROI**: Sprawdzenie czy ROI zawiera przetworzony tag
    2. **Filtrowanie rozmiaru**: Odrzucenie ROI z maską mniejszą niż 10000 pikseli
    3. **Przycinanie do granic**: Dostosowanie ROI do wymiarów obrazu bazowego
    4. **Kopiowanie z maską**: Precyzyjne wklejanie używając maski tagu
    5. **Aktualizacja canvas**: Modyfikacja obrazu bazowego w miejscu

    Parametry:
    ----------
    base : np.ndarray
        Obraz bazowy, na który będą wklejane przetworzone ROI

    rois : List[Dict]
        Lista słowników ROI, gdzie każdy musi zawierać:
        - 'origin' (tuple): współrzędne (x, y) lewego górnego rogu na obrazie bazowym
        - 'warped_image' (np.ndarray): przetworzony obraz ROI (H_r×W_r×3, uint8 BGR/RGB)
        - 'tag_mask' (np.ndarray): maska tagu (H_r×W_r, uint8 0 lub 255, pojedynczy kanał)
        - 'does_it_contain_tag' (bool): flaga czy ROI zawiera przetworzony tag

    Zwraca:
    -------
    np.ndarray
        Obraz bazowy z wklejonymi przetworzonymi ROI

    Przykład:
    ---------
    >>> base_image = np.zeros((1000, 1000, 3), dtype=np.uint8)
    >>> roi_list = [
    ...     {
    ...         'origin': (100, 100),
    ...         'warped_image': processed_roi,
    ...         'tag_mask': tag_mask,
    ...         'does_it_contain_tag': True
    ...     }
    ... ]
    >>> result = merge_rois_into_image(base_image, roi_list)

    Uwagi:
    ------
    - ROI z maską mniejszą niż 10000 pikseli są automatycznie odrzucane
    - ROI leżące całkowicie poza granicami obrazu są pomijane
    - Kopiowanie odbywa się tylko w obszarach gdzie maska != 0
    - Obraz bazowy jest modyfikowany w miejscu (in-place)
    """
    canvas = base.copy()

    for roi in rois:
        if not roi.get("does_it_contain_tag", False):
            continue

        x0, y0 = roi["origin"]
        patch = roi["warped_image"]
        roi_mask = roi.get("tag_mask")
        if roi_mask is None:
            continue

        # MARK: ROI MASK BBOX SIZE CHECK
        roi_mask_bbox = cv2.boundingRect(roi_mask)
        roi_mask_bbox_size = roi_mask_bbox[2] * roi_mask_bbox[3]

        if roi_mask_bbox_size < 10000:
            continue

        ph, pw = patch.shape[:2]

        # ---------- clip ROI to canvas bounds ----------------------------
        x1, y1 = max(0, x0), max(0, y0)
        x2, y2 = min(canvas.shape[1], x0 + pw), min(canvas.shape[0], y0 + ph)
        if x2 <= x1 or y2 <= y1:
            continue  # ROI lies completely outside

        patch_sub = patch[y1 - y0 : y2 - y0, x1 - x0 : x2 - x0]
        mask_sub = roi_mask[y1 - y0 : y2 - y0, x1 - x0 : x2 - x0]

        # ---------- copy where mask != 0 ---------------------------------
        dst = canvas[y1:y2, x1:x2]
        cv2.copyTo(patch_sub, mask_sub, dst)  # in-place on canvas slice

    return canvas
