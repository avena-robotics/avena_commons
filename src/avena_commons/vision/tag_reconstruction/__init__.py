"""
Pakiet do rekonstrukcji i przetwarzania tagów wizyjnych w obrazach.

Zasady działania pakietu:
-----------------------
Pakiet implementuje kompletny system do analizy, rekonstrukcji i przetwarzania
tagów wizyjnych (QR, AR) z obrazów z wykorzystaniem zaawansowanych technik
przetwarzania obrazu i analizy geometrycznej.

Główne komponenty:
-----------------
1. **Analiza geometryczna**: Obliczanie cech geometrycznych, walidacja konstelacji
2. **Wykrywanie konturów**: Znajdowanie, filtrowanie i grupowanie konturów
3. **Segmentacja ROI**: Podział obrazu na regiony zainteresowania
4. **Transformacje**: Mapowanie perspektywiczne i kanonizacja tagów
5. **Integracja**: Łączenie przetworzonych regionów w końcowy obraz

Pipeline przetwarzania:
----------------------
1. Preprocessing obrazu i wykrywanie konturów
2. Filtrowanie i grupowanie konturów referencyjnych
3. Podział obrazu na ROI z konfigurowalnymi parametrami
4. Mapowanie tagów referencyjnych na ROI z uwzględnieniem perspektywy
5. Walidacja geometryczna i rekonstrukcja
6. Łączenie ROI w końcowy obraz

Zastosowania:
------------
- Rekonstrukcja tagów QR/AR z obrazów zniekształconych perspektywą
- Poprawa jakości tagów wizyjnych dla lepszego dekodowania
- Przetwarzanie obrazów z kamer przemysłowych i robotycznych
- Analiza wzorców geometrycznych w wizji komputerowej
- Walidacja poprawności wykrytych elementów wizyjnych

Autor: Avena Commons Team
"""

from .calculate_geometric_features import calculate_geometric_features
from .canonicalise import canonicalise
from .check_geometric_constellation import check_geometric_constellation
from .create_reference_tag_shapes import create_reference_tag_shapes
from .divide_image_into_roi import divide_image_into_roi
from .divide_image_into_rois import divide_image_into_rois
from .filter_reference_contours import filter_reference_contours
from .find_contours import find_contours
from .find_scenes_contours import find_scenes_contours
from .find_similar_contours import find_similar_contours
from .find_valid_contour_groups import find_valid_contour_groups
from .get_contour_centroid import get_contour_centroid
from .list_of_contours_per_type import list_of_contours_per_type
from .merge_rois_into_image import merge_rois_into_image
from .preprocess_for_contours import preprocess_for_contours
from .reconstruct_tags import reconstruct_tags
from .wrap_tag_to_roi import wrap_tag_to_roi

__all__ = [
    "canonicalise",
    "calculate_geometric_features",
    "check_geometric_constellation",
    "create_reference_tag_shapes",
    "divide_image_into_roi",
    "divide_image_into_rois",
    "filter_reference_contours",
    "find_contours",
    "find_scenes_contours",
    "find_similar_contours",
    "find_valid_contour_groups",
    "get_contour_centroid",
    "merge_rois_into_image",
    "preprocess_for_contours",
    "reconstruct_tags",
    "wrap_tag_to_roi",
    "list_of_contours_per_type",
]
