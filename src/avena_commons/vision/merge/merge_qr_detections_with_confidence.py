from typing import Any, Dict, List


def get_confidence_score(detection: Any) -> float:
    """
    Pobiera wartość confidence z detekcji AprilTag.

    Próbuje różne możliwe nazwy atrybutów confidence.

    Args:
        detection: Obiekt detekcji AprilTag

    Returns:
        Wartość confidence jako float, 0.0 jeśli nie można określić
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
    """
    Łączy aktualny stan detekcji QR z nowymi detekcjami, używając funkcji confidence.

    Funkcja merguje nowe detekcje (już posortowane według pozycji) z aktualnym stanem,
    wybierając bardziej pewne wyniki na podstawie confidence.

    Args:
        current_state: Aktualny stan detekcji {1: detection1, 2: detection2, ...}
        new_detections: Słownik nowych detekcji AprilTag {1: detection1, 2: detection2, ...}
        expected_count: Maksymalna liczba spodziewanych QR kodów (domyślnie 4)

    Returns:
        Zaktualizowany słownik stanu z połączonymi detekcjami
    """
    if expected_count < 1 or expected_count > 4:
        raise ValueError("expected_count must be between 1 and 4")

    # Inicjalizuj wynik z aktualnym stanem
    merged_state = current_state.copy()

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
