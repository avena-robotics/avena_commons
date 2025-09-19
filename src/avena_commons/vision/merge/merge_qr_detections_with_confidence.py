import copy
from typing import Any, Dict, List


def get_confidence_score(detection: Any) -> float:
    """Pobiera wartość confidence z detekcji AprilTag.

    Funkcja próbuje różne możliwe nazwy atrybutów confidence w obiekcie
    detekcji AprilTag, aby zapewnić kompatybilność z różnymi wersjami
    biblioteki. Sprawdza atrybuty: confidence, confidence_score, score, quality.

    Args:
        detection: Obiekt detekcji AprilTag z potencjalnym atrybutem confidence

    Returns:
        float: Wartość confidence jako liczba zmiennoprzecinkowa.
            Zwraca 0.0 jeśli nie można określić confidence.

    Example:
        >>> detection = april_tag_detection  # Obiekt z atrybutem confidence
        >>> score = get_confidence_score(detection)
        >>> print(f"Confidence: {score}")
    """
    confidence_attrs = ["confidence", "confidence_score", "score", "quality"]

    for attr in confidence_attrs:
        if hasattr(detection, attr):
            value = getattr(detection, attr)
            if isinstance(value, (int, float)):
                return float(value)

    # Jeśli nie ma atrybutu confidence, zwróć domyślną wartość
    return 0.0


def merge_qr_detections_with_confidence(
    current_state: Dict[int, Any],
    new_detections: Dict[int, Any],
    expected_count: int = 4,
) -> Dict[int, Any]:
    """Łączy aktualny stan detekcji QR z nowymi detekcjami, używając confidence.

    Funkcja merguje nowe detekcje (już posortowane według pozycji) z aktualnym stanem,
    wybierając bardziej pewne wyniki na podstawie wartości confidence. Proces
    zapewnia stabilność detekcji między klatkami obrazu, preferując detekcje
    o wyższym poziomie pewności.

    Args:
        current_state: Aktualny stan detekcji {1: detection1, 2: detection2, ...}
        new_detections: Słownik nowych detekcji AprilTag {1: detection1, 2: detection2, ...}
        expected_count: Maksymalna liczba spodziewanych kodów QR (domyślnie 4)

    Returns:
        Dict[int, Any]: Zaktualizowany słownik stanu z połączonymi detekcjami

    Raises:
        ValueError: Jeśli expected_count nie jest w zakresie 1-4

    Example:
        >>> current = {1: old_detection, 2: None, 3: None, 4: None}
        >>> new_detections = {1: new_detection1, 2: new_detection2}
        >>> merged = merge_qr_detections_with_confidence(current, new_detections, 4)
        >>> print(f"Zaktualizowane pozycje: {len([v for v in merged.values() if v is not None])}")
    """
    if expected_count < 1 or expected_count > 4:
        raise ValueError("expected_count must be between 1 and 4")

    # Inicjalizuj wynik z aktualnym stanem
    merged_state = copy.deepcopy(current_state)

    # Upewnij się, że wszystkie pozycje są zainicjalizowane
    for i in range(1, expected_count + 1):
        if i not in merged_state:
            merged_state[i] = None

    # Dla każdej pozycji (1-4) porównaj nową detekcję z aktualną
    for position in range(1, expected_count + 1):
        new_detection = new_detections.get(position)

        if new_detection is None:
            continue  # Brak nowej detekcji dla tej pozycji

        current_detection = merged_state.get(position)

        if current_detection is None:
            # Pozycja była pusta - dodaj nową detekcję
            merged_state[position] = new_detection
        else:
            # Porównaj confidence i wybierz lepszą detekcję
            new_confidence = get_confidence_score(new_detection)
            current_confidence = get_confidence_score(current_detection)

            if new_confidence > current_confidence:
                merged_state[position] = new_detection
            # Jeśli confidence jest równe lub mniejsze, zachowujemy aktualną

    return merged_state
