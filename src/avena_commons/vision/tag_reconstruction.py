from itertools import product
from typing import Any, Dict, List

import cv2
import numpy as np


class TagReconstuction:
    @staticmethod
    def reconsturct_tags_on_image(
        image: np.ndarray, tag_image: np.ndarray, config: dict = None
    ) -> np.ndarray:
        debug = {}
        if config is None:
            config = {
                "roi_config": {
                    "horizontal_slice": (0.33, 0.66),
                    "vertical_slice": (0.0, 1.0),  # Cała wysokość
                    "overlap_fraction": 0.2,
                },
                "scene_corners": ["BL", "TR", "BL", "TR"],
            }

        if tag_image.ndim == 3:
            tag_image = cv2.cvtColor(tag_image, cv2.COLOR_BGR2GRAY)

        ref_tag_shapes = TagReconstuction._create_reference_tag_shapes(tag_image)

        if config.get("central", False) == False:
            rois = TagReconstuction._divide_image_into_rois(image, config["roi_config"])
        else:
            rois = TagReconstuction._divide_image_into_roi(image)

        for i, roi in enumerate(rois):
            roi, debug = TagReconstuction._warp_tag_to_roi(
                ref_tag_shapes, roi, config["scene_corners"][i]
            )
            debug[f"roi_{i}"] = debug

        merged_image = TagReconstuction._merge_rois_into_image(image, rois)

        return merged_image

    @staticmethod
    def _create_reference_tag_shapes(
        tag_image: np.ndarray,
    ) -> list[np.ndarray]:  # MARK: create reference tag shapes
        contours = TagReconstuction._find_contours(tag_image)
        cnts_dict = TagReconstuction._filter_reference_cnts(contours)
        ref_cnts = TagReconstuction._list_of_cnt_per_type(cnts_dict)

        output = {}
        output["ref_cnts"] = ref_cnts
        output["cnts_dict"] = cnts_dict
        output["image"] = tag_image

        return output

    @staticmethod
    def _find_contours(image: np.ndarray) -> list[np.ndarray]:
        if image.ndim != 2:
            raise ValueError("Input must be a single‑channel (grayscale) image array.")

        # Binarise automatically with Otsu
        _, binary = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

        num_labels, labels = cv2.connectedComponents(
            binary, connectivity=4
        )  # labels: 0 .. num_labels‑1
        contours: list[np.ndarray] = []
        for lbl in range(1, num_labels):  # skip background 0
            mask = np.uint8(labels == lbl) * 255  # binary mask for this component
            cnts, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
            contours.extend(cnts)
        return contours

    @staticmethod
    def _filter_reference_cnts(cnts: list[np.ndarray]) -> list[dict]:
        """
        Output: a list of dicts with keys 'cnt' and 'type'.
        'cnt' is the contour, 'type' is the type index.
        Contours are grouped by shape similarity using cv2.matchShapes.
        The similarity threshold is set to 0.05.
        """
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)
        cnts = cnts[2:]  # filter out 2 largest contours

        groups = []
        assigned = [False] * len(cnts)
        threshold = 0.05

        for i, cnt in enumerate(cnts):
            if assigned[i]:
                continue
            group = [i]
            assigned[i] = True
            for j in range(i + 1, len(cnts)):
                if not assigned[j]:
                    similarity = cv2.matchShapes(
                        cnt, cnts[j], cv2.CONTOURS_MATCH_I1, 0.0
                    )
                    if similarity < threshold:
                        group.append(j)
                        assigned[j] = True
            groups.append(group)

        result = []
        for type_idx, group in enumerate(groups):
            for idx in group:
                result.append({"cnt": cnts[idx], "type": type_idx})

        return result

    @staticmethod
    def _list_of_cnt_per_type(cnts_dict: list[dict]) -> list[list[np.ndarray]]:
        """Return a list of contours grouped by type."""
        cnts_per_type = []
        current_type = 0
        for cnt_info in cnts_dict:
            type_idx = cnt_info["type"]
            if type_idx == current_type:
                cnts_per_type.append(cnt_info["cnt"])
                current_type += 1
        return cnts_per_type

    @staticmethod
    def _divide_image_into_roi(image: np.ndarray) -> np.ndarray:
        """
        Wyodrębnia centralny region zainteresowania (ROI) z obrazu.

        ROI stanowi środkowe 50% obrazu zarówno w osi X, jak i Y.

        Args:
            image (np.ndarray): Obraz wejściowy.

        Returns:
            np.ndarray: Wycięty centralny region obrazu (ROI).
        """
        h, w = image.shape[:2]

        # Obliczanie współrzędnych dla centralnego 50%
        x_start = int(w * 0.25)
        x_end = int(w * 0.75)
        y_start = int(h * 0.25)
        y_end = int(h * 0.75)

        # Wycięcie i zwrócenie ROI
        roi_image = image[y_start:y_end, x_start + 300 : x_end]

        roi = {
            "name": "central",
            "roi_image": roi_image,
            "origin": (x_start + 300, y_start),
            "warped_image": None,
            "does_it_contain_tag": False,
            "tag_mask": None,
            "correct_rotation": 90
        }

        rois = []
        rois.append(roi)

        return rois

    @staticmethod
    def _divide_image_into_rois(
        image: np.ndarray, config: Dict[str, Any] = None
    ) -> list[Dict[str, Any]]:  # MARK: divide image into rois
        """
        Dzieli obraz na 4 nakładające się na siebie regiony zainteresowania (ROI)
        zgodnie z podaną konfiguracją.

        Args:
            image: Obraz wejściowy w formacie NumPy.
            config: Słownik konfiguracyjny. Może zawierać:
                - horizontal_slice (tuple): Procentowy zakres szerokości do wycięcia (domyślnie 0.33-0.66).
                - vertical_slice (tuple): Procentowy zakres wysokości do wycięcia (domyślnie 0.0-1.0, czyli całość).
                - overlap_fraction (float): Procent, o jaki ROI mają na siebie nachodzić (domyślnie 0.2).

        Returns:
            Lista słowników, gdzie każdy słownik reprezentuje jeden ROI i zawiera:
                - 'name' (str): Nazwa ROI (TL, TR, BL, BR).
                - 'roi_image' (np.ndarray): Wycięty fragment obrazu.
                - 'origin' (tuple): Współrzędne (x, y) lewego górnego rogu ROI w oryginalnym obrazie.
        """
        if config is None:
            config = DEFAULT_ROI_CONFIG.copy()

        h, w = image.shape[:2]

        # Etap 1: Wycięcie głównej sekcji na podstawie konfiguracji
        x_start = int(w * config.get("horizontal_slice", (0.33, 0.66))[0])
        x_end = int(w * config.get("horizontal_slice", (0.33, 0.66))[1])
        y_start = int(h * config.get("vertical_slice", (0.0, 1.0))[0])
        y_end = int(h * config.get("vertical_slice", (0.0, 1.0))[1])

        main_section = image[y_start:y_end, x_start:x_end]
        main_section_origin = (x_start, y_start)

        # Etap 2: Wykrojenie 4 nakładających się ROI z głównej sekcji
        mh, mw = main_section.shape[:2]
        overlap = config.get("overlap_fraction", 0.2)

        # Obliczenie wymiarów ROI, aby nachodziły na siebie
        roi_h = int(mh * (0.5 + overlap / 2))
        roi_w = int(mw * (0.5 + overlap / 2))

        # Zgodnie z poleceniem, wysokość ROI jest zmniejszana do 2/3.
        # Dla TL i TR przycinany jest dół, a dla BL i BR - góra.
        shorter_roi_h = int(roi_h * (2 / 3))

        # Definicje współrzędnych (x1, y1, x2, y2) wewnątrz `main_section`
        roi_definitions = {
            "TL": (0, 0, roi_w, shorter_roi_h, 90),
            "TR": (mw - roi_w, 0, mw, shorter_roi_h, -90),
            "BL": (0, mh - shorter_roi_h, roi_w, mh, 90),
            "BR": (mw - roi_w, mh - shorter_roi_h, mw, mh, -90),
        }

        rois = []
        for name, (r_x1, r_y1, r_x2, r_y2, correct_rotation) in roi_definitions.items():
            # Wycięcie obrazu ROI
            roi_image = main_section[r_y1:r_y2, r_x1:r_x2]

            # Obliczenie globalnych koordynatów
            global_origin_x = main_section_origin[0] + r_x1
            global_origin_y = main_section_origin[1] + r_y1

            rois.append(
                {
                    "name": name,
                    "roi_image": roi_image,
                    "origin": (global_origin_x, global_origin_y),
                    "warped_image": None,
                    "does_it_contain_tag": False,
                    "tag_mask": None,
                    "correct_rotation": correct_rotation,
                }
            )

        return rois

    @staticmethod
    def _warp_tag_to_roi(
        ref_tag_dict: dict, roi_dict: dict, scene_corner: str = "TL"
    ) -> dict:  # MARK: warp tag to roi
        debug = {}
        tag_image = ref_tag_dict["image"]
        roi_image = roi_dict["roi_image"]
        roi_correct_rotation = roi_dict["correct_rotation"]

        processed_roi = TagReconstuction._preprocess_for_contours(roi_image)
        scene_contours = TagReconstuction._find_scenes_contours(processed_roi)
        similar_cnts_list = TagReconstuction._find_similar_cnts(
            scene_contours, ref_tag_dict["ref_cnts"], min_similarity_threshold=0.1
        )

        for i, similar_cnts in enumerate(similar_cnts_list):
            similar_cnts_list[i] = sorted(
                similar_cnts, key=cv2.contourArea, reverse=True
            )

        constelation = TagReconstuction._find_valid_contour_groups(
            similar_cnts_list, ref_tag_dict["ref_cnts"]
        )

        if len(constelation) == 0:
            return roi_dict, debug
            
        best_group = constelation[0]["contours"]
        
        src_a = TagReconstuction._canonicalise(
            ref_tag_dict["ref_cnts"][0], corner="TL"
        )  # reference (tag image)
        src_b = TagReconstuction._canonicalise(
            ref_tag_dict["ref_cnts"][1], corner="TL"
        )  # reference (tag image)
        src_c = TagReconstuction._canonicalise(
            ref_tag_dict["ref_cnts"][2], corner="TL"
        )  # reference (tag image)
        src_d = TagReconstuction._canonicalise(
            ref_tag_dict["ref_cnts"][3], corner="TL"
        )  # reference (tag image)
        
        dst_a = TagReconstuction._canonicalise(
            best_group[0], corner=scene_corner
        )  # contour found in scene
        dst_b = TagReconstuction._canonicalise(
            best_group[1], corner=scene_corner
        )  # contour found in scene
        dst_c = TagReconstuction._canonicalise(
            best_group[2], corner=scene_corner
        )  # contour found in scene
        dst_d = TagReconstuction._canonicalise(
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
        
        #MARK: Weryfikacja orientacji na podstawie rzeczywistego układu konturów w best_group
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
                    valid_diffs = [ # [x, y] True if positive, False if negative
                        [True, False],
                        [False, False],
                        [True, True]
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
                    valid_diffs = [ # [x, y] True if positive, False if negative
                        [False, True],
                        [True, True],
                        [False, False]
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
        

        warped = cv2.warpAffine(
            tag_image, M_aff6, (roi_image.shape[1], roi_image.shape[0])
        )

        # mask for warped image
        cnts, _ = cv2.findContours(warped, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        mask = np.zeros_like(roi_image)
        cv2.fillPoly(mask, cnts, 255)
        mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)

        blended = cv2.addWeighted(
            roi_image, 0.5, cv2.cvtColor(warped, cv2.COLOR_BGR2RGB), 0.5, 0
        )

        roi_dict["warped_image"] = blended
        roi_dict["does_it_contain_tag"] = True
        roi_dict["tag_mask"] = mask

        return roi_dict, debug

    @staticmethod
    def _preprocess_for_contours(image: np.ndarray) -> np.ndarray:
        """
        Przygotowuje obraz do detekcji konturów.

        Kroki:
        1. Konwersja do skali szarości.
        2. Poprawa kontrastu za pomocą CLAHE (Contrast Limited Adaptive Histogram Equalization).
        3. Adaptacyjna binaryzacja w celu uzyskania czystego obrazu czarno-białego.
        4. Operacja morfologiczna otwarcia w celu usunięcia drobnych szumów.

        Args:
            image (np.ndarray): Obraz wejściowy (może być kolorowy lub w skali szarości).

        Returns:
            np.ndarray: Obraz binarny, gotowy do analizy konturów.
        """
        if len(image.shape) > 2:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Poprawa kontrastu
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Adaptacyjna binaryzacja jest lepsza dla obrazów o nierównym oświetleniu
        binary = cv2.adaptiveThreshold(
            enhanced,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,  # Odwrócenie, aby obiekty były białe na czarnym tle
            blockSize=21,
            C=5,
        )

        # Usunięcie małych "kropek" szumu za pomocą operacji otwarcia
        kernel = np.ones((3, 3), np.uint8)
        opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

        return opened

    @staticmethod
    def _find_scenes_contours(image: np.ndarray) -> list[np.ndarray]:
        num_labels, labels = cv2.connectedComponents(image, connectivity=4)
        scene_contours = []
        for lbl in range(1, num_labels):
            mask = np.uint8(labels == lbl) * 255
            cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            scene_contours.extend(cnts)
        return scene_contours

    @staticmethod
    def _find_similar_cnts(
        scene_contours: list[np.ndarray],
        reference_contours: list[np.ndarray],
        min_similarity_threshold: float = 0.1,
    ) -> list[np.ndarray]:
        """
        I want to find similar counturs in scene_contours to reference_contours.
        each scene_cnt is similar to one of the reference_cnts,or none

        return list of lists that contains scene_cnts that are similar to each reference_cnt. For example: if reference_cnts = [cnt1, cnt2, cnt3] and scene_cnts = [cnt1, cnt2, cnt3, cnt4, cnt5, cnt6]
        then return should be like this: [[cnt1], [cnt2], [cnt3, cnt4, cnt5, cnt6]]
        score should decide to which reference_cnt scene_cnt is similar.
        if score is less than min_similarity_threshold, then scene_cnt is similar to reference_cnt.
        if score is greater than min_similarity_threshold, then scene_cnt is not similar to reference_cnt.
        if scene_cnt is not similar to any reference_cnt, then return None.
        if scene_cnt is similar to multiple reference_cnts, then return the one with the lowest score.
        if scene_cnt is not similar to any reference_cnt, then return None.

        """
        similar_cnts = [[] for _ in reference_contours]

        for scene_cnt in scene_contours:
            # Przechowujemy najlepszy wynik i indeks konturu referencyjnego.
            # Zamiast wartości '1' używam `float('inf')` jako początkowy wynik,
            # co jest bezpieczniejszym podejściem.
            best_match = {"score": float("inf"), "index": None}

            for i, reference_cnt in enumerate(reference_contours):
                # Porównanie kształtów konturów
                score = cv2.matchShapes(
                    reference_cnt, scene_cnt, cv2.CONTOURS_MATCH_I3, 0.0
                )

                if score < best_match["score"]:
                    best_match["score"] = score

                    # Sprawdzenie, czy wynik jest poniżej progu i czy jest to najlepszy
                    # dotychczasowy wynik dla tego konturu ze sceny.
                    if score < min_similarity_threshold:
                        best_match["score"] = score
                        best_match["index"] = (
                            i  # Przechowujemy indeks, a nie obiekt konturu
                        )

            # Jeśli znaleziono odpowiednie dopasowanie (indeks nie jest już None),
            # dodaj kontur ze sceny do odpowiedniej listy, używając zapisanego indeksu.

            if best_match["index"] is not None:
                similar_cnts[best_match["index"]].append(scene_cnt)

        return similar_cnts

    @staticmethod
    def _canonicalise(cnt, N=180, *, corner="TL"):
        """
        Resample a closed contour → clockwise → roll so index 0 is the chosen
        corner.

        Parameters
        ----------
        cnt : (M,1,2) or (M,2) array
        N   : number of resampled points
        corner : {"TL","TR","BL","BR"}
            TL = top-left       (min x, then min y)
            TR = top-right      (max x, then min y)
            BL = bottom-left    (min x, then max y)
            BR = bottom-right   (max x, then max y)
        """

        def resample_contour(cnt, N=180):
            """Return N equally-spaced samples around a closed contour."""
            p = cnt.reshape(-1, 2).astype(np.float32)
            seg = np.linalg.norm(np.diff(p, axis=0, append=p[:1]), axis=1)
            s = np.concatenate(([0], np.cumsum(seg)))
            t = np.linspace(0, s[-1], N, endpoint=False)
            p2 = np.vstack([p, p[0]])
            x = np.interp(t, s, p2[:, 0])
            y = np.interp(t, s, p2[:, 1])
            return np.column_stack([x, y]).astype(np.float32)

        q = resample_contour(cnt, N)

        # 1. make clockwise  (positive signed area)
        if cv2.contourArea(q.reshape(-1, 1, 2)) < 0:
            q = q[::-1]

        # 2. choose deterministic start index
        if corner == "TL":
            k = np.lexsort((q[:, 1], q[:, 0]))[0]  # min x , then min y
        elif corner == "TR":
            k = np.lexsort((q[:, 1], -q[:, 0]))[0]  # max x , then min y
        elif corner == "BL":
            k = np.lexsort((-q[:, 1], q[:, 0]))[0]  # min x , then max y
        elif corner == "BR":
            k = np.lexsort((-q[:, 1], -q[:, 0]))[0]  # max x , then max y
        else:
            raise ValueError("corner must be 'TL', 'TR', 'BL' or 'BR'")

        return np.roll(q, -k, axis=0).astype(np.float32)

    @staticmethod
    def _merge_rois_into_image(base: np.ndarray, rois: List[Dict]) -> np.ndarray:
        """
        Paste every ROI back onto *base* using roi['tag_mask'] as a stencil.

        ROI dict must contain
            'origin'            : (x, y)   – top-left corner on *base*
            'warped_image'      : H_r×W_r×3  (uint8 BGR or RGB, doesn't matter)
            'tag_mask'          : H_r×W_r    uint8 0 or 255  (single channel)
            'does_it_contain_tag': bool
        """
        canvas = base.copy()

        for roi in rois:
            if not roi.get("does_it_contain_tag", False):
                continue

            x0, y0 = roi["origin"]
            patch = roi["warped_image"]
            roi_mask = roi.get("tag_mask")
            if roi_mask is None:
                continue
            
            #MARK: ROI MASK BBOX SIZE CHECK
            roi_mask_bbox = cv2.boundingRect(roi_mask)
            roi_mask_bbox_size = roi_mask_bbox[2] * roi_mask_bbox[3]
            
            if roi_mask_bbox_size < 10000:
                continue
            
            ph, pw = patch.shape[:2]

            # ---------- clip ROI to canvas bounds ----------------------------
            x1, y1 = max(0, x0), max(0, y0)
            x2, y2 = min(canvas.shape[1], x0 + pw), min(canvas.shape[0], y0 + ph)
            if x2 <= x1 or y2 <= y1:
                continue  # ROI lies completely outside

            patch_sub = patch[y1 - y0 : y2 - y0, x1 - x0 : x2 - x0]
            mask_sub = roi_mask[y1 - y0 : y2 - y0, x1 - x0 : x2 - x0]

            # ---------- copy where mask != 0 ---------------------------------
            dst = canvas[y1:y2, x1:x2]
            cv2.copyTo(patch_sub, mask_sub, dst)  # in-place on canvas slice

        return canvas

    @staticmethod
    def _calculate_geometric_features(centroids):
        """Oblicza cechy geometryczne dla zbioru centroidów."""
        if len(centroids) < 2:
            return None

        centroids = np.array(centroids)

        # Oblicz macierz odległości
        distances = np.linalg.norm(centroids[:, None] - centroids[None, :], axis=2)

        # Oblicz kąty między parami punktów
        angles = []
        for i in range(len(centroids)):
            for j in range(i + 1, len(centroids)):
                for k in range(j + 1, len(centroids)):
                    # Kąt między trzema punktami (i, j, k)
                    v1 = centroids[i] - centroids[j]
                    v2 = centroids[k] - centroids[j]

                    # Oblicz kąt
                    dot_product = np.dot(v1, v2)
                    norms = np.linalg.norm(v1) * np.linalg.norm(v2)
                    if norms > 0:
                        angle = np.arccos(np.clip(dot_product / norms, -1.0, 1.0))
                        angles.append(np.degrees(angle))

        return {
            "distances": distances,
            "angles": angles,
            "centroid": np.mean(centroids, axis=0),
            "bounding_box": (np.min(centroids, axis=0), np.max(centroids, axis=0)),
            "span": np.max(centroids, axis=0) - np.min(centroids, axis=0),
        }

    @staticmethod
    def _check_geometric_constellation(
        reference_centroids,
        scene_centroids,
        max_distance_ratio=0.3,
        max_angle_diff=15.0,
    ):
        """Sprawdza, czy układ centroidów w scenie odpowiada układowi referencyjnemu."""
        if len(reference_centroids) != len(scene_centroids):
            return False

        ref_features = TagReconstuction._calculate_geometric_features(
            reference_centroids
        )
        scene_features = TagReconstuction._calculate_geometric_features(scene_centroids)

        if ref_features is None or scene_features is None:
            return False

        # Sprawdź stosunek odległości
        ref_distances = ref_features["distances"]
        scene_distances = scene_features["distances"]

        # Normalizuj odległości przez największą odległość
        if np.max(ref_distances) > 0 and np.max(scene_distances) > 0:
            ref_distances_norm = ref_distances / np.max(ref_distances)
            scene_distances_norm = scene_distances / np.max(scene_distances)

            # Sprawdź różnice w odległościach
            distance_diff = np.abs(ref_distances_norm - scene_distances_norm)
            if np.max(distance_diff) > max_distance_ratio:
                return False

        # Sprawdź różnice w kątach (jeśli są dostępne)
        if len(ref_features["angles"]) > 0 and len(scene_features["angles"]) > 0:
            ref_angles = np.array(ref_features["angles"])
            scene_angles = np.array(scene_features["angles"])

            if len(ref_angles) == len(scene_angles):
                angle_diff = np.abs(ref_angles - scene_angles)
                if np.max(angle_diff) > max_angle_diff:
                    return False

        return True

    @staticmethod
    def _get_contour_centroid(contour):
        """Calculates the centroid of a single contour."""
        M = cv2.moments(contour)
        if M["m00"] == 0:
            return None  # Avoid division by zero
        cX = int(M["m10"] / M["m00"])
        cY = int(M["m01"] / M["m00"])
        return np.array([cX, cY])

    @staticmethod
    def _find_valid_contour_groups(similar_cnts, ref_cnts, max_distance=100):
        """Znajduje grupy konturów, które spełniają relacje geometryczne."""
        valid_groups = []

        # Oblicz centroidy konturów referencyjnych
        ref_centroids = []
        for cnt in ref_cnts:
            centroid = TagReconstuction._get_contour_centroid(cnt)
            if centroid is not None:
                ref_centroids.append(centroid)

        # Upewnij się, że mamy przynajmniej jeden kontur każdego typu
        valid_similar_cnts = []
        for i, cnts in enumerate(similar_cnts):
            if len(cnts) > 0:
                valid_similar_cnts.append(cnts)
            else:
                # Jeśli brak konturów danego typu, nie możemy utworzyć konstelacji
                return []

        # Sprawdź wszystkie kombinacje
        for combination in product(*valid_similar_cnts):
            # Oblicz centroidy dla tej kombinacji
            scene_centroids = []
            for cnt in combination:
                centroid = TagReconstuction._get_contour_centroid(cnt)
                if centroid is not None:
                    scene_centroids.append(centroid)

            # Sprawdź, czy wszystkie centroidy są blisko siebie
            if len(scene_centroids) < 2:
                continue

            # Sprawdź maksymalne odległości między centroidami
            max_dist = 0
            for i in range(len(scene_centroids)):
                for j in range(i + 1, len(scene_centroids)):
                    dist = np.linalg.norm(
                        np.array(scene_centroids[i]) - np.array(scene_centroids[j])
                    )
                    max_dist = max(max_dist, dist)

            if max_dist > max_distance:
                continue

            # Sprawdź konstelację geometryczną
            if TagReconstuction._check_geometric_constellation(
                ref_centroids, scene_centroids
            ):
                valid_groups.append(
                    {
                        "contours": combination,
                        "centroids": scene_centroids,
                        "max_distance": max_dist,
                    }
                )

        # Sortuj według jakości (najmniejsze odległości najpierw)
        # valid_groups.sort(key=lambda x: x["max_distance"])

        return valid_groups

    @staticmethod
    def _check_centroids_proximity(centroids, max_distance=100):
        """Sprawdza, które centroidy są blisko siebie."""
        if len(centroids) < 2:
            return []

        valid_centroids = []

        for i, centroid_a in enumerate(centroids):
            close_neighbors = [centroid_a]

            for j, centroid_b in enumerate(centroids):
                if i != j:
                    distance = np.sqrt(
                        (centroid_a[0] - centroid_b[0]) ** 2
                        + (centroid_a[1] - centroid_b[1]) ** 2
                    )

                    if distance <= max_distance:
                        close_neighbors.append(centroid_b)

            if len(close_neighbors) >= 2:
                for neighbor in close_neighbors:
                    if not any(np.array_equal(neighbor, vc) for vc in valid_centroids):
                        valid_centroids.append(neighbor)

        return valid_centroids
