import math

import cv2
import numpy as np
import os
import pickle
from copy import deepcopy


class Vision:
    """
    Vision class responsible for image processing and object detection.
    """

    @staticmethod
    def create_box_depth_mask(depth_image, config):  # MARK: CREATE BOX DEPTH MASK
        """
        Creates a depth mask for box detection.

        :param depth_image: Depth image from the camera
        :param config: Dictionary containing mask configuration parameters:
                      - center_size: Size of the center region to calculate median depth
                      - depth_range: Range of acceptable depth values
                      - depth_bias: Bias adjustment for depth calculation
        :return: Binary mask based on depth thresholds
        """
        center_of_the_image = config["center_point"]
        center_size = config["center_size"]

        depth_image_cropped = depth_image[
            center_of_the_image[1] - center_size : center_of_the_image[1] + center_size,
            center_of_the_image[0] - center_size : center_of_the_image[0] + center_size,
        ]

        depth_image_cropped_0 = depth_image_cropped[depth_image_cropped == 0].flatten()
        depth_image_cropped_non_0 = depth_image_cropped[depth_image_cropped != 0].flatten()

        non_zero_percentage = len(depth_image_cropped_non_0) / (len(depth_image_cropped_0) + len(depth_image_cropped_non_0))

        if non_zero_percentage < config["min_non_zero_percentage"]:
            return None

        median_depth = np.median(depth_image_cropped_non_0)

        depth_range = [
            int(median_depth - config["depth_range"] - config["depth_bias"]),
            int(median_depth - config["depth_bias"]),
        ]

        return cv2.inRange(depth_image, depth_range[0], depth_range[1])

    @staticmethod
    def create_box_color_mask(color_image, config):  # MARK: CREATE BOX COLOR MASK
        """
        Creates a color mask for box detection using HSV color space.

        :param color_image: BGR color image
        :param config: Dictionary containing HSV threshold parameters:
                      - hsv_h_min/max: Hue range
                      - hsv_s_min/max: Saturation range
                      - hsv_v_min/max: Value range
        :return: Binary mask based on HSV thresholds
        """
        hsv_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv_image)

        mask_h = cv2.inRange(h, config["hsv_h_min"], config["hsv_h_max"])
        mask_s = cv2.inRange(s, config["hsv_s_min"], config["hsv_s_max"])
        mask_v = cv2.inRange(v, config["hsv_v_min"], config["hsv_v_max"])

        mask = mask_h & mask_s & mask_v
        return mask

    @staticmethod
    def merge_masks(masks: list[np.ndarray]):  # MARK: MERGE MASKS
        """
        Combines multiple binary masks using bitwise AND operation.

        :param masks: List of binary masks to be combined
        :return: Single combined binary mask
        """
        return np.bitwise_and.reduce(masks)

    @staticmethod
    def preprocess_mask(mask, config):  # MARK: PREPROCESS MASK
        blur_size = config["blur_size"]
        opened_size = config["opened_size"]
        opened_iterations = config["opened_iterations"]
        closed_size = config["closed_size"]
        closed_iterations = config["closed_iterations"]
        opened_kernel_type = config["opened_kernel_type"]
        closed_kernel_type = config["closed_kernel_type"]

        if blur_size % 2 == 0:
            blur_size += 1

        blurred = cv2.GaussianBlur(mask, (blur_size, blur_size), 0)
        _, mask_smoothed = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        kernel_opened = cv2.getStructuringElement(opened_kernel_type, (opened_size[0], opened_size[1]))
        mask_opened = cv2.morphologyEx(mask_smoothed, cv2.MORPH_OPEN, kernel_opened, iterations=opened_iterations)
        kernel_closed = cv2.getStructuringElement(closed_kernel_type, (closed_size[0], closed_size[1]))
        mask_closed = cv2.morphologyEx(mask_opened, cv2.MORPH_CLOSE, kernel_closed, iterations=closed_iterations)

        return mask_closed

    @staticmethod
    def undistort_image(image, camera_params, dist):  # MARK: UNDISTORT IMAGE
        """
        Corrects lens distortion in the image.

        :param image: Input distorted image
        :param camera_params: List/array of camera parameters [fx, fy, cx, cy]
                            where fx,fy are focal lengths and cx,cy are principal points
        :param dist: Distortion coefficients
        :return: Undistorted image
        """
        camera_matrix = np.array(
            [
                [camera_params[0], 0, camera_params[2]],
                [0, camera_params[1], camera_params[3]],
                [0, 0, 1],
            ],
            dtype=np.float32,
        )
        dist = np.array(dist, dtype=np.float32)
        return cv2.undistort(image, camera_matrix, dist)

    @staticmethod
    def find_cnts(mask):  # MARK: FIND CONTOURS
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        return contours

    @staticmethod
    def remove_cnts_outside_expected_bbox(contours, config):  # MARK: REMOVE CONTOURS OUTSIDE EXPECTED BOX
        def distance_from_center(cnt, center_point):
            x, y, w, h = cv2.boundingRect(cnt)
            return ((x + w / 2 - center_point[0]) ** 2 + (y + h / 2 - center_point[1]) ** 2) ** 0.5

        center_point = config["center_point"]
        box_expected_width = config["expected_width"]
        box_expected_height = config["expected_height"]

        expected_bbox = (center_point[0] - box_expected_width // 2, center_point[1] - box_expected_height // 2, box_expected_width, box_expected_height)

        box_cnts = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if not (
                x + w < expected_bbox[0]  # contour is left of bbox
                or x > expected_bbox[0] + expected_bbox[2]  # contour is right of bbox
                or y + h < expected_bbox[1]  # contour is above bbox
                or y > expected_bbox[1] + expected_bbox[3]
            ):  # contour is below bbox
                box_cnts.append(contour)

        box_cnts.sort(key=lambda cnt: distance_from_center(cnt, center_point))

        return box_cnts

    @staticmethod
    def get_hit_contours(mask, cnts, config):  # MARK: GET HIT CONTOURS
        def label_contours(image_shape, contours):
            """
            Create a labeled mask where each contour is filled with a unique integer label.
            """
            labeled_mask = np.zeros(image_shape, dtype=np.int32)
            for i, cnt in enumerate(contours, start=1):  # start labels from 1
                cv2.drawContours(labeled_mask, [cnt], -1, i, -1)  # fill the contour
            return labeled_mask

        def ray_scan_labeled(labeled_mask, center, angle_step=1, step_size=1):
            """
            Scan the labeled mask using rays from the center.
            For each ray, record the first contour label encountered.

            Parameters:
            labeled_mask: 2D array where each contour has a unique integer value.
            center: Tuple (x, y) for the center point.
            angle_step: Angular resolution in degrees.
            step_size: Distance to move along each ray per iteration.

            Returns:
            Dictionary mapping contour label to a list of intersection points.
            """
            hits = {}
            height, width = labeled_mask.shape
            for angle in np.arange(0, 360, angle_step):
                rad = np.deg2rad(angle)
                dx = np.cos(rad)
                dy = np.sin(rad)
                x, y = center[0], center[1]

                # Step along the ray until we go out of bounds or hit a contour pixel.
                while 0 <= int(x) < width and 0 <= int(y) < height:
                    label = labeled_mask[int(y), int(x)]
                    if label != 0:  # nonzero means a contour pixel
                        if label not in hits:
                            hits[label] = []
                        hits[label].append((x, y))
                        break
                    x += dx * step_size
                    y += dy * step_size

            return hits

        angle_step = config["angle_step"]
        step_size = config["step_size"]
        center_point = config["center_point"]

        labeled_mask = label_contours(mask.shape, cnts)
        hits = ray_scan_labeled(labeled_mask, center_point, angle_step, step_size)
        hit_contour_ids = list(hits.keys())
        hit_contours = [cnts[label - 1] for label in hit_contour_ids]
        return hit_contours, labeled_mask

    @staticmethod
    def rect_from_cnts(cnts):  # MARK: RECT FROM CONTOURS
        combined_points = np.vstack([cnt.reshape(-1, 2) for cnt in cnts])
        rect = cv2.minAreaRect(combined_points)
        box = cv2.boxPoints(rect).tolist()
        return rect, box

    @staticmethod
    def rect_validation(rect, box, image, config):  # MARK: RECT VALIDATION
        if rect[1][0] > rect[1][1]:
            long = rect[1][0]
            short = rect[1][1]
        else:
            long = rect[1][1]
            short = rect[1][0]
            
        #0. check if box is not too small or too big
        if long < 800 or long > 1050 or short < 500 or short > 800:
            return False

        ratio = long / short
        if ratio > config["box_ratio_range"][1] or ratio < config["box_ratio_range"][0]:
            return False

        # 2. check distance between center of the rect and assumed center of the box
        center_rect = rect[0]
        center_box = config["center_point"]
        distance = math.sqrt((center_rect[0] - center_box[0]) ** 2 + (center_rect[1] - center_box[1]) ** 2)
        if distance > config["max_distance"]:
            return (False,)

        # 3. check box angle
        angle = rect[2]
        if angle == 45:
            return False
        if angle < 45 and angle > config["max_angle"]:
            return False
        if angle > 45 and angle < 90 - config["max_angle"]:
            return False

        # 4. check if box corner is not near the edge of the image
        for corner in box:
            if corner[0] < 0 or corner[0] > image.shape[1] or corner[1] < 0 or corner[1] > image.shape[0]:
                return False

        return True

    @staticmethod
    def prepare_box_output(rect, box, depth_image, config):  # MARK: PREPARE BOX OUTPUT
        center = rect[0]
        angle = rect[2]

        sorted_corners = sorted(box, key=lambda point: (point[0]))
        left = sorted_corners[0:2]
        right = sorted_corners[2:4]
        left_y = sorted(left, key=lambda point: (point[1]))
        right_y = sorted(right, key=lambda point: (point[1]))
        sorted_corners = [left_y[1], right_y[1], right_y[0], left_y[0]]

        z = (
            np.median(
                depth_image[
                    int(center[1]) - config["center_size"] : int(center[1]) + config["center_size"],
                    int(center[0]) - config["center_size"] : int(center[0]) + config["center_size"],
                ]
            )
        ) / 1000
        return center, sorted_corners, angle, z

    @staticmethod
    def remove_edge_contours(contours, image_shape, config):
        """Remove contours that touch the edge of the image within a certain margin"""
        margin = config.get("edge_margin", 5)  # Default margin of 5 pixels from edge
        height, width = image_shape

        filtered_cnts = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            # Check if contour is too close to any edge
            if (
                x > margin  # Not too close to left edge
                and y > margin  # Not too close to top edge
                and x + w < width - margin  # Not too close to right edge
                and y + h < height - margin
            ):  # Not too close to bottom edge
                filtered_cnts.append(cnt)

        return filtered_cnts

    @staticmethod
    def prepare_image_output(image, cnts, rect, box):  # MARK: PREPARE IMAGE OUTPUT
        image_copy = deepcopy(image)
        for cnt in cnts:
            cv2.drawContours(image_copy, [cnt], -1, (0, 255, 0), 2)

        for point in box:
            cv2.circle(image_copy, (int(point[0]), int(point[1])), 10, (0, 0, 255), -1)

        cv2.circle(image_copy, (int(rect[0][0]), int(rect[0][1])), 10, (0, 0, 255), -1)
        box_int = np.intp(box)
        cv2.drawContours(image_copy, [box_int], -1, (0, 255, 0), 2)

        return image_copy

    @staticmethod
    def read_image_from_dataset(path, id):  # MARK: READ IMAGE FROM DATASET
        photo_id = str(id)
        color_image = cv2.imread(os.path.join(path, f"color_photo{photo_id.zfill(3)}.png"))

        with open(os.path.join(path, f"depth_{photo_id.zfill(3)}.pkl"), "rb") as f:
            depth_image = pickle.load(f)

        return color_image, depth_image

    @staticmethod
    def qr_preprocess(image, config):  # MARK: QR PRE-PROCESS
        """
        config = {
            'clahe': {
                'clip_limit': 4.0,
                'grid_size': 8,
            },
            'glare': {
                'threshold': 200,
                'kernel_size': 5,
                'iter': 2
            },
            'border_size': 20,
            'gamma': 3,
            'binarization': {
                'block_size': 31,
                'C': 1
            },
            'morph': {
                'kernel_size': 3,
                'open_iter': 1,
                'close_iter': 3
            },
            'merge': {
                'cropped_weight': 0.7,
                'image_weight': 0.7
            }
        }
        """
        # 1. Turning image gray
        image_grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 2. Applying CLAHE
        image_clahe = cv2.createCLAHE(clipLimit=config["clahe"]["clip_limit"], tileGridSize=(config["clahe"]["grid_size"], config["clahe"]["grid_size"])).apply(image_grey)

        # 3. Glare Mask Create
        glare_mask = Vision.create_glare_mask(image, config["glare"])

        if max(glare_mask.flatten()) <= 0:
            return image_clahe

        # 4. Glare Mask - rectangle - TODO: Make better masks
        cropped_image, crop_size = Vision.glare_mask_crop(image_grey, glare_mask, {"border_size": config["border_size"]})
        x, y, w, h = crop_size
        # 5. Gamma Correction - on cropped image
        # 6. Cropped Image binarization
        # 7. Morph Operations
        process_config = {"gamma": config["gamma"], "binarization": config["binarization"], "morph": config["morph"]}
        binary_image = Vision.crop_image_process(cropped_image, process_config)

        # 8. Image Merger
        cropped_merge_image = cv2.addWeighted(cropped_image, 1 - config["merge"]["cropped_weight"], binary_image, config["merge"]["cropped_weight"], 0)

        image_clahe_copy = image_clahe.copy()
        image_clahe_copy[y : y + h, x : x + w] = cropped_merge_image

        image = cv2.addWeighted(image_clahe_copy, config["merge"]["image_weight"], image_clahe, 1 - config["merge"]["image_weight"], 0)
        return image

    @staticmethod
    def qr_preprocess_b(image, config):
        image_grey = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 2. Applying CLAHE
        image_clahe = cv2.createCLAHE(clipLimit=config["clahe"]["clip_limit"], tileGridSize=(config["clahe"]["grid_size"], config["clahe"]["grid_size"])).apply(image_grey)

        process_config = {"gamma": config["gamma"], "binarization": config["binarization"], "morph": config["morph"]}
        binary_image = Vision.crop_image_process(image_grey, process_config)

        return cv2.addWeighted(binary_image, config["merge"]["image_weight"], image_clahe, 1 - config["merge"]["image_weight"], 0)

    @staticmethod
    def create_glare_mask(image, config):  # MARK: CREATE GLARE MASK
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        _, _, v = cv2.split(hsv)
        glare_mask = cv2.threshold(v, config["threshold"], 255, cv2.THRESH_BINARY)[1]
        glare_mask = cv2.morphologyEx(glare_mask, cv2.MORPH_OPEN, np.ones((config["kernel_size"], config["kernel_size"]), np.uint8), iterations=config["iter"])

        return glare_mask

    @staticmethod
    def glare_mask_crop(image, glare_mask, config):
        x, y, w, h = cv2.boundingRect(glare_mask)
        glare_mask = cv2.rectangle(
            image.copy(), (x - config["border_size"], y - config["border_size"]), (x + w + config["border_size"], y + h + config["border_size"]), (0, 0, 255), 2
        )

        y = max(y - config["border_size"], 0)
        x = max(x - config["border_size"], 0)
        h = min(h + 2 * config["border_size"], image.shape[0] - y)
        w = min(w + 2 * config["border_size"], image.shape[1] - x)

        cropped_image = image[y : y + h, x : x + w]
        return cropped_image, [x, y, w, h]

    @staticmethod
    def crop_image_process(image, config):
        image = np.power(image / 255.0, config["gamma"]) * 255.0
        image = image.astype(np.uint8)

        # 6. Cropped Image binarization
        binary_image = cv2.adaptiveThreshold(
            image,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,  # or cv2.ADAPTIVE_THRESH_MEAN_C
            cv2.THRESH_BINARY,
            config["binarization"]["block_size"],  # blockSize (odd number)
            config["binarization"]["C"],  # C (constant subtracted from the mean)
        )

        # 7. Morph Operations
        binary_image = cv2.bitwise_not(binary_image)

        kernel = np.ones((config["morph"]["kernel_size"], config["morph"]["kernel_size"]), np.uint8)
        binary_image = cv2.morphologyEx(binary_image, cv2.MORPH_OPEN, kernel, iterations=config["morph"]["open_iter"])
        binary_image = cv2.morphologyEx(binary_image, cv2.MORPH_CLOSE, kernel, iterations=config["morph"]["close_iter"])

        binary_image = cv2.bitwise_not(binary_image)

        return binary_image
    
    #MARK: PROPAGATE EMPTY DEPTH
    @staticmethod
    def fix_depth_img(depth_image, config, debug: bool = False):
        """
        Example config:
        fix_depth_config = {
            "closing_mask": {
                "kernel_size": 10,
                "iterations": 2,
            },
            "zero_mask": {
                "kernel_size": 10,
                "iterations": 2,
            },
            "r_wide": 2.0,
            "r_tall": 0.5,
            "final_closing_mask": {
                "kernel_size": 10,
                "iterations": 2,
            },
        }
        """
        
        debug_dict = {}
        
        #STEP 1: CLOSE DEPTH IMAGE
        kernel = np.ones((config["closing_mask"]["kernel_size"], config["closing_mask"]["kernel_size"]), np.uint8)
        closed_depth_image = cv2.morphologyEx(depth_image, cv2.MORPH_CLOSE, kernel, iterations=config["closing_mask"]["iterations"])
        
        if debug:
            debug_dict["closed_depth_image"] = closed_depth_image
        
        #STEP 2: CREATE ZERO DEPTH MASK
        zero_depth_mask = closed_depth_image == 0
        zero_depth_mask = zero_depth_mask.astype(np.uint8) * 255
        kernel = np.ones((config["zero_mask"]["kernel_size"], config["zero_mask"]["kernel_size"]), np.uint8)
        closed_zero_mask = cv2.morphologyEx(zero_depth_mask, cv2.MORPH_CLOSE, kernel, iterations=config["zero_mask"]["iterations"])
        
        if debug:
            debug_dict["zero_depth_mask"] = zero_depth_mask
            debug_dict["closed_zero_mask"] = closed_zero_mask
        
        #STEP 3: SPLIT ZERO DEPTH NASJ
        zero_depth_mask_list = []
        n, labels = cv2.connectedComponents(closed_zero_mask, connectivity=8)
        for i in range(1, n):
            mask = np.zeros_like(closed_zero_mask)
            mask[labels == i] = 255
            zero_depth_mask_list.append(mask)
            
        if debug:
            debug_dict["zero_depth_mask_list"] = zero_depth_mask_list
            
            
        #STEP 4: PROPAGATE ZERO DEPTH MASK
        inpainted_depth_list = []
        for mask in zero_depth_mask_list:
            inpainted_depth = Vision._propagate_by_shape(closed_depth_image, mask, config["r_wide"], config["r_tall"])
            inpainted_depth_list.append(inpainted_depth)
        if debug:
            debug_dict["inpainted_depth_list"] = inpainted_depth_list
            
        #STEP 5: MERGE INPAINTED DEPTH
        depth_merged = Vision._merge_depth_lists(closed_depth_image, inpainted_depth_list, zero_depth_mask_list)
        kernel = np.ones((config["final_closing_mask"]["kernel_size"], config["final_closing_mask"]["kernel_size"]), np.uint8)
        depth_merged_closed = cv2.morphologyEx(depth_merged, cv2.MORPH_CLOSE, kernel, iterations=config["final_closing_mask"]["iterations"])
                
        return depth_merged_closed, debug_dict
    
    
    @staticmethod
    def _merge_depth_lists(original_depth, painted_layers, masks=None):
   
        merged = original_depth.astype(np.float32).copy()

        # normalise inputs to lists so we can loop uniformly
        if not isinstance(painted_layers, (list, tuple)):
            painted_layers = [painted_layers]

        if masks is None:
            masks = [None] * len(painted_layers)
        elif not isinstance(masks, (list, tuple)):
            masks = [masks] * len(painted_layers)

        if len(masks) != len(painted_layers):
            raise ValueError("`masks` must be None, a single array, "
                            "or a list the same length as `painted_layers`")

        # ------------------------------------------------------------
        for layer, mask in zip(painted_layers, masks):
            if mask is None:
                sel = layer != 0               # write wherever layer has data
            else:
                sel = mask == 255              # obey supplied mask

            merged[sel] = layer[sel]

        return merged
    
    @staticmethod
    def _propagate_by_shape(depth, mask, r_wide=2.0, r_tall=0.5):
        ys, xs = np.where(mask)
        
        h = ys.max() - ys.min() + 1
        w = xs.max() - xs.min() + 1
        ratio = w / h
        
        if   ratio > r_wide: direction = "horizontal"
        elif ratio < r_tall: direction = "vertical"
        else:                direction = "square"
        
        return Vision._propagate(depth, mask, direction)
        
    @staticmethod
    def _propagate(depth, mask, direction):
        def propagate_logic(depth: np.ndarray,
                    mask:  np.ndarray,
                    direction: str = "left") -> np.ndarray:
            if direction not in {"left", "right", "up", "down"}:
                raise ValueError("direction must be 'left', 'right', 'up', or 'down'")

            h, w        = depth.shape
            painted     = np.zeros_like(depth, dtype=np.float32)
            holes_equal = (mask == 255)        # pre-compute for speed

            if direction in {"left", "right"}:
                for y in range(h):
                    if not holes_equal[y].any():
                        continue  # no hole in this row

                    row = depth[y]
                    if direction == "left":
                        # first hole from the left → walk left
                        start_x = np.argmax(holes_equal[y])
                        search_range = range(start_x - 1, -1, -1)    # ←
                    else:  # "right"
                        # first hole from the right → walk right
                        start_x = w - 1 - np.argmax(holes_equal[y][::-1])
                        search_range = range(start_x + 1, w)         # →

                    # find first valid depth along search_range
                    val = next(
                        (row[x] for x in search_range
                        if (row[x] != 0) and (not np.isnan(row[x]))),
                        np.nan
                    )
                    if not np.isnan(val):
                        painted[y, holes_equal[y]] = val

            else:  # "up" or "down"
                for x in range(w):
                    col_mask = holes_equal[:, x]
                    if not col_mask.any():
                        continue  # no hole in this column

                    col = depth[:, x]
                    if direction == "up":
                        # first hole from the top → walk up
                        start_y = np.argmax(col_mask)
                        search_range = range(start_y - 1, -1, -1)    # ↑
                    else:  # "down"
                        # first hole from the bottom → walk down
                        start_y = h - 1 - np.argmax(col_mask[::-1])
                        search_range = range(start_y + 1, h)         # ↓

                    val = next(
                        (col[y] for y in search_range
                        if (col[y] != 0) and (not np.isnan(col[y]))),
                        np.nan
                    )
                    if not np.isnan(val):
                        painted[col_mask, x] = val

            return painted
                
        
        if direction == "horizontal":
            left_propagation = propagate_logic(depth, mask, "left")
            right_propagation = propagate_logic(depth, mask, "right")
            
            return (left_propagation + right_propagation) / 2
        elif direction == "vertical":
            top_propagation = propagate_logic(depth, mask, "up")
            bottom_propagation = propagate_logic(depth, mask, "down")
            return (top_propagation + bottom_propagation) / 2
        elif direction == "square":
            left_propagation = propagate_logic(depth, mask, "left")
            right_propagation = propagate_logic(depth, mask, "right")
            top_propagation = propagate_logic(depth, mask, "up")
            bottom_propagation = propagate_logic(depth, mask, "down")
            return ((left_propagation + right_propagation)/2 + (top_propagation + bottom_propagation)/2)/2
        else:
            raise ValueError("direction must be horizontal / vertical / square")
