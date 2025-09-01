from typing import Any, Dict, List


def sort_qr_by_center_position(
    expected_count: int,
    detections: List[Any],  # Lista detekcji AprilTag
) -> Dict[int, Any]:
    """
    Sortuje QR kody według pozycji center i zwraca słownik z kluczami 1,2,3,4.

    Args:
        expected_count: Liczba spodziewanych QR kodów (1-4)
        detections: Lista detekcji AprilTag (musi mieć atrybut .center)

    Returns:
        Słownik {1: detection1, 2: detection2, 3: detection3, 4: detection4}
        Brakujące pozycje mają wartość None
    """
    if expected_count < 1 or expected_count > 4:
        raise ValueError("expected_count must be between 1 and 4")

    if not detections:
        return {1: None, 2: None, 3: None, 4: None}

    # Wyciągnij centery
    qr_centers = [
        (detection.center[0], detection.center[1]) for detection in detections
    ]

    # Sortuj po y (wysokość), potem po x (lewo/prawo)
    # W OpenCV: y rośnie w dół, x rośnie w prawo
    sorted_indices = sorted(
        range(len(qr_centers)), key=lambda i: (qr_centers[i][1], qr_centers[i][0])
    )

    # Inicjalizuj wynik
    result = {1: None, 2: None, 3: None, 4: None}

    # Przypisz posortowane detekcje do kluczy 1,2,3,4
    for i, sorted_idx in enumerate(sorted_indices[:expected_count]):
        result[i + 1] = detections[sorted_idx]

    return result


def merge_qr_detections(
    current_state: Dict[int, Any],
    new_detections: List[Any],
    expected_count: int = 4,
) -> Dict[int, Any]:
    """
    Łączy aktualny stan detekcji QR z nowymi detekcjami, wybierając bardziej pewne wyniki.

    Funkcja merguje nowe detekcje z aktualnym stanem, aktualizując pozycje QR kodów
    i wybierając detekcje o wyższym confidence (jeśli dostępne) lub zachowując
    istniejące detekcje jeśli są lepsze.

    Args:
        current_state: Aktualny stan detekcji {1: detection1, 2: detection2, ...}
        new_detections: Lista nowych detekcji AprilTag
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

    if not new_detections:
        return merged_state

    # Sortuj nowe detekcje według pozycji
    sorted_new_detections = sort_qr_by_center_position(expected_count, new_detections)

    # Dla każdej pozycji (1-4) porównaj nową detekcję z aktualną
    for position in range(1, expected_count + 1):
        new_detection = sorted_new_detections.get(position)
        current_detection = merged_state.get(position)

        if new_detection is None:
            continue  # Brak nowej detekcji dla tej pozycji

        if current_detection is None:
            # Pozycja była pusta - dodaj nową detekcję
            merged_state[position] = new_detection
        else:
            # Porównaj confidence i wybierz lepszą detekcję
            # Zakładamy, że AprilTag ma atrybut confidence lub podobny
            # Jeśli nie ma, zachowujemy aktualną detekcję
            if hasattr(new_detection, "confidence") and hasattr(
                current_detection, "confidence"
            ):
                if new_detection.confidence > current_detection.confidence:
                    merged_state[position] = new_detection
                # Jeśli confidence jest równe lub mniejsze, zachowujemy aktualną
            elif hasattr(new_detection, "confidence"):
                # Nowa detekcja ma confidence, aktualna nie - wybieramy nową
                merged_state[position] = new_detection
            # W przeciwnym razie zachowujemy aktualną detekcję

    return merged_state


