"""
Moduł do mapowania perspektywicznego tagów referencyjnych na ROI.

Zasady działania:
--------------
Moduł implementuje zaawansowany algorytm mapowania perspektywicznego tagów
wizyjnych z obrazu referencyjnego na regiony zainteresowania (ROI) w obrazie
docelowym. Proces obejmuje wykrywanie konturów, dopasowywanie geometryczne
i transformację afinową z walidacją orientacji.

Pipeline mapowania:
------------------
1. **Preprocessing ROI**: Przygotowanie obrazu ROI do analizy konturów
2. **Wykrycie konturów**: Znalezienie konturów w scenie
3. **Dopasowanie**: Identyfikacja konturów podobnych do referencyjnych
4. **Grupowanie**: Walidacja konstelacji konturów
5. **Kanonizacja**: Normalizacja punktów kontrolnych
6. **Transformacja**: Obliczenie macierzy afinowej
7. **Walidacja orientacji**: Sprawdzenie poprawności układu geometrycznego
8. **Mapowanie**: Aplikacja transformacji i tworzenie maski

Algorytm walidacji:
------------------
- Analiza pozycji centroidów konturów
- Sprawdzenie względnych różnic współrzędnych
- Walidacja zgodnie z oczekiwaną rotacją (90° lub -90°)
- Odrzucenie nieprawidłowych konstelacji

Zastosowania:
- Rekonstrukcja tagów QR/AR z perspektywy
- Mapowanie wzorców referencyjnych na sceny
- Poprawa jakości tagów wizyjnych
- Automatyczna korekcja zniekształceń perspektywicznych
"""

import cv2
import numpy as np

import avena_commons.vision.preprocess as preprocess
import avena_commons.vision.tag_reconstruction as tag_reconstruction


