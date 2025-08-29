import cv2
import numpy as np

from avena_commons.util.catchtime import Catchtime
from avena_commons.util.logger import debug
from avena_commons.vision.vision.merge_depth_lists import merge_depth_lists
from avena_commons.vision.vision.propagate_by_shape import propagate_by_shape


def fix_depth(depth_image, config):
    """Naprawia i uzupełnia brakujące wartości w obrazie głębi (depth image).

    Funkcja wykonuje serię operacji morfologicznych i algorytmów inpainting'u
    w celu wypełnienia obszarów z zerowymi wartościami głębi (holes) w obrazie
    3D. Proces składa się z 5 głównych kroków przetwarzania.

    Args:
        depth_image: Obraz głębi w formacie numpy.ndarray z wartościami odległości
        config: Słownik z konfiguracją zawierający:
            - closing_mask (dict): Parametry maski zamykającej dla obrazu głębi:
                - kernel_size (int): Rozmiar jądra morfologicznego
                - iterations (int): Liczba iteracji operacji morfologicznej
            - zero_mask (dict): Parametry maski dla obszarów zerowych:
                - kernel_size (int): Rozmiar jądra morfologicznego
                - iterations (int): Liczba iteracji operacji morfologicznej
            - r_wide (float): Współczynnik szerokości dla propagacji kształtu
            - r_tall (float): Współczynnik wysokości dla propagacji kształtu
            - final_closing_mask (dict): Parametry końcowej maski zamykającej:
                - kernel_size (int): Rozmiar jądra morfologicznego
                - iterations (int): Liczba iteracji operacji morfologicznej

    Returns:
        numpy.ndarray: Obraz głębi po naprawie i uzupełnieniu brakujących wartości

    Example:
        >>> config = {
        ...     "closing_mask": {"kernel_size": 10, "iterations": 2},
        ...     "zero_mask": {"kernel_size": 10, "iterations": 2},
        ...     "r_wide": 2.0, "r_tall": 0.5,
        ...     "final_closing_mask": {"kernel_size": 10, "iterations": 2}
        ... }
        >>> fixed_depth = fix_depth(depth_image, config)
    """
    # debug_dict = {}

    # STEP 1: CLOSE DEPTH IMAGE
    # Operacja morfologiczna zamykania na obrazie głębi
    # Zamyka małe dziury i łączy bliskie obiekty
    with Catchtime() as t1:
        kernel = np.ones(
            (
                config["closing_mask"]["kernel_size"],
                config["closing_mask"]["kernel_size"],
            ),
            np.uint8,
        )
        closed_depth_image = cv2.morphologyEx(
            depth_image,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=config["closing_mask"]["iterations"],
        )

    # if debug:
    #     debug_dict["closed_depth_image"] = closed_depth_image

    # STEP 2: CREATE ZERO DEPTH MASK
    # Tworzy maskę obszarów z zerowymi wartościami głębi
    # Następnie zamyka morfologicznie tę maskę aby połączyć bliskie obszary
    with Catchtime() as t2:
        zero_depth_mask = closed_depth_image == 0
        zero_depth_mask = zero_depth_mask.astype(np.uint8) * 255
        kernel = np.ones(
            (config["zero_mask"]["kernel_size"], config["zero_mask"]["kernel_size"]),
            np.uint8,
        )
        closed_zero_mask = cv2.morphologyEx(
            zero_depth_mask,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=config["zero_mask"]["iterations"],
        )

    # if debug:
    #     debug_dict["zero_depth_mask"] = zero_depth_mask
    #     debug_dict["closed_zero_mask"] = closed_zero_mask

    # STEP 3: SPLIT ZERO DEPTH MASK
    # Dzieli maskę obszarów zerowych na pojedyncze, spójne komponenty
    # Każdy obszar staje się osobną maską do przetworzenia
    with Catchtime() as t3:
        zero_depth_mask_list = []
        n, labels = cv2.connectedComponents(closed_zero_mask, connectivity=8)
        for i in range(1, n):
            mask = np.zeros_like(closed_zero_mask)
            mask[labels == i] = 255
            zero_depth_mask_list.append(mask)

    # if debug:
    #     debug_dict["zero_depth_mask_list"] = zero_depth_mask_list

    # STEP 4: PROPAGATE ZERO DEPTH MASK - #README NAJBARDZIEJ KOSZTOWNY CZASOWO KROK ~66% CZASU
    # Dla każdego obszaru zerowego wykonuje inpainting oparty na kształcie
    # Uzupełnia brakujące wartości głębi na podstawie otaczających pikseli
    with Catchtime() as t4:
        inpainted_depth_list = []
        for mask in zero_depth_mask_list:
            inpainted_depth = propagate_by_shape(
                closed_depth_image, mask, config["r_wide"], config["r_tall"]
            )
            inpainted_depth_list.append(inpainted_depth)
    # if debug:
    #     debug_dict["inpainted_depth_list"] = inpainted_depth_list

    # STEP 5: MERGE INPAINTED DEPTH
    # Łączy wszystkie uzupełnione obszary głębi w jeden obraz
    # Wykonuje końcową operację morfologiczną dla wygładzenia wyników
    with Catchtime() as t5:
        depth_merged = merge_depth_lists(
            closed_depth_image, inpainted_depth_list, zero_depth_mask_list
        )
        kernel = np.ones(
            (
                config["final_closing_mask"]["kernel_size"],
                config["final_closing_mask"]["kernel_size"],
            ),
            np.uint8,
        )
        depth_merged_closed = cv2.morphologyEx(
            depth_merged,
            cv2.MORPH_CLOSE,
            kernel,
            iterations=config["final_closing_mask"]["iterations"],
        )
    debug(
        f"fix_depth: t1: {t1.t * 1_000:.1f}ms t2: {t2.t * 1_000:.1f}ms t3: {t3.t * 1_000:.1f}ms t4: {t4.t * 1_000:.1f}ms t5: {t5.t * 1_000:.1f}ms"
    )

    return depth_merged_closed
