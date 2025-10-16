import os
from datetime import datetime

import cv2
import numpy as np

import avena_commons.vision.camera as camera
import avena_commons.vision.image_preprocess as preprocess
import avena_commons.vision.validation as validation
from avena_commons.util.catchtime import Catchtime
from avena_commons.vision.vision import (
    create_box_color_mask,
    create_box_depth_mask,
    find_contours,
    fix_depth,
    get_hit_contours,
    merge_masks,
    prepare_box_output,
    prepare_image_output,
    preprocess_mask,
    rectangle_from_contours,
    remove_contours_outside_box,
    remove_edge_contours,
)


def box_detector(*, frame, camera_config, config):
    """Detektor pudełek wykorzystujący kombinację masek kolorowej i głębi.

    Analizuje ramki kolorowe i głębi aby wykryć prostokątne pudełka na podstawie
    konfiguracji HSV i parametrów głębi. Zwraca pozycję, narożniki, kąt i głębię
    wykrytego pudełka wraz z danymi debugowania.

    Args:
        frame (dict): Słownik zawierający ramki 'color' i 'depth'.
        camera_config (dict): Konfiguracja kamery z parametrami i współczynnikami dystorsji.
        config (dict): Konfiguracja detektora zawierająca ustawienia HSV, głębi, filtrowania
                    konturów, walidacji i innych parametrów.

    Returns:
        tuple: Krotka zawierająca:
            - center (tuple | None): Współrzędne środka pudełka (x, y).
            - sorted_corners (list | None): Lista 4 narożników pudełka [(x1,y1), ...].
            - angle (float | None): Kąt obrotu pudełka w stopniach.
            - z (float | None): Głębość środka pudełka w mm.
            - detect_image (numpy.ndarray): Obraz wizualizacyjny z wykrytymi elementami.
            - debug_data (dict): Słownik z danymi debugowania z każdego etapu przetwarzania.

    Raises:
        Exception: Może wystąpić przy błędach przetwarzania obrazu lub konfiguracji.

    Przykład:
        >>> frame = {"color": color_img, "depth": depth_img}
        >>> camera_cfg = {"camera_params": {...}, "distortion_coefficients": [...]}
        >>> config = {"hsv": {...}, "depth": {...}, "center_point": (640, 480)}
        >>> center, corners, angle, z, viz, debug = box_detector(
        ...     frame=frame, camera_config=camera_cfg, config=config)
    """
    color_image = frame["color"]
    depth_image = frame["depth"]

    # Zapisz ramki do debugowania
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    debug_dir = "temp/debug_frames"
    os.makedirs(debug_dir, exist_ok=True)

    # # Zapisz obraz kolorowy
    # color_filename = f"{debug_dir}/color_frame_{timestamp}.jpg"
    # cv2.imwrite(color_filename, color_image)

    # Zapisz obraz głębi (skonwertowany do 8-bit dla lepszej wizualizacji)
    # depth_normalized = cv2.normalize(
    #     depth_image, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U
    # )
    # depth_filename = f"{debug_dir}/depth_frame_{timestamp}.jpg"
    # cv2.imwrite(depth_filename, depth_normalized)

    # Zapisz także raw depth jako numpy array
    # depth_raw_filename = f"{debug_dir}/depth_raw_{timestamp}.npy"
    # np.save(depth_raw_filename, depth_image)

    # print(f"DEBUG: Zapisano ramki do {debug_dir}/")
    # print(
    #     f"DEBUG: Kolor: {color_image.shape}, min={color_image.min()}, max={color_image.max()}"
    # )
    # print(
    #     f"DEBUG: Głębia: {depth_image.shape}, min={depth_image.min()}, max={depth_image.max()}"
    # )
    # print(f"DEBUG: Config HSV: {config.get('hsv', {})}")
    # print(f"DEBUG: Config depth: {config.get('depth', {})}")
    # print(f"DEBUG: Center point: {config.get('center_point', None)}")

    debug_data = {}
    with Catchtime() as t1:
        camera_matrix = camera.create_camera_matrix(camera_config["camera_params"])
        camera_distortion = camera.create_camera_distortion(
            camera_config["distortion_coefficients"]
        )

    with Catchtime() as t2:
        if config.get("fix_depth_on", False):
            depth_image = fix_depth(depth_image, config["fix_depth_config"])
            debug_data["box_depth_image_fixed"] = depth_image

    # Zapisz depth fix jako numpy array
    # depth_fix_filename = f"{debug_dir}/depth_fix_{timestamp}.npy"
    # np.save(depth_fix_filename, depth_image)

    # create box depth mask
    with Catchtime() as t3:
        depth_mask = create_box_depth_mask(
            depth_image, {**config["depth"], "center_point": config["center_point"]}
        )
        debug_data["box_depth_mask"] = depth_mask

    # create box color mask
    with Catchtime() as t4:
        color_mask = create_box_color_mask(
            color_image, {**config["hsv"], "center_point": config["center_point"]}
        )
        debug_data["box_color_mask"] = color_mask

    # combine masks
    with Catchtime() as t5:
        mask_combined = merge_masks([depth_mask, color_mask])
        debug_data["box_mask_combined"] = mask_combined

    # Zapisz maski do debugowania
    # depth_mask_filename = f"{debug_dir}/depth_mask_{timestamp}.jpg"
    # cv2.imwrite(depth_mask_filename, depth_mask)

    # color_mask_filename = f"{debug_dir}/color_mask_{timestamp}.jpg"
    # cv2.imwrite(color_mask_filename, color_mask)

    # combined_mask_filename = f"{debug_dir}/combined_mask_{timestamp}.jpg"
    # cv2.imwrite(combined_mask_filename, mask_combined)

    # print(
    #     f"DEBUG: Maski zapisane - depth: {np.max(depth_mask)}, color: {np.max(color_mask)}, combined: {np.max(mask_combined)}"
    # )

    if np.max(mask_combined) <= 0:
        detect_image = mask_combined
        print("DEBUG: Brak pikseli w combined mask - zwracam None")
        return None, None, None, None, detect_image, debug_data

    with Catchtime() as t6:
        mask_preprocessed = preprocess_mask(mask_combined, config["preprocess"])
        debug_data["box_mask_preprocessed"] = mask_preprocessed

    with Catchtime() as t7:
        mask_undistorted = preprocess.undistort(
            mask_preprocessed, camera_matrix, camera_distortion
        )
        debug_data["box_mask_undistorted"] = mask_undistorted

    with Catchtime() as t8:
        contours = find_contours(mask_undistorted)
        debug_data["box_contours"] = contours

    with Catchtime() as t9:
        box_contours = remove_contours_outside_box(
            contours, {**config["remove_cnts"], "center_point": config["center_point"]}
        )
        debug_data["box_box_contours"] = box_contours

    with Catchtime() as t10:
        filtered_contours = remove_edge_contours(
            contours,  # FIXME contours czy to nie powinno być box_contours?
            mask_undistorted.shape,
            config.get("edge_removal", {"edge_margin": 50}),
        )
        debug_data["box_filtered_contours"] = filtered_contours

    with Catchtime() as t11:
        hit_contours, labeled_mask = get_hit_contours(
            mask_undistorted,
            filtered_contours,
            {**config["hit_contours"], "center_point": config["center_point"]},
        )
        debug_data["box_hit_contours"] = hit_contours
        debug_data["box_labeled_mask"] = labeled_mask

    if len(hit_contours) == 0:
        detect_image = mask_combined
        print("DEBUG: Brak konturów po filtracji - zwracam None")
        return None, None, None, None, detect_image, debug_data

    with Catchtime() as t12:
        rect, box = rectangle_from_contours(hit_contours)
        debug_data["box_rect"] = rect
        debug_data["box_box"] = box

    with Catchtime() as t13:
        valid = validation.validate_rectangle(
            rect,
            box,
            color_image,
            {**config["rect_validation"], "center_point": config["center_point"]},
        )
        debug_data["box_valid"] = valid

    with Catchtime() as t14:  # debug
        detect_image = prepare_image_output(color_image, box_contours, rect, box)
        debug_data["box_detect_image"] = detect_image

    if not valid:
        print("DEBUG: Prosta nie przeszła walidacji - zwracam None")
        # Nawet jeśli walidacja się nie powiodła, stwórz wizualizację tego co zostało wykryte
        # aby zobaczyć dlaczego nie przeszło walidacji
        if rect is not None and box is not None:
            # Oblicz centrum i corners z prostokąta dla wizualizacji
            temp_center, temp_corners, temp_angle, _ = prepare_box_output(
                rect,
                box,
                depth_image,
                {**config["depth"], "center_point": config["center_point"]},
            )
            failed_validation_viz = create_detection_visualization(
                color_image,
                temp_center,
                temp_corners,
                temp_angle,
                f"{timestamp}_FAILED_VALIDATION",
                debug_dir,
            )
            print(
                f"DEBUG: Wizualizacja nieudanej walidacji - Center: {temp_center}, Corners: {temp_corners}"
            )
        return None, None, None, None, detect_image, debug_data

    with Catchtime() as t15:
        center, sorted_corners, angle, z = prepare_box_output(  # wynik glowny
            rect,
            box,
            depth_image,
            {**config["depth"], "center_point": config["center_point"]},
        )
        debug_data["box_center"] = center
        debug_data["box_sorted_corners"] = sorted_corners
        debug_data["box_angle"] = angle
        debug_data["box_z"] = z

    # Stwórz wizualizację wykrytego pudła
    detection_visualization = create_detection_visualization(
        color_image, center, sorted_corners, angle, timestamp, debug_dir
    )

    print(
        f"t1: {t1.t * 1_000:.1f}ms t2: {t2.t * 1_000:.1f}ms t3: {t3.t * 1_000:.1f}ms t4: {t4.t * 1_000:.1f}ms t5: {t5.t * 1_000:.1f}ms t6: {t6.t * 1_000:.1f}ms t7: {t7.t * 1_000:.1f}ms t8: {t8.t * 1_000:.1f}ms t9: {t9.t * 1_000:.1f}ms t10: {t10.t * 1_000:.1f}ms t11: {t11.t * 1_000:.1f}ms t12: {t12.t * 1_000:.1f}ms t13: {t13.t * 1_000:.1f}ms t14: {t14.t * 1_000:.1f}ms t15: {t15.t * 1_000:.1f}ms"
    )
    return center, sorted_corners, angle, z, detect_image, debug_data


