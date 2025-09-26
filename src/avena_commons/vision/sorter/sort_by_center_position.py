from typing import Any, Dict, List


def sort_qr_by_center_position(
    expected_count: int,
    detections: List[Any],  # Lista detekcji AprilTag
) -> Dict[int, Any]:
    """Organizuje kody QR w siatce 2x2 na podstawie dynamicznych punktów podziału.

    Funkcja organizuje detekcje kodów QR w siatce 2x2 używając:
    - Dynamicznej mediany pozycji Y dla podziału na górny/dolny rząd
    - Dynamicznej mediany pozycji X dla podziału na lewą/prawą stronę

    Mapowanie pozycji:
    - 1: Górny lewy (Y < middle_point_y, X < middle_point_x)
    - 2: Dolny lewy (Y >= middle_point_y, X < middle_point_x)
    - 3: Górny prawy (Y < middle_point_y, X >= middle_point_x)
    - 4: Dolny prawy (Y >= middle_point_y, X >= middle_point_x)

    Args:
        expected_count: Liczba spodziewanych kodów QR (1-4)
        detections: Lista detekcji AprilTag (musi mieć atrybuty .center)

    Returns:
        Dict[int, Any]: Słownik z kluczami 1-4 zawierający detekcje w pozycjach siatki.
            Brakujące pozycje mają wartość None.

    Raises:
        ValueError: Jeśli expected_count nie jest w zakresie 1-4

    Example:
        >>> detections = [detection1, detection2, detection3]
        >>> result = sort_qr_by_center_position(3, detections)
        >>> print(f"Górny lewy: {result[1]}")
        >>> print(f"Dolny lewy: {result[2]}")
    """
    if expected_count < 1 or expected_count > 4:
        raise ValueError("expected_count must be between 1 and 4")

    if not detections:
        return {1: None, 2: None, 3: None, 4: None}

    # Inicjalizuj wynik
    result = {1: None, 2: None, 3: None, 4: None}

    # Oblicz dynamiczne punkty podziału X i Y dla wszystkich tagów
    if len(detections) <= 1:
        # Dla pojedynczego tagu użyj centrum obrazu
        middle_point_x = 1280 // 2  # 640
        middle_point_y = 800 // 2  # 400 dla obrazu 800p
    else:
        # Oblicz medianę pozycji X wszystkich tagów
        x_positions = [det.center[0] for det in detections]
        x_positions.sort()
        middle_point_x = x_positions[len(x_positions) // 2]

        # Oblicz medianę pozycji Y wszystkich tagów
        y_positions = [det.center[1] for det in detections]
        y_positions.sort()
        middle_point_y = y_positions[len(y_positions) // 2]
    for i, detection in enumerate(detections):
        y = detection.center[1]
        x = detection.center[0]

        is_left = x < middle_point_x
        is_top = y < middle_point_y

        # Określ pozycję w siatce 2x2 na podstawie Y (góra/dół) i X (lewy/prawy)
        if is_top:
            # Górny rząd
            if is_left:
                position = 1
                result[1] = detection  # Górny lewy
            else:
                position = 3
                result[3] = detection  # Górny prawy
        else:
            # Dolny rząd
            if is_left:
                position = 2
                result[2] = detection  # Dolny lewy
            else:
                position = 4
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
