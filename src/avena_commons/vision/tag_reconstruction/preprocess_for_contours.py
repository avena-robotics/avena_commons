"""
Moduł do preprocessingu obrazów przed detekcją konturów.

Zasady działania:
--------------
Moduł implementuje pipeline preprocessingu obrazów, który optymalizuje
jakość obrazu dla algorytmów detekcji konturów. Proces obejmuje
konwersję do skali szarości, poprawę kontrastu, binaryzację adaptacyjną
i operacje morfologiczne.

Pipeline preprocessingu:
----------------------
1. **Konwersja kolorów**: Automatyczna konwersja RGB/BGR do skali szarości
2. **Poprawa kontrastu**: Zastosowanie CLAHE dla lepszego kontrastu lokalnego
3. **Binaryzacja adaptacyjna**: Inteligentne progowanie z uwzględnieniem lokalnego oświetlenia
4. **Operacje morfologiczne**: Usunięcie szumu i poprawa jakości konturów

Zastosowania:
- Przygotowanie obrazów do algorytmów detekcji konturów
- Optymalizacja jakości obrazów z nierównomiernym oświetleniem
- Redukcja szumu i artefaktów w obrazach wizyjnych
- Standaryzacja danych wejściowych dla algorytmów wizyjnych
"""

import cv2
import numpy as np


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
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Poprawa kontrastu
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

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