def create_detection_visualization(
    color_image, center, corners, angle, timestamp, debug_dir
):
    """
    Tworzy wizualizację wykrytego pudła na obrazie kolorowym.

    Rysuje centrum, corners i łączy je liniami na kopii obrazu kolorowego.
    Dodaje długości linii między sąsiednimi corners oraz między centrum a każdym corner.

    Args:
        color_image: Obraz kolorowy z kamery
        center: Punkt środka wykrytego pudła (x, y)
        corners: Lista 4 punktów narożnych pudła [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
        angle: Kąt obrotu pudła w stopniach
        timestamp: Znacznik czasu dla nazwy pliku
        debug_dir: Katalog do zapisu plików debug

    Returns:
        numpy.ndarray: Obraz z naniesioną wizualizacją zawierającą:
            - Centrum (czerwone koło)
            - Corners z numerami (zielone koła)
            - Linie łączące corners (niebieskie linie z żółtymi długościami)
            - Linie od centrum do corners (niebieskie linie z pomarańczowymi długościami)
            - Informacje tekstowe o centrum, kącie i liczbie corners
    """
    # Skopiuj obraz kolorowy aby nie modyfikować oryginału
    vis_image = color_image.copy()

    if center is None or corners is None:
        print("DEBUG: Brak danych do wizualizacji (center lub corners to None)")
        return vis_image

    # Konwertuj center do int (jeśli to float)
    center_int = (int(center[0]), int(center[1]))

    # Konwertuj corners do int
    corners_int = [(int(corner[0]), int(corner[1])) for corner in corners]

    print(
        f"DEBUG: Wizualizacja - Center: {center_int}, Corners: {corners_int}, Angle: {angle}"
    )

    # Kolory dla wizualizacji (BGR format dla OpenCV)
    center_color = (0, 0, 255)  # Czerwony dla centrum
    corner_color = (0, 255, 0)  # Zielony dla corners
    line_color = (255, 0, 0)  # Niebieski dla linii
    text_color = (255, 255, 255)  # Biały dla tekstu

    # Narysuj centrum jako wypełnione koło
    cv2.circle(vis_image, center_int, 8, center_color, -1)
    cv2.circle(vis_image, center_int, 10, center_color, 2)  # Obwódka

    # Narysuj każdy corner jako wypełnione koło z numerem
    for i, corner in enumerate(corners_int):
        # Koło dla corner
        cv2.circle(vis_image, corner, 6, corner_color, -1)
        cv2.circle(vis_image, corner, 8, corner_color, 2)  # Obwódka

        # Numer corner
        cv2.putText(
            vis_image,
            str(i),
            (corner[0] + 12, corner[1] + 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            text_color,
            2,
        )

    # Połącz corners liniami aby stworzyć prostokąt i dodaj długości linii
    for i in range(len(corners_int)):
        start_point = corners_int[i]
        end_point = corners_int[
            (i + 1) % len(corners_int)
        ]  # Następny punkt (z wraparound)
        cv2.line(vis_image, start_point, end_point, line_color, 2)

        # Oblicz długość linii w pikselach
        line_length = np.sqrt(
            (end_point[0] - start_point[0]) ** 2 + (end_point[1] - start_point[1]) ** 2
        )

        # Oblicz punkt środkowy linii dla umieszczenia tekstu
        mid_point = (
            int((start_point[0] + end_point[0]) / 2),
            int((start_point[1] + end_point[1]) / 2),
        )

        # Przygotuj tekst z długością linii
        length_text = f"{line_length:.1f}px"

        # Oblicz rozmiar tekstu dla lepszego pozycjonowania
        text_size = cv2.getTextSize(length_text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0]

        # Dodaj tło pod tekst dla lepszej czytelności
        text_bg_pt1 = (
            mid_point[0] - text_size[0] // 2 - 3,
            mid_point[1] - text_size[1] - 3,
        )
        text_bg_pt2 = (mid_point[0] + text_size[0] // 2 + 3, mid_point[1] + 3)
        cv2.rectangle(vis_image, text_bg_pt1, text_bg_pt2, (0, 0, 0), -1)

        # Dodaj tekst z długością linii
        cv2.putText(
            vis_image,
            length_text,
            (mid_point[0] - text_size[0] // 2, mid_point[1]),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 0),  # Żółty kolor dla długości linii
            1,
        )

    # Połącz centrum z każdym corner i dodaj długości linii
    for i, corner in enumerate(corners_int):
        cv2.line(vis_image, center_int, corner, line_color, 1)

        # Oblicz długość linii od centrum do corner
        diagonal_length = np.sqrt(
            (corner[0] - center_int[0]) ** 2 + (corner[1] - center_int[1]) ** 2
        )

        # Oblicz punkt dla umieszczenia tekstu (1/3 drogi od centrum do corner)
        text_point = (
            int(center_int[0] + (corner[0] - center_int[0]) * 0.33),
            int(center_int[1] + (corner[1] - center_int[1]) * 0.33),
        )

        # Przygotuj tekst z długością przekątnej
        diagonal_text = f"{diagonal_length:.1f}"

        # Oblicz rozmiar tekstu
        text_size = cv2.getTextSize(diagonal_text, cv2.FONT_HERSHEY_SIMPLEX, 0.3, 1)[0]

        # Dodaj tło pod tekst
        text_bg_pt1 = (
            text_point[0] - text_size[0] // 2 - 2,
            text_point[1] - text_size[1] - 2,
        )
        text_bg_pt2 = (text_point[0] + text_size[0] // 2 + 2, text_point[1] + 2)
        cv2.rectangle(vis_image, text_bg_pt1, text_bg_pt2, (50, 50, 50), -1)

        # Dodaj tekst z długością przekątnej
        cv2.putText(
            vis_image,
            diagonal_text,
            (text_point[0] - text_size[0] // 2, text_point[1]),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.3,
            (255, 165, 0),  # Pomarańczowy kolor dla przekątnych
            1,
        )

    # Dodaj informacje tekstowe
    info_text = [
        f"Center: ({center[0]:.1f}, {center[1]:.1f})",
        f"Angle: {angle:.1f}°",
        f"Corners: {len(corners)}",
    ]

    # Narysuj tekst z informacjami
    y_offset = 30
    for i, text in enumerate(info_text):
        y_pos = y_offset + (i * 25)
        # Tło dla lepszej czytelności
        text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
        cv2.rectangle(
            vis_image,
            (10, y_pos - 20),
            (10 + text_size[0] + 10, y_pos + 5),
            (0, 0, 0),
            -1,
        )
        # Tekst
        cv2.putText(
            vis_image, text, (15, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.6, text_color, 2
        )

    # Zapisz wizualizację
    vis_filename = f"{debug_dir}/detection_visualization_{timestamp}.jpg"
    cv2.imwrite(vis_filename, vis_image)

    print(f"DEBUG: Wizualizacja zapisana do {vis_filename}")

    return vis_image
