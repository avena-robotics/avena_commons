from typing import Any, Dict, List


def _try_static_division(detections: List[Any]) -> Dict[int, List[Any]]:
    """Próbuje przypisać detekcje do pozycji używając statycznych punktów podziału.

    Args:
        detections: Lista detekcji AprilTag

    Returns:
        Dict[int, List[Any]]: Słownik z listami detekcji dla każdej pozycji
    """
    # Stałe punkty podziału - środek obrazu
    middle_point_x = 640  # 1280 / 2
    middle_point_y = 400  # 800 / 2

    result = {1: [], 2: [], 3: [], 4: []}

    for i, detection in enumerate(detections):
        y = detection.center[1]
        x = detection.center[0]

        is_left = x < middle_point_x
        is_top = y < middle_point_y

        # Określ pozycję w siatce 2x2
        if is_top and is_left:
            position = 1  # Górny lewy
        elif not is_top and is_left:
            position = 2  # Dolny lewy
        elif is_top and not is_left:
            position = 3  # Górny prawy
        else:
            position = 4  # Dolny prawy

        result[position].append(detection)

    return result


def _has_conflicts(position_lists: Dict[int, List[Any]]) -> bool:
    """Sprawdza czy są konflikty w przypisaniu pozycji (więcej niż jedna detekcja na pozycję).

    Args:
        position_lists: Słownik z listami detekcji dla każdej pozycji

    Returns:
        bool: True jeśli są konflikty, False w przeciwnym razie
    """
    conflicts = []
    for pos, detections_list in position_lists.items():
        if len(detections_list) > 1:
            conflicts.append(f"pozycja {pos}: {len(detections_list)} detekcji")

    has_conflicts = len(conflicts) > 0

    return has_conflicts


def _convert_to_single_detection_dict(
    position_lists: Dict[int, List[Any]],
) -> Dict[int, Any]:
    """Konwertuje słownik z listami detekcji na słownik z pojedynczymi detekcjami.

    Args:
        position_lists: Słownik z listami detekcji

    Returns:
        Dict[int, Any]: Słownik z pojedynczymi detekcjami lub None
    """
    result = {1: None, 2: None, 3: None, 4: None}

    for pos, detections_list in position_lists.items():
        if len(detections_list) == 1:
            result[pos] = detections_list[0]
        elif len(detections_list) > 1:
            # W przypadku konfliktu, weź pierwszą detekcję (nie powinno się zdarzyć przy prawidłowym użyciu)
            result[pos] = detections_list[0]

    return result


def _sort_with_dynamic_division(detections: List[Any]) -> Dict[int, Any]:
    """Sortuje detekcje używając dynamicznych punktów podziału (oryginalna logika).

    Args:
        detections: Lista detekcji AprilTag

    Returns:
        Dict[int, Any]: Słownik z detekcjami przypisanymi do pozycji
    """
    result = {1: None, 2: None, 3: None, 4: None}

    # Oblicz dynamiczne punkty podziału X i Y dla wszystkich tagów
    if len(detections) <= 1:
        # Dla pojedynczego tagu użyj centrum obrazu
        middle_point_x = 640
        middle_point_y = 400
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
            if is_left:
                position = 1
                result[1] = detection  # Górny lewy
            else:
                position = 3
                result[3] = detection  # Górny prawy
        else:
            if is_left:
                position = 2
                result[2] = detection  # Dolny lewy
            else:
                position = 4
                result[4] = detection  # Dolny prawy

    return result


def sort_qr_by_center_position(
    expected_count: int,
    detections: List[Any],  # Lista detekcji AprilTag
) -> Dict[int, Any]:
    """Organizuje kody QR w siatce 2x2 używając hybrydowej strategii sortowania.

    Funkcja używa hybrydowego podejścia:
    1. Najpierw próbuje statycznego podziału (środek obrazu jako punkt podziału)
    2. Jeśli wystąpią konflikty (więcej detekcji w jednej pozycji), używa dynamicznego podziału
    3. Dynamiczny podział używa mediany pozycji wszystkich detekcji jako punktów podziału

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

    # Krok 1: Próba ze statycznym podziałem
    static_position_lists = _try_static_division(detections)

    # Krok 2: Sprawdzenie konfliktów
    if _has_conflicts(static_position_lists):
        # Krok 3: Fallback do dynamicznego dzielenia
        result = _sort_with_dynamic_division(detections)
    else:
        # Brak konfliktów - użyj wyniku statycznego
        result = _convert_to_single_detection_dict(static_position_lists)

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
