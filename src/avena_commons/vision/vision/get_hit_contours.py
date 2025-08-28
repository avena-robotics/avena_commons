import cv2
import numpy as np


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
