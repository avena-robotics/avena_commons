import numpy as np


def propagate(depth, mask, direction):
    def propagate_logic(
        depth: np.ndarray, mask: np.ndarray, direction: str = "left"
    ) -> np.ndarray:
        if direction not in {"left", "right", "up", "down"}:
            raise ValueError("direction must be 'left', 'right', 'up', or 'down'")

        h, w = depth.shape
        painted = np.zeros_like(depth, dtype=np.float32)
        holes_equal = mask == 255  # pre-compute for speed

        if direction in {"left", "right"}:
            for y in range(h):
                if not holes_equal[y].any():
                    continue  # no hole in this row

                row = depth[y]
                if direction == "left":
                    # first hole from the left → walk left
                    start_x = np.argmax(holes_equal[y])
                    search_range = range(start_x - 1, -1, -1)  # ←
                else:  # "right"
                    # first hole from the right → walk right
                    start_x = w - 1 - np.argmax(holes_equal[y][::-1])
                    search_range = range(start_x + 1, w)  # →

                # find first valid depth along search_range
                val = next(
                    (
                        row[x]
                        for x in search_range
                        if (row[x] != 0) and (not np.isnan(row[x]))
                    ),
                    np.nan,
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
                    search_range = range(start_y - 1, -1, -1)  # ↑
                else:  # "down"
                    # first hole from the bottom → walk down
                    start_y = h - 1 - np.argmax(col_mask[::-1])
                    search_range = range(start_y + 1, h)  # ↓

                val = next(
                    (
                        col[y]
                        for y in search_range
                        if (col[y] != 0) and (not np.isnan(col[y]))
                    ),
                    np.nan,
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
        return (
            (left_propagation + right_propagation) / 2
            + (top_propagation + bottom_propagation) / 2
        ) / 2
    else:
        raise ValueError("direction must be horizontal / vertical / square")
