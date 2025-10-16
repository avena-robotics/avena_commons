


def qr_output_process(detection_list: list, middle_point_y: int = 540) -> dict:
    """Przetwarza listę detekcji QR i organizuje je w siatce 2x2.

    Funkcja przyjmuje listę detekcji kodów QR i organizuje je w siatce 2x2
    na podstawie pozycji Y i kąta rotacji Z. Obecnie funkcja jest w fazie rozwoju
    i większość logiki jest zakomentowana.

    Args:
        detection_list: Lista obiektów detekcji QR
        middle_point_y: Punkt podziału Y dla górnego i dolnego rzędu (domyślnie 540)

    Returns:
        dict: Słownik z kluczami 1-4 reprezentującymi pozycje w siatce:
            - 1: Górny lewy
            - 2: Dolny lewy
            - 3: Górny prawy
            - 4: Dolny prawy
            Wartości to None jeśli brak detekcji w danej pozycji

    Example:
        >>> detections = [qr_detection1, qr_detection2]
        >>> result = qr_output_process(detections, middle_point_y=500)
        >>> print(f"Górny lewy: {result[1]}")
    """
    if detection_list is None or len(detection_list) == 0:
        return {1: None, 2: None, 3: None, 4: None}

    centers = []
    for detection in detection_list:
        print(f"detection: {detection}")
        # vision.calculate_pose_pnp(
        #     detection.corners,
        #     detection.a,
        #     detection.b,
        #     detection.camera_params,
        #     detection.z,
        # )
    #     # min_x, min_y = (
    #     #     int(np.min(detection.corners[:, 0], axis=0)),
    #     #     int(np.min(detection.corners[:, 1], axis=0)),
    #     # )
    #     # max_x, max_y = (
    #     #     int(np.max(detection.corners[:, 0], axis=0)),
    #     #     int(np.max(detection.corners[:, 1], axis=0)),
    #     # )

    #     # depth_original - Do obliczenia odległości do obiektu. Jest dokładniesza niż z translacji ale zdaża się że nie wykryję głębi w tym miejscu dlatego mamy 2 opcje. If jest w funkcji calculate_pose_pnp
    #     # cropped_depth_array = depth_original[min_y:max_y, min_x:max_x]
    #     # z = np.median(cropped_depth_array) / 1000

    #     corners = detection.corners.tolist()
    #     print(detection)

    #     detected = [
    #         detection.center[0],
    #         detection.center[1],
    #         corners,
    #         detection.center[1],  # FIXME - tu ma byc z
    #         detection.pose_t,
    #         rotation_matrix_to_rvec(
    #             euler_to_rotation_matrix(
    #                 0, 0, rotation_matrix_to_euler_angles(detection.pose_R)[2]
    #             )
    #         ),
    #     ]
    #     centers.append(detected)

    result = {1: None, 2: None, 3: None, 4: None}

    for c in centers:
        y = c[1]
        rot_z = c[5][2]

        if y < middle_point_y:
            # Top row
            if rot_z < 0:
                result[1] = c  # Top-left
            else:
                result[3] = c  # Top-right
        else:
            # Bottom row
            if rot_z < 0:
                result[2] = c  # Bottom-left
            else:
                result[4] = c  # Bottom-right

    if (
        result[1] is None
        and result[2] is None
        and result[3] is None
        and result[4] is None
    ):
        return {1: None, 2: None, 3: None, 4: None}

    return result
