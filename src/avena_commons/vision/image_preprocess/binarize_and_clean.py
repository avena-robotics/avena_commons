import cv2
import numpy as np


def binarize_and_clean(image: np.ndarray, config: dict) -> np.ndarray:
    """Przetwarza przycięty obraz poprzez serię operacji wizyjnych.

    Funkcja wykonuje kompleksowe przetwarzanie obrazu w następujących krokach:
    1. Korekcja gamma - dostosowuje jasność i kontrast obrazu
    2. Binarizacja adaptacyjna - konwertuje obraz do czarno-białego
    3. Operacje morfologiczne - oczyszcza i poprawia jakość obrazu binarnego

    Args:
        image: Obraz wejściowy w formacie OpenCV (numpy.ndarray)
        config: Słownik z konfiguracją zawierający:
            - gamma (float): Wartość gamma dla korekcji jasności (np. 1.2)
            - binarization (dict): Konfiguracja binarizacji:
                - block_size (int): Rozmiar bloku dla binarizacji adaptacyjnej (liczba nieparzysta)
                - C (int): Stała odejmowana od średniej (np. 2)
            - morph (dict): Konfiguracja operacji morfologicznych:
                - kernel_size (int): Rozmiar jądra morfologicznego (np. 3)
                - open_iter (int): Liczba iteracji operacji otwarcia
                - close_iter (int): Liczba iteracji operacji zamknięcia

    Returns:
        numpy.ndarray: Obraz binarny po przetworzeniu morfologicznym

    Example:
        >>> config = {
        ...     "gamma": 1.2,
        ...     "binarization": {"block_size": 11, "C": 2},
        ...     "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 1}
        ... }
        >>> processed_image = crop_image_process(input_image, config)
    """
    # 1. Korekcja gamma - dostosowuje jasność i kontrast
    image = np.power(image / 255.0, config["gamma"]) * 255.0
    image = image.astype(np.uint8)

    # 2. Binarizacja adaptacyjna - konwertuje do czarno-białego
    binary_image = cv2.adaptiveThreshold(
        image,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,  # lub cv2.ADAPTIVE_THRESH_MEAN_C
        cv2.THRESH_BINARY,
        config["binarization"]["block_size"],  # blockSize (liczba nieparzysta)
        config["binarization"]["C"],  # C (stała odejmowana od średniej)
    )

    # 3. Inwersja obrazu binarnego
    binary_image = cv2.bitwise_not(binary_image)

    # 4. Operacje morfologiczne - oczyszczanie obrazu
    kernel = np.ones(
        (config["morph"]["kernel_size"], config["morph"]["kernel_size"]), np.uint8
    )

    # Operacja otwarcia - usuwa małe obiekty i szum
    binary_image = cv2.morphologyEx(
        binary_image, cv2.MORPH_OPEN, kernel, iterations=config["morph"]["open_iter"]
    )

    # Operacja zamknięcia - wypełnia małe dziury
    binary_image = cv2.morphologyEx(
        binary_image, cv2.MORPH_CLOSE, kernel, iterations=config["morph"]["close_iter"]
    )

    # 5. Przywrócenie oryginalnych kolorów (ponowna inwersja)
    binary_image = cv2.bitwise_not(binary_image)

    return binary_image