def wrap_tag_to_roi(
    ref_tag_dict: dict, roi_dict: dict, scene_corner: str = "TL"
) -> tuple[dict, dict]:  # MARK: warp tag to roi
    """
    Mapuje tag referencyjny na region zainteresowania (ROI) z uwzględnieniem perspektywy.

    Funkcja implementuje kompletny pipeline mapowania perspektywicznego tagów
    wizyjnych, obejmujący wykrywanie konturów, dopasowywanie geometryczne,
    transformację afinową i walidację orientacji.

    Zasada działania:
    ----------------
    1. **Preprocessing**: Przygotowanie ROI do analizy konturów
    2. **Wykrycie konturów**: Znalezienie konturów w scenie ROI
    3. **Dopasowanie**: Identyfikacja konturów podobnych do referencyjnych
    4. **Grupowanie**: Walidacja konstelacji konturów (minimum 4 kontury)
    5. **Kanonizacja**: Normalizacja punktów kontrolnych dla transformacji
    6. **Transformacja afinowa**: Obliczenie macierzy mapowania perspektywicznego
    7. **Walidacja orientacji**: Sprawdzenie poprawności układu geometrycznego
    8. **Mapowanie**: Aplikacja transformacji i tworzenie maski
    9. **Blendowanie**: Połączenie oryginalnego ROI z zmapowanym tagiem

    Parametry:
    ----------
    ref_tag_dict : dict
        Słownik zawierający dane referencyjne tagu:
        - 'image': obraz tagu referencyjnego
        - 'ref_cnts': skategoryzowane kontury referencyjne

    roi_dict : dict
        Słownik ROI zawierający:
        - 'roi_image': obraz regionu zainteresowania
        - 'correct_rotation': oczekiwana rotacja korekcyjna

    scene_corner : str, default="TL"
        Narożnik sceny używany do kanonizacji konturów (TL, TR, BL, BR)

    Zwraca:
    -------
    tuple[dict, dict]
        Krotka zawierająca:
        - roi_dict: zaktualizowany słownik ROI z polami:
            - 'warped_image': zmapowany i zblendowany obraz
            - 'does_it_contain_tag': flaga obecności tagu
            - 'tag_mask': maska tagu
        - debug: słownik z informacjami debugowania

    Przykład:
    ---------
    >>> ref_data = {'image': ref_tag, 'ref_cnts': ref_contours}
    >>> roi_data = {'roi_image': roi_img, 'correct_rotation': 90}
    >>> updated_roi, debug_info = wrap_tag_to_roi(ref_data, roi_data, "TL")
    >>> if updated_roi['does_it_contain_tag']:
    ...     print("Tag successfully mapped to ROI")

    Uwagi:
    ------
    - Wymagane minimum 4 kontury dla walidacji konstelacji
    - Walidacja orientacji oparta na analizie pozycji centroidów
    - Transformacja afinowa z RANSAC dla odporności na szum
    - Blendowanie 50/50 między oryginalnym ROI a zmapowanym tagiem
    """
    debug = {}
    tag_image = ref_tag_dict["image"]
    roi_image = roi_dict["roi_image"]
    roi_correct_rotation = roi_dict["correct_rotation"]

    processed_roi = tag_reconstruction.preprocess_for_contours(roi_image)
    scene_contours = tag_reconstruction.find_scenes_contours(processed_roi)
    similar_cnts_list = tag_reconstruction.find_similar_contours(
        scene_contours, ref_tag_dict["ref_cnts"], min_similarity_threshold=0.1
    )

    for i, similar_cnts in enumerate(similar_cnts_list):
        similar_cnts_list[i] = sorted(similar_cnts, key=cv2.contourArea, reverse=True)

    constelation = tag_reconstruction.find_valid_contour_groups(
        similar_cnts_list, ref_tag_dict["ref_cnts"]
    )

    if len(constelation) == 0:
        return roi_dict, debug

    best_group = constelation[0]["contours"]

    src_a = tag_reconstruction.canonicalise(
        ref_tag_dict["ref_cnts"][0], corner="TL"
    )  # reference (tag image)
    src_b = tag_reconstruction.canonicalise(
        ref_tag_dict["ref_cnts"][1], corner="TL"
    )  # reference (tag image)
    src_c = tag_reconstruction.canonicalise(
        ref_tag_dict["ref_cnts"][2], corner="TL"
    )  # reference (tag image)
    src_d = tag_reconstruction.canonicalise(
        ref_tag_dict["ref_cnts"][3], corner="TL"
    )  # reference (tag image)

    dst_a = tag_reconstruction.canonicalise(
        best_group[0], corner=scene_corner
    )  # contour found in scene
    dst_b = tag_reconstruction.canonicalise(
        best_group[1], corner=scene_corner
    )  # contour found in scene
    dst_c = tag_reconstruction.canonicalise(
        best_group[2], corner=scene_corner
    )  # contour found in scene
    dst_d = tag_reconstruction.canonicalise(
        best_group[3], corner=scene_corner
    )  # contour found in scene

    # dst_a = TagReconstuction._canonicalise(
    #     similar_cnts_list[0][0], corner=scene_corner
    # )  # contour found in scene
    # dst_b = TagReconstuction._canonicalise(
    #     similar_cnts_list[1][0], corner=scene_corner
    # )  # contour found in scene

    src = np.vstack([src_a, src_b, src_c, src_d])
    dst = np.vstack([dst_a, dst_b, dst_c, dst_d])

    M_aff6, inliers = cv2.estimateAffine2D(
        src,
        dst,
        inliers=None,
        method=cv2.RANSAC,
        ransacReprojThreshold=3.0,
        maxIters=4000,
        confidence=0.995,
        refineIters=10,
    )

    # MARK: Weryfikacja orientacji na podstawie rzeczywistego układu konturów w best_group
    if M_aff6 is not None and len(constelation) > 0:
        # Oblicz dokładne pozycje centroidów dla każdego konturu w best_group
        # print(f"=== CONTOUR POSITIONS ANALYSIS ===")
        # print(f"Number of contours in best_group: {len(best_group)}")
        if len(best_group) != 4:
            # print("REJECTED: Insufficient contours")
            roi_dict["warped_image"] = None
            roi_dict["does_it_contain_tag"] = False
            roi_dict["tag_mask"] = None
            debug["rejection_reason"] = "Insufficient contours"
            return roi_dict, debug

        group_centroids = []
        for i, cnt in enumerate(best_group):
            M_cnt = cv2.moments(cnt)
            if M_cnt["m00"] != 0:
                cx = M_cnt["m10"] / M_cnt["m00"]
                cy = M_cnt["m01"] / M_cnt["m00"]
                group_centroids.append([cx, cy])
            else:
                # print(f"Contour[{i}]: ZERO AREA - invalid!")
                pass

        diff_x = []
        diff_y = []
        # Prosty wydruk pozycji z różnicami względem cnt[0]
        if len(group_centroids) > 0:
            ref_x, ref_y = group_centroids[0]
            # print(f"cnt[0] - {ref_x:.1f} {ref_y:.1f}")

            for i in range(1, len(group_centroids)):
                x, y = group_centroids[i]
                cnt_diff_x = x - ref_x
                cnt_diff_y = y - ref_y
                diff_x.append(cnt_diff_x > 0)
                diff_y.append(cnt_diff_y > 0)
                # print(f"cnt[{i}] - {x:.1f} {y:.1f} | diff from cnt[0]: ({cnt_diff_x:+.1f}, {cnt_diff_y:+.1f})")
        else:
            # print("No valid centroids found!")
            pass

        match roi_correct_rotation:
            case 90:
                valid_diffs = [  # [x, y] True if positive, False if negative
                    [True, False],
                    [False, False],
                    [True, True],
                ]
                valid_diffs_found = True

                for i, diff in enumerate(valid_diffs):
                    if diff_x[i] != diff[0] or diff_y[i] != diff[1]:
                        valid_diffs_found = False

                if valid_diffs_found:
                    # print("VALID DIFF")
                    pass
                else:
                    # print("INVALID DIFF")
                    roi_dict["warped_image"] = None
                    roi_dict["does_it_contain_tag"] = False
                    roi_dict["tag_mask"] = None
                    return roi_dict, debug
            case -90:
                valid_diffs = [  # [x, y] True if positive, False if negative
                    [False, True],
                    [True, True],
                    [False, False],
                ]
                valid_diffs_found = True

                for i, diff in enumerate(valid_diffs):
                    if diff_x[i] != diff[0] or diff_y[i] != diff[1]:
                        valid_diffs_found = False

                if valid_diffs_found:
                    # print("VALID DIFF")
                    pass
                else:
                    # print("INVALID DIFF")
                    roi_dict["warped_image"] = None
                    roi_dict["does_it_contain_tag"] = False
                    roi_dict["tag_mask"] = None
                    return roi_dict, debug
    else:
        # debug("M_aff6 is None")
        roi_dict["warped_image"] = None
        roi_dict["does_it_contain_tag"] = False
        roi_dict["tag_mask"] = None
        return roi_dict, debug

    warped = cv2.warpAffine(tag_image, M_aff6, (roi_image.shape[1], roi_image.shape[0]))

    # mask for warped image
    cnts, _ = cv2.findContours(warped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    mask = np.zeros_like(roi_image)
    cv2.fillPoly(mask, cnts, 255)
    mask = preprocess.to_gray(mask)

    blended = cv2.addWeighted(
        roi_image, 0.5, cv2.cvtColor(warped, cv2.COLOR_BGR2RGB), 0.5, 0
    )

    roi_dict["warped_image"] = blended
    roi_dict["does_it_contain_tag"] = True
    roi_dict["tag_mask"] = mask

    return roi_dict, debug
