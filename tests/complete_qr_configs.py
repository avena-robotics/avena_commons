# Kompletne konfiguracje QR (a-i) do skopiowania do testów

qr_configs_complete = [
    {
        "qr_size": 0.026,
        "mode": "gray",
        "clahe": {"clip_limit": 4.0, "grid_size": 8},
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    },
    {
        "qr_size": 0.026,
        "mode": "gray_with_binarization",
        "clahe": {"clip_limit": 4.0, "grid_size": 8},
        "binarization": {
            "gamma": 3,
            "binarization": {"block_size": 31, "C": 1},
            "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
        },
        "merge_image_weight": 0.7,
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    },
    {
        "qr_size": 0.026,
        "mode": "gray",
        "clahe": {"clip_limit": 1.0, "grid_size": 1},
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    },
    {
        "qr_size": 0.026,
        "mode": "gray_with_binarization",
        "clahe": {"clip_limit": 1.0, "grid_size": 1},
        "binarization": {
            "gamma": 3,
            "binarization": {"block_size": 31, "C": 1},
            "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
        },
        "merge_image_weight": 0.7,
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    },
    {
        "qr_size": 0.026,
        "mode": "saturation",
        "clahe": {"clip_limit": 4.0, "grid_size": 8},
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    },
    {
        "qr_size": 0.026,
        "mode": "saturation_with_binarization",
        "clahe": {"clip_limit": 4.0, "grid_size": 8},
        "binarization": {
            "gamma": 3,
            "binarization": {"block_size": 31, "C": 1},
            "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
        },
        "merge_image_weight": 0.7,
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    },
    {
        "qr_size": 0.026,
        "mode": "saturation",
        "clahe": {"clip_limit": 1.0, "grid_size": 1},
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    },
    {
        "qr_size": 0.026,
        "mode": "saturation_with_binarization",
        "clahe": {"clip_limit": 1.0, "grid_size": 1},
        "binarization": {
            "gamma": 3,
            "binarization": {"block_size": 31, "C": 1},
            "morph": {"kernel_size": 3, "open_iter": 1, "close_iter": 3},
        },
        "merge_image_weight": 0.7,
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    },
    {
        "qr_size": 0.026,
        "mode": "tag_reconstruction",
        "tag_reconstruction": {
            "roi_config": {
                "horizontal_slice": (0.33, 0.66),
                "vertical_slice": (0.0, 1.0),
                "overlap_fraction": 0.2,
            },
            "scene_corners": ["BL", "TR", "BL", "TR"],
            "central": False,
        },
        "middle_area": {"min_x": 0.56, "max_x": 1.44},
    },
]

# Mapowanie nazw konfiguracji
config_names = {
    0: "config_a (gray, clahe 4.0/8)",
    1: "config_b (gray_with_binarization, clahe 4.0/8)",
    2: "config_c (gray, clahe 1.0/1)",
    3: "config_d (gray_with_binarization, clahe 1.0/1)",
    4: "config_e (saturation, clahe 4.0/8)",
    5: "config_f (saturation_with_binarization, clahe 4.0/8)",
    6: "config_g (saturation, clahe 1.0/1)",
    7: "config_h (saturation_with_binarization, clahe 1.0/1)",
    8: "config_i (tag_reconstruction)",
}

print("Kompletne konfiguracje QR (9 konfiguracji):")
for i, (config, name) in enumerate(zip(qr_configs_complete, config_names.values())):
    print(f"{i}: {name}")
    print(f"   mode: {config['mode']}")
    if "clahe" in config:
        print(f"   clahe: {config['clahe']}")
    if "binarization" in config:
        print(
            f"   binarization: {config.get('binarization', {}).get('binarization', {})}"
        )
    if "tag_reconstruction" in config:
        print(f"   tag_reconstruction: {config['tag_reconstruction']}")
    print()
