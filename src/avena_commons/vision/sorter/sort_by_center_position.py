from typing import Any, Dict, List


def sort_qr_by_center_position(
    expected_count: int,
    detections: List[Any],  # Lista detekcji AprilTag
    middle_point_y: int = 540,
) -> Dict[int, Any]:
    """Organizuje kody QR w siatce 2x2 na podstawie pozycji Y i kąta rotacji Z.

    Funkcja organizuje detekcje kodów QR w siatce 2x2 używając:
    - Pozycji Y względem middle_point_y (górny/dolny rząd)
    - Kąta rotacji Z dla określenia lewej/prawej strony

    Mapowanie pozycji:
    - 1: Górny lewy (Y < middle_point_y, rot_z < 0)
    - 2: Dolny lewy (Y >= middle_point_y, rot_z < 0)
    - 3: Górny prawy (Y < middle_point_y, rot_z >= 0)
    - 4: Dolny prawy (Y >= middle_point_y, rot_z >= 0)

    Args:
        expected_count: Liczba spodziewanych kodów QR (1-4)
        detections: Lista detekcji AprilTag (musi mieć atrybuty .center i .pose_R lub rot_z)
        middle_point_y: Punkt podziału Y dla górnego i dolnego rzędu (domyślnie 540)

    Returns:
        Dict[int, Any]: Słownik z kluczami 1-4 zawierający detekcje w pozycjach siatki.
            Brakujące pozycje mają wartość None.

    Raises:
        ValueError: Jeśli expected_count nie jest w zakresie 1-4

    Example:
        >>> detections = [detection1, detection2, detection3]
        >>> result = sort_qr_by_center_position(3, detections, middle_point_y=500)
        >>> print(f"Górny lewy: {result[1]}")
        >>> print(f"Dolny lewy: {result[2]}")
    """
    if expected_count < 1 or expected_count > 4:
        raise ValueError("expected_count must be between 1 and 4")

    if not detections:
        return {1: None, 2: None, 3: None, 4: None}

    # Inicjalizuj wynik
    result = {1: None, 2: None, 3: None, 4: None}

    for detection in detections:
        y = detection.center[1]

        # Pobierz kąt rotacji Z - sprawdź różne możliwe atrybuty
        rot_z = 0
        if hasattr(detection, "pose_R") and detection.pose_R is not None:
            # Jeśli mamy macierz rotacji, wyciągnij kąt Z
            try:
                from avena_commons.util.utils import rotation_matrix_to_euler_angles

                rot_z = rotation_matrix_to_euler_angles(detection.pose_R)[2]
            except (ImportError, AttributeError):
                # Fallback - użyj współrzędnej X jako przybliżenia kierunku
                rot_z = 1 if detection.center[0] > (1280 // 2) else -1
        elif hasattr(detection, "rot_z"):
            rot_z = detection.rot_z
        elif hasattr(detection, "rotation_z"):
            rot_z = detection.rotation_z
        else:
            # Fallback - użyj pozycji X jako przybliżenia kierunku
            # Jeśli X > połowa szerokości, zakładamy prawą stronę (rot_z >= 0)
            rot_z = 1 if detection.center[0] > (1280 // 2) else -1

        # Określ pozycję w siatce 2x2
        if y < middle_point_y:
            # Górny rząd
            if rot_z < 0:
                result[1] = detection  # Górny lewy
            else:
                result[3] = detection  # Górny prawy
        else:
            # Dolny rząd
            if rot_z < 0:
                result[2] = detection  # Dolny lewy
            else:
                result[4] = detection  # Dolny prawy

    return result


def merge_qr_detections(
    current_state: Dict[int, Any],
    new_detections: List[Any],
    expected_count: int = 4,
) -> Dict[int, Any]:
    """Łączy aktualny stan detekcji QR z nowymi detekcjami, wybierając bardziej pewne wyniki.

    Funkcja merguje nowe detekcje z aktualnym stanem, aktualizując pozycje kodów QR
    i wybierając detekcje o wyższym confidence (jeśli dostępne) lub zachowując
    istniejące detekcje jeśli są lepsze. Proces zapewnia stabilność detekcji
    między klatkami obrazu.

    Args:
        current_state: Aktualny stan detekcji {1: detection1, 2: detection2, ...}
        new_detections: Lista nowych detekcji AprilTag
        expected_count: Maksymalna liczba spodziewanych kodów QR (domyślnie 4)

    Returns:
        Dict[int, Any]: Zaktualizowany słownik stanu z połączonymi detekcjami

    Raises:
        ValueError: Jeśli expected_count nie jest w zakresie 1-4

    Example:
        >>> current = {1: old_detection, 2: None, 3: None, 4: None}
        >>> new_detections = [new_detection1, new_detection2]
        >>> merged = merge_qr_detections(current, new_detections, 4)
        >>> print(f"Zaktualizowane pozycje: {len([v for v in merged.values() if v is not None])}")
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
