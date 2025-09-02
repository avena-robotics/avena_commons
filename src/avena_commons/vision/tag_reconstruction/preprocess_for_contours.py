import cv2
import numpy as np

import avena_commons.vision.image_preprocess as preprocess


def preprocess_for_contours(image: np.ndarray) -> np.ndarray:
    """
    Przygotowuje obraz do detekcji konturów poprzez preprocessing wizyjny.

    Funkcja implementuje kompletny pipeline preprocessingu, który optymalizuje
    jakość obrazu dla algorytmów detekcji konturów. Proces obejmuje konwersję
    kolorów, poprawę kontrastu, binaryzację adaptacyjną i operacje morfologiczne.

    Zasada działania:
    ----------------
    1. **Konwersja kolorów**: Automatyczna konwersja RGB/BGR do skali szarości
    2. **Poprawa kontrastu**: Zastosowanie CLAHE dla lepszego kontrastu lokalnego
    3. **Binaryzacja adaptacyjna**: Inteligentne progowanie z uwzględnieniem lokalnego oświetlenia
    4. **Operacje morfologiczne**: Usunięcie szumu i poprawa jakości konturów

    Parametry:
    ----------
    image : np.ndarray
        Obraz wejściowy (może być kolorowy RGB/BGR lub w skali szarości)

    Zwraca:
    -------
    np.ndarray
        Obraz binarny gotowy do analizy konturów (białe obiekty na czarnym tle)

    Przykład:
    ---------
    >>> input_image = cv2.imread('image.jpg')
    >>> preprocessed = preprocess_for_contours(input_image)
    >>> contours, _ = cv2.findContours(preprocessed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    Uwagi:
    ------
    - CLAHE poprawia kontrast lokalny bez wprowadzania artefaktów
    - Binaryzacja adaptacyjna jest lepsza dla obrazów o nierównomiernym oświetleniu
    - Operacja otwarcia usuwa drobne szumy i poprawia jakość konturów
    - Parametry CLAHE i binaryzacji są zoptymalizowane dla tagów wizyjnych
    """
    if len(image.shape) > 2:
        gray = preprocess.to_gray(image)
    else:
        gray = image

    # Poprawa kontrastu
    enhanced = preprocess.clahe(gray, clip_limit=2.0, grid_size=8)

    # Adaptacyjna binaryzacja jest lepsza dla obrazów o nierównym oświetleniu
    binary = cv2.adaptiveThreshold(
        enhanced,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,  # Odwrócenie, aby obiekty były białe na czarnym tle
        blockSize=21,
        C=5,
    )

    # Usunięcie małych "kropek" szumu za pomocą operacji otwarcia
    kernel = np.ones((3, 3), np.uint8)
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    return opened
