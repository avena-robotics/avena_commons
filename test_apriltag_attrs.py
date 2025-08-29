#!/usr/bin/env python3
"""Test atrybutów obiektu AprilTag Detection."""

import numpy as np
from pupil_apriltags import Detector


def test_detection_attributes():
    """Sprawdza atrybuty obiektu Detection."""
    d = Detector()

    # Stwórz przykładowy obraz testowy
    img = np.random.randint(0, 255, (200, 200), dtype=np.uint8)

    print("=== TESTING APRILTAG DETECTION ===")
    print(f"Image shape: {img.shape}")

    # Wywołaj detect
    result = d.detect(img)
    print(f"Detection count: {len(result)}")

    if result:
        detection = result[0]
        print(f"\nFirst detection type: {type(detection)}")
        print(
            f"Detection attributes: {[attr for attr in dir(detection) if not attr.startswith('_')]}"
        )

        # Sprawdź konkretne atrybuty
        print(f"\n=== DETECTION DETAILS ===")
        print(f"ID: {detection.id}")
        print(f"Center: {detection.center}")
        print(f"Corners: {detection.corners}")

        # Sprawdź czy są inne atrybuty związane z pewnością
        if hasattr(detection, "decision_margin"):
            print(f"Decision margin: {detection.decision_margin}")
        if hasattr(detection, "hamming"):
            print(f"Hamming: {detection.hamming}")
        if hasattr(detection, "goodness"):
            print(f"Goodness: {detection.goodness}")
        if hasattr(detection, "homography"):
            print(f"Homography: {detection.homography}")

        print(f"\nFull detection object: {detection}")
    else:
        print("No detections found in test image")


if __name__ == "__main__":
    test_detection_attributes()
