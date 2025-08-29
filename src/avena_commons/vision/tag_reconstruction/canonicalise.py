"""
Moduł do kanonizacji konturów wizyjnych.

Zasady działania:
--------------
Moduł implementuje algorytm kanonizacji konturów, który zapewnia
spójną reprezentację geometryczną poprzez resampling, normalizację
kierunku i standaryzację punktu startowego.

Algorytm kanonizacji:
--------------------
1. **Resampling**: Próbkowanie konturu na N równomiernie rozłożonych punktów
2. **Normalizacja kierunku**: Upewnienie się, że kontur jest zgodny z ruchem wskazówek zegara
3. **Standaryzacja startu**: Ustawienie punktu startowego na określonym narożniku
4. **Spójność**: Zapewnienie deterministycznej reprezentacji konturu

Zastosowania:
- Standaryzacja konturów przed porównaniem geometrycznym
- Przygotowanie konturów do transformacji afinowych
- Zapewnienie spójności w algorytmach mapowania perspektywicznego
- Normalizacja danych wejściowych dla algorytmów wizyjnych
"""

import cv2
import numpy as np


def canonicalise(cnt, N=180, *, corner="TL"):
    """
    Kanonizuje kontur poprzez resampling, normalizację kierunku i standaryzację punktu startowego.

    Funkcja implementuje algorytm kanonizacji konturów, który zapewnia
    spójną reprezentację geometryczną poprzez trzy kluczowe kroki:
    resampling na N punktów, normalizację kierunku (zgodnie z ruchem
    wskazówek zegara) i ustawienie punktu startowego na określonym narożniku.

    Zasada działania:
    ----------------
    1. **Resampling**: Próbkowanie konturu na N równomiernie rozłożonych punktów
    2. **Normalizacja kierunku**: Upewnienie się, że kontur jest zgodny z ruchem wskazówek zegara
    3. **Standaryzacja startu**: Ustawienie punktu startowego na określonym narożniku
    4. **Spójność**: Zapewnienie deterministycznej reprezentacji konturu

    Parametry:
    ----------
    cnt : (M,1,2) or (M,2) array
        Kontur wejściowy w formacie OpenCV (M punktów z 2 współrzędnymi)

    N : int, default=180
        Liczba punktów po resamplingu (domyślnie 180 dla wysokiej precyzji)

    corner : {"TL","TR","BL","BR"}, default="TL"
        Narożnik używany jako punkt startowy:
        - TL = top-left (min x, potem min y)
        - TR = top-right (max x, potem min y)
        - BL = bottom-left (min x, potem max y)
        - BR = bottom-right (max x, potem max y)

    Zwraca:
    -------
    np.ndarray
        Kanonizowany kontur z N punktami, zgodny z ruchem wskazówek zegara,
        z punktem startowym na określonym narożniku

    Przykład:
    ---------
    >>> contour = np.array([[[100, 100]], [[200, 100]], [[150, 200]]])
    >>> canonical_contour = canonicalise(contour, N=90, corner="TL")
    >>> print(f"Kanonizowany kontur: {canonical_contour.shape}")

    Uwagi:
    ------
    - Kontur musi być zamknięty (pierwszy i ostatni punkt są identyczne)
    - Resampling zapewnia równomierne rozłożenie punktów
    - Kierunek jest normalizowany do zgodnego z ruchem wskazówek zegara
    - Punkt startowy jest deterministycznie wybierany na podstawie narożnika
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
