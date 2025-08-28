import cv2


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
