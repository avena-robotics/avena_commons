"""
Moduł do rekonstrukcji i przetwarzania tagów wizyjnych w obrazach.

Zasady działania:
--------------
Moduł implementuje pipeline do rekonstrukcji tagów wizyjnych (QR, AR) z obrazów
z wykorzystaniem technik przetwarzania obrazu i analizy ROI (Region of Interest).

Główne etapy przetwarzania:
1. Preprocessing obrazu tagu referencyjnego (konwersja do skali szarości)
2. Tworzenie wzorców referencyjnych tagów
3. Podział obrazu na regiony zainteresowania (ROI)
4. Mapowanie tagów referencyjnych na ROI z uwzględnieniem perspektywy
5. Łączenie przetworzonych ROI w końcowy obraz

Strategie ROI:
- Podział na 4 kwadranty z nakładaniem się (overlap)
- Tryb centralny - pojedynczy ROI w centrum obrazu
- Konfigurowalne parametry slice'owania i nakładania

Zastosowania:
- Rekonstrukcja tagów QR/AR z obrazów zniekształconych perspektywą
- Poprawa jakości tagów wizyjnych dla lepszego dekodowania
- Przetwarzanie obrazów z kamer przemysłowych i robotycznych
"""

import numpy as np

import avena_commons.vision.preprocess as preprocess
import avena_commons.vision.tag_reconstruction as tag_reconstruction
from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import debug


def reconstruct_tags(
    image: np.ndarray, tag_image: np.ndarray, config: dict = None
) -> np.ndarray:
    """
    Główna funkcja do rekonstrukcji tagów wizyjnych w obrazie.

    Implementuje kompletny pipeline przetwarzania obrazu w celu poprawy
    jakości i czytelności tagów wizyjnych. Funkcja dzieli obraz na regiony
    zainteresowania, aplikuje transformacje perspektywiczne i łączy wyniki.

    Zasada działania:
    ----------------
    1. Preprocessing: Konwersja obrazu tagu do skali szarości
    2. Referencja: Tworzenie wzorców referencyjnych tagów
    3. Segmentacja: Podział obrazu na ROI (Region of Interest)
    4. Transformacja: Mapowanie tagów referencyjnych na ROI z perspektywą
    5. Integracja: Łączenie przetworzonych ROI w końcowy obraz

    Parametry:
    ----------
    image : np.ndarray
        Obraz wejściowy do przetworzenia (RGB lub skala szarości)

    tag_image : np.ndarray
        Obraz tagu referencyjnego do użycia jako wzorzec

    config : dict, optional
        Konfiguracja przetwarzania zawierająca:
        - 'roi_config': parametry podziału ROI
            - 'horizontal_slice': (start, end) - proporcje podziału poziomego
            - 'vertical_slice': (start, end) - proporcje podziału pionowego
            - 'overlap_fraction': frakcja nakładania się ROI
        - 'scene_corners': lista narożników sceny dla każdego ROI
        - 'central': bool - czy używać pojedynczego centralnego ROI

    Zwraca:
    -------
    np.ndarray
        Przetworzony obraz z zrekonstruowanymi tagami wizyjnymi

    Przykład:
    ---------
    >>> config = {
    ...     "roi_config": {
    ...         "horizontal_slice": (0.25, 0.75),
    ...         "vertical_slice": (0.0, 1.0),
    ...         "overlap_fraction": 0.15
    ...     },
    ...     "scene_corners": ["BL", "TR", "BL", "TR"]
    ... }
    >>> result = reconstruct_tags(input_image, reference_tag, config)

    Uwagi:
    ------
    - Funkcja używa Catchtime do pomiaru wydajności poszczególnych etapów
    - ROI są przetwarzane sekwencyjnie z mapowaniem perspektywicznym
    - Konfiguracja domyślna dzieli obraz na 4 kwadranty z 20% nakładaniem
    """
    if config is None:
        config = {
            "roi_config": {
                "horizontal_slice": (0.33, 0.66),
                "vertical_slice": (0.0, 1.0),  # Cała wysokość
                "overlap_fraction": 0.2,
            },
            "scene_corners": ["BL", "TR", "BL", "TR"],
        }

    with Catchtime() as ct1:
        if tag_image.ndim == 3:
            tag_image = preprocess.to_gray(tag_image)

    with Catchtime() as ct2:
        ref_tag_shapes = tag_reconstruction.create_reference_tag_shapes(tag_image)

    with Catchtime() as ct3:
        if not config.get("central", False):
            rois = tag_reconstruction.divide_image_into_rois(
                image, config["roi_config"]
            )
        else:
            rois = tag_reconstruction.divide_image_into_roi(image)

    with Catchtime() as ct4:
        # debug(f"rois: {len(rois)}")
        for i, roi in enumerate(rois):
            roi, _ = tag_reconstruction.wrap_tag_to_roi(
                ref_tag_shapes, roi, config["scene_corners"][i]
            )

    with Catchtime() as ct5:
        merged_image = tag_reconstruction.merge_rois_into_image(image, rois)

    # debug(
    #     f"reconstruct_tags: t1: {ct1.t * 1_000:.2f}ms t2: {ct2.t * 1_000:.2f}ms t3: {ct3.t * 1_000:.2f}ms t4: {ct4.t * 1_000:.2f}ms t5: {ct5.t * 1_000:.2f}ms"
    # )
    return merged_image
