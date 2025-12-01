#!/usr/bin/env python3
"""
Skrypt kalibracji kamery Orbec Gemini 335LE - wersja bez GUI

Automatycznie zapisuje obrazy do kalibracji bez wyświetlania okna.
Używa automatycznego wykrywania wzorca lub ręcznego trybu czasowego.

Autor: AI Assistant
Data: 2025-09-23
"""

import json
import os
import time
from datetime import datetime
from typing import Optional, Tuple

import cv2
import numpy as np
import pyorbbecsdk as ob


class CameraCalibratorNoGUI:
    """Klasa do kalibracji kamery Orbec Gemini 335LE bez GUI."""

    def __init__(
        self,
        chessboard_size: Tuple[int, int] = (9, 6),
        square_size: float = 25.0,  # mm
        camera_ip: str = "192.168.1.10",
    ):
        """Inicjalizuje kalibrator kamery.

        Args:
            chessboard_size: Rozmiar wzorca szachownicy (szerokość, wysokość) w naroznikach wewnętrznych
            square_size: Rozmiar kwadratu szachownicy w mm
            camera_ip: Adres IP kamery Orbec
        """
        self.chessboard_size = chessboard_size
        self.square_size = square_size
        self.camera_ip = camera_ip

        # Przygotowanie punktów wzorca 3D
        self.pattern_points = self._prepare_pattern_points()

        # Listy do przechowywania punktów
        self.object_points = []  # Punkty 3D w przestrzeni świata
        self.image_points = []  # Punkty 2D w przestrzeni obrazu
        self.images = []  # Przechowywane obrazy

        # Parametry kamery
        self.camera_matrix = None
        self.distortion_coeffs = None
        self.image_size = None
        self.calibration_rms = None  # Prawdziwy błąd RMS z kalibracji
        self.rvecs = None  # Wektory rotacji z kalibracji
        self.tvecs = None  # Wektory translacji z kalibracji

        # Pipeline Orbec
        self.pipeline = None
        self.config = None

        # Katalog na zdjęcia
        self.output_dir = (
            f"calibration_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def _prepare_pattern_points(self) -> np.ndarray:
        """Przygotowuje punkty wzorca 3D."""
        pattern_points = np.zeros(
            (self.chessboard_size[0] * self.chessboard_size[1], 3), np.float32
        )
        pattern_points[:, :2] = np.mgrid[
            0 : self.chessboard_size[0], 0 : self.chessboard_size[1]
        ].T.reshape(-1, 2)
        pattern_points *= self.square_size
        return pattern_points

    def init_camera(self) -> bool:
        """Inicjalizuje kamerę Orbec.

        Returns:
            bool: True jeśli inicjalizacja się powiodła
        """
        try:
            # Inicjalizacja kontekstu Orbec
            ctx = ob.Context()
            device_list = ctx.query_devices()

            if device_list.get_count() == 0:
                print("BŁĄD: Nie znaleziono urządzeń Orbec")
                return False

            # Wybierz pierwsze urządzenie
            device = device_list.get_device_by_index(0)

            # Stwórz pipeline
            self.pipeline = ob.Pipeline(device)
            self.config = ob.Config()

            # Konfiguracja strumienia kolorowego
            color_profiles = self.pipeline.get_stream_profile_list(
                ob.OBSensorType.COLOR_SENSOR
            )
            if color_profiles.get_count() > 0:
                # Szukaj profilu RGB/BGR o wysokiej rozdzielczości
                color_profile = None
                for i in range(color_profiles.get_count()):
                    try:
                        profile = color_profiles.get_stream_profile_by_index(i)
                        video_profile = profile.as_video_stream_profile()
                        if (
                            video_profile
                            and video_profile.get_format()
                            in [ob.OBFormat.RGB, ob.OBFormat.BGR]
                            and video_profile.get_width() >= 1280
                        ):
                            color_profile = video_profile
                            print(
                                f"✓ Używam profilu: {video_profile.get_width()}x{video_profile.get_height()}, {video_profile.get_format()}"
                            )
                            break
                    except:
                        continue

                # Jeśli nie znaleziono RGB/BGR, użyj domyślnego
                if color_profile is None:
                    color_profile = color_profiles.get_default_video_stream_profile()
                    print(
                        f"⚠ Używam domyślnego profilu: {color_profile.get_width()}x{color_profile.get_height()}, {color_profile.get_format()}"
                    )

                self.config.enable_stream(color_profile)

            # Uruchom pipeline
            self.pipeline.start(self.config)

            print(f"✓ Kamera Orbec zainicjalizowana pomyślnie")
            return True

        except Exception as e:
            print(f"BŁĄD inicjalizacji kamery: {e}")
            return False

    def capture_frame(self) -> Optional[np.ndarray]:
        """Przechwytuje ramkę z kamery.

        Returns:
            Optional[np.ndarray]: Obraz kolorowy lub None w przypadku błędu
        """
        try:
            # Pobierz ramkę
            frames = self.pipeline.wait_for_frames(100)
            if frames is None:
                return None

            color_frame = frames.get_color_frame()
            if color_frame is None:
                return None

            # Uzyskaj właściwości ramki
            width = color_frame.get_width()
            height = color_frame.get_height()
            format_type = color_frame.get_format()

            # Konwertuj do numpy array
            color_data = np.frombuffer(color_frame.get_data(), dtype=np.uint8)

            # Obsługa różnych formatów
            if format_type == ob.OBFormat.RGB:
                color_image = color_data.reshape(height, width, 3)
                # Konwertuj z RGB do BGR (OpenCV format)
                color_image = cv2.cvtColor(color_image, cv2.COLOR_RGB2BGR)
            elif format_type == ob.OBFormat.BGR:
                color_image = color_data.reshape(height, width, 3)
                # BGR już jest w formacie OpenCV
            elif format_type == ob.OBFormat.MJPG:
                # Dekompresja MJPG
                color_image = cv2.imdecode(color_data, cv2.IMREAD_COLOR)
                if color_image is None:
                    return None
            else:
                print(f"BŁĄD: Nieobsługiwany format: {format_type}")
                return None

            if self.image_size is None:
                self.image_size = (color_image.shape[1], color_image.shape[0])
                print(f"✓ Rozmiar obrazu: {self.image_size[0]}x{self.image_size[1]}")

            return color_image

        except Exception as e:
            print(f"BŁĄD przechwytywania ramki: {e}")
            return None

    def find_chessboard_corners(
        self, image: np.ndarray
    ) -> Tuple[bool, Optional[np.ndarray]]:
        """Znajduje narożniki szachownicy na obrazie.

        Args:
            image: Obraz wejściowy

        Returns:
            Tuple[bool, Optional[np.ndarray]]: (sukces, narożniki)
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Znajdź narożniki szachownicy
        ret, corners = cv2.findChessboardCorners(gray, self.chessboard_size, None)

        if ret:
            # Popraw dokładność narożników
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

        return ret, corners if ret else None

    def collect_calibration_images_auto(
        self, min_images: int = 20, interval_sec: float = 2.0
    ) -> bool:
        """Automatycznie zbiera obrazy do kalibracji.

        Args:
            min_images: Minimalna liczba obrazów wymagana do kalibracji
            interval_sec: Odstęp czasowy między zdjęciami w sekundach

        Returns:
            bool: True jeśli zebrano wystarczającą liczbę obrazów
        """
        print(f"\n🎯 Rozpoczynam automatyczne zbieranie obrazów kalibracyjnych")
        print(f"📋 Instrukcje:")
        print(
            f"   • Umieść wzorzec szachownicy {self.chessboard_size[0]}x{self.chessboard_size[1]} przed kamerą"
        )
        print(f"   • Rozmiar kwadratu: {self.square_size}mm")
        print(f"   • Będę robił zdjęcie co {interval_sec} sekundy")
        print(f"   • Potrzebuję minimum {min_images} dobrych obrazów")
        print(f"   • Naciśnij Ctrl+C aby zakończyć przedwcześnie")
        print(f"   • Poruszaj wzorcem w różnych pozycjach i kątach")
        print(f"   • Obrazy zapisywane w: {self.output_dir}")

        successful_captures = 0
        last_capture_time = 0

        try:
            while successful_captures < min_images:
                current_time = time.time()

                # Przechwycenie ramki
                image = self.capture_frame()
                if image is None:
                    time.sleep(0.1)
                    continue

                # Sprawdź czy można znaleźć narożniki
                ret, corners = self.find_chessboard_corners(image)

                # Sprawdź czy minął odpowiedni czas
                if current_time - last_capture_time >= interval_sec:
                    # Zapisz obraz do sprawdzenia (nawet bez narożników)
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    raw_filename = os.path.join(
                        self.output_dir,
                        f"raw_img_{successful_captures + 1:02d}_{timestamp}.jpg",
                    )
                    cv2.imwrite(raw_filename, image)

                    if ret:
                        # Narysuj narożniki na obrazie
                        corners_image = image.copy()
                        cv2.drawChessboardCorners(
                            corners_image, self.chessboard_size, corners, ret
                        )

                        # Zapisz obraz z narożnikami
                        corners_filename = os.path.join(
                            self.output_dir,
                            f"corners_img_{successful_captures + 1:02d}_{timestamp}.jpg",
                        )
                        cv2.imwrite(corners_filename, corners_image)

                        # Zapisz punkty
                        self.object_points.append(self.pattern_points)
                        self.image_points.append(corners)
                        self.images.append(image)
                        successful_captures += 1

                        print(
                            f"✓ Obraz {successful_captures}/{min_images} zapisany: {corners_filename}"
                        )
                        last_capture_time = current_time

                    else:
                        print(
                            f"⚠ Obraz {successful_captures + 1} - nie znaleziono narożników: {raw_filename}"
                        )
                        last_capture_time = current_time

                # Krótka pauza
                time.sleep(0.1)

        except KeyboardInterrupt:
            print(f"\n⚠️  Zbieranie obrazów przerwane przez użytkownika")

        print(
            f"\n📊 Zebrano {successful_captures} obrazów kalibracyjnych z wykrytymi narożnikami"
        )
        return successful_captures >= min_images

    def collect_calibration_images_manual(self, min_images: int = 20) -> bool:
        """Ręcznie zbiera obrazy do kalibracji.

        Args:
            min_images: Minimalna liczba obrazów wymagana do kalibracji

        Returns:
            bool: True jeśli zebrano wystarczającą liczbę obrazów
        """
        print(f"\n🎯 Rozpoczynam ręczne zbieranie obrazów kalibracyjnych")
        print(f"📋 Instrukcje:")
        print(
            f"   • Umieść wzorzec szachownicy {self.chessboard_size[0]}x{self.chessboard_size[1]} przed kamerą"
        )
        print(f"   • Rozmiar kwadratu: {self.square_size}mm")
        print(f"   • Naciśnij ENTER aby wykonać zdjęcie")
        print(f"   • Potrzebuję minimum {min_images} dobrych obrazów")
        print(f"   • Wpisz 'q' aby zakończyć")
        print(f"   • Poruszaj wzorcem w różnych pozycjach i kątach")
        print(f"   • Obrazy zapisywane w: {self.output_dir}")

        successful_captures = 0

        try:
            while successful_captures < min_images:
                # Przechwycenie ramki
                image = self.capture_frame()
                if image is None:
                    time.sleep(0.1)
                    continue

                # Sprawdź czy można znaleźć narożniki
                ret, corners = self.find_chessboard_corners(image)

                # Pokaż status
                if ret:
                    print(
                        f"✓ Wykryto narożniki szachownicy - gotowy do zdjęcia {successful_captures + 1}/{min_images}"
                    )
                else:
                    print(f"⚠ Brak narożników - dostosuj pozycję wzorca")

                # Czekaj na input użytkownika
                user_input = input(
                    "Naciśnij ENTER aby wykonać zdjęcie (lub 'q' aby zakończyć): "
                ).strip()

                if user_input.lower() == "q":
                    break

                # Zapisz obraz
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                raw_filename = os.path.join(
                    self.output_dir,
                    f"raw_img_{successful_captures + 1:02d}_{timestamp}.jpg",
                )
                cv2.imwrite(raw_filename, image)

                if ret:
                    # Narysuj narożniki na obrazie
                    corners_image = image.copy()
                    cv2.drawChessboardCorners(
                        corners_image, self.chessboard_size, corners, ret
                    )

                    # Zapisz obraz z narożnikami
                    corners_filename = os.path.join(
                        self.output_dir,
                        f"corners_img_{successful_captures + 1:02d}_{timestamp}.jpg",
                    )
                    cv2.imwrite(corners_filename, corners_image)

                    # Zapisz punkty
                    self.object_points.append(self.pattern_points)
                    self.image_points.append(corners)
                    self.images.append(image)
                    successful_captures += 1

                    print(f"✓ Obraz {successful_captures} zapisany: {corners_filename}")

                else:
                    print(f"⚠ Obraz zapisany ale bez narożników: {raw_filename}")

        except KeyboardInterrupt:
            print(f"\n⚠️  Zbieranie obrazów przerwane przez użytkownika")

        print(
            f"\n📊 Zebrano {successful_captures} obrazów kalibracyjnych z wykrytymi narożnikami"
        )
        return successful_captures >= min_images

    def calibrate_camera(self) -> bool:
        """Wykonuje kalibrację kamery.

        Returns:
            bool: True jeśli kalibracja się powiodła
        """
        if len(self.object_points) < 10:
            print("BŁĄD: Za mało obrazów do kalibracji (minimum 10)")
            return False

        print(f"\n🔧 Rozpoczynam kalibrację kamery...")
        print(f"📊 Używam {len(self.object_points)} obrazów")

        try:
            # Wykonaj kalibrację bez CALIB_FIX_ASPECT_RATIO dla lepszej jakości
            ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
                self.object_points,
                self.image_points,
                self.image_size,
                None,
                None,
                flags=cv2.CALIB_RATIONAL_MODEL,  # Lepszy model zniekształceń
            )

            if ret and ret < 5.0:  # Sprawdź czy błąd RMS jest rozsądny
                self.camera_matrix = camera_matrix
                self.distortion_coeffs = dist_coeffs
                self.calibration_rms = ret  # Zapisz prawdziwy błąd RMS
                self.rvecs = rvecs  # Zapisz wektory rotacji
                self.tvecs = tvecs  # Zapisz wektory translacji

                print(f"✓ Kalibracja zakończona pomyślnie!")
                print(f"📏 Błąd reprojekcji RMS: {ret:.4f} pikseli")

                # Dodatkowe sprawdzenie jakości
                if ret > 2.0:
                    print(
                        f"⚠️  UWAGA: Wysoki błąd RMS ({ret:.4f}). Rozważ powtórzenie kalibracji."
                    )
                elif ret > 1.0:
                    print(
                        f"⚠️  Błąd RMS ({ret:.4f}) jest akceptowalny ale może być lepszy."
                    )
                else:
                    print(f"✓ Doskonała jakość kalibracji! (RMS: {ret:.4f})")

                return True
            else:
                print(f"✗ Kalibracja nieudana - błąd RMS za wysoki: {ret:.4f}")
                return False

        except Exception as e:
            print(f"BŁĄD podczas kalibracji: {e}")
            return False

    def evaluate_calibration(self) -> float:
        """Ocenia jakość kalibracji używając rzeczywistych wektorów rotacji i translacji.

        Returns:
            float: Średni błąd reprojekcji w pikselach
        """
        if self.camera_matrix is None or self.rvecs is None or self.tvecs is None:
            # Zwróć prawdziwy błąd RMS z kalibracji jeśli dostępny
            return (
                self.calibration_rms
                if self.calibration_rms is not None
                else float("inf")
            )

        total_error = 0
        total_points = 0

        for i in range(len(self.object_points)):
            # POPRAWKA: Użyj rzeczywistych wektorów rotacji i translacji z kalibracji
            projected_points, _ = cv2.projectPoints(
                self.object_points[i],
                self.rvecs[i],  # Używaj prawdziwego wektora rotacji
                self.tvecs[i],  # Używaj prawdziwego wektora translacji
                self.camera_matrix,
                self.distortion_coeffs,
            )

            # Oblicz błąd reprojekcji
            error = cv2.norm(self.image_points[i], projected_points, cv2.NORM_L2) / len(
                projected_points
            )
            total_error += error * len(projected_points)
            total_points += len(projected_points)

        calculated_rms = total_error / total_points

        # Zwróć prawdziwy błąd RMS z kalibracji - jest bardziej wiarygodny
        return (
            self.calibration_rms if self.calibration_rms is not None else calculated_rms
        )

    def save_calibration(self, filename: str = None) -> str:
        """Zapisuje parametry kalibracji do pliku JSON.

        Args:
            filename: Nazwa pliku (opcjonalne)

        Returns:
            str: Ścieżka do zapisanego pliku
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"camera_calibration_{timestamp}.json"

        # Przygotuj dane do zapisania
        calibration_data = {
            "camera_model": "orbec_gemini_335le",
            "camera_ip": self.camera_ip,
            "calibration_date": datetime.now().isoformat(),
            "image_size": {"width": self.image_size[0], "height": self.image_size[1]},
            "chessboard_config": {
                "size": self.chessboard_size,
                "square_size_mm": self.square_size,
            },
            "camera_params": [
                float(self.camera_matrix[0, 0]),  # fx
                float(self.camera_matrix[1, 1]),  # fy
                float(self.camera_matrix[0, 2]),  # cx
                float(self.camera_matrix[1, 2]),  # cy
            ],
            "distortion_coefficients": [
                float(self.distortion_coeffs[0, 0]),  # k1
                float(self.distortion_coeffs[0, 1]),  # k2
                float(self.distortion_coeffs[0, 2]),  # p1
                float(self.distortion_coeffs[0, 3]),  # p2
                float(self.distortion_coeffs[0, 4]),  # k3
            ],
            "camera_matrix": self.camera_matrix.tolist(),
            "rms_error": self.calibration_rms
            if self.calibration_rms is not None
            else self.evaluate_calibration(),
            "num_images": len(self.object_points),
            "output_directory": self.output_dir,
        }

        # Zapisz do pliku
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(calibration_data, f, indent=4, ensure_ascii=False)

        print(f"💾 Parametry kalibracji zapisane do: {filename}")
        return filename

    def update_camera_config(
        self, config_file: str = "camera_server_192.168.1.10_config.json"
    ):
        """Aktualizuje plik konfiguracji kamery nowymi parametrami.

        Args:
            config_file: Ścieżka do pliku konfiguracji
        """
        if not os.path.exists(config_file):
            print(f"BŁĄD: Plik konfiguracji {config_file} nie istnieje")
            return

        try:
            # Wczytaj istniejącą konfigurację
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            # Utwórz kopię zapasową
            backup_file = (
                f"{config_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            print(f"💾 Kopia zapasowa: {backup_file}")

            # Aktualizuj parametry
            config["camera_configuration"]["camera_params"] = [
                float(self.camera_matrix[0, 0]),  # fx
                float(self.camera_matrix[1, 1]),  # fy
                float(self.camera_matrix[0, 2]),  # cx
                float(self.camera_matrix[1, 2]),  # cy
            ]

            config["camera_configuration"]["distortion_coefficients"] = [
                float(self.distortion_coeffs[0, 0]),  # k1
                float(self.distortion_coeffs[0, 1]),  # k2
                float(self.distortion_coeffs[0, 2]),  # p1
                float(self.distortion_coeffs[0, 3]),  # p2
                float(self.distortion_coeffs[0, 4]),  # k3
            ]

            # Zapisz zaktualizowaną konfigurację
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            print(f"✓ Konfiguracja kamery zaktualizowana: {config_file}")

        except Exception as e:
            print(f"BŁĄD aktualizacji konfiguracji: {e}")

    def print_results(self):
        """Wyświetla wyniki kalibracji."""
        if self.camera_matrix is None:
            print("Brak danych kalibracji")
            return

        print(f"\n" + "=" * 60)
        print(f"🎯 WYNIKI KALIBRACJI KAMERY")
        print(f"=" * 60)
        rms_error = (
            self.calibration_rms
            if self.calibration_rms is not None
            else self.evaluate_calibration()
        )
        print(f"📏 Błąd reprojekcji RMS: {rms_error:.4f} pikseli")

        # Dodatkowa analiza jakości
        print(f"📊 Ocena jakości kalibracji:")
        if rms_error < 0.5:
            print(f"├─ 🟢 DOSKONAŁA (< 0.5 piksela)")
        elif rms_error < 1.0:
            print(f"├─ 🔵 BARDZO DOBRA (< 1.0 piksela)")
        elif rms_error < 2.0:
            print(f"├─ 🟡 AKCEPTOWALNA (< 2.0 pikseli)")
        else:
            print(f"├─ 🔴 SŁABA (≥ 2.0 pikseli) - zalecane powtórzenie")

        # Sprawdź stosunek ogniskowych
        fx, fy = self.camera_matrix[0, 0], self.camera_matrix[1, 1]
        aspect_ratio = fx / fy if fy > 0 else 1.0
        print(f"├─ Stosunek ogniskowych fx/fy: {aspect_ratio:.4f}")
        if abs(aspect_ratio - 1.0) > 0.05:
            print(f"│  ⚠️  Stosunek ogniskowych znacznie odbiega od 1.0")

        # Sprawdź punkt główny
        cx, cy = self.camera_matrix[0, 2], self.camera_matrix[1, 2]
        center_x, center_y = self.image_size[0] / 2, self.image_size[1] / 2
        offset_x = abs(cx - center_x)
        offset_y = abs(cy - center_y)
        print(f"└─ Odchylenie punktu głównego: X={offset_x:.1f}px, Y={offset_y:.1f}px")
        if offset_x > 50 or offset_y > 50:
            print(f"   ⚠️  Punkt główny znacznie odbiega od środka obrazu")

        print(f"📊 Liczba obrazów: {len(self.object_points)}")
        print(f"📐 Rozmiar obrazu: {self.image_size[0]}x{self.image_size[1]}")
        print(f"📁 Katalog obrazów: {self.output_dir}")
        print(f"\n📋 PARAMETRY DO KOPIOWANIA:")
        print(f"├─ camera_params:")
        print(
            f"│  [{self.camera_matrix[0, 0]:.5f}, {self.camera_matrix[1, 1]:.5f}, {self.camera_matrix[0, 2]:.5f}, {self.camera_matrix[1, 2]:.5f}]"
        )
        print(f"├─ distortion_coefficients:")
        print(
            f"│  [{self.distortion_coeffs[0, 0]:.8f}, {self.distortion_coeffs[0, 1]:.8f}, {self.distortion_coeffs[0, 2]:.8f}, {self.distortion_coeffs[0, 3]:.8f}, {self.distortion_coeffs[0, 4]:.8f}]"
        )
        print(f"\n📊 SZCZEGÓŁY MACIERZY KAMERY:")
        print(f"├─ fx (ogniskowa X): {self.camera_matrix[0, 0]:.5f} pikseli")
        print(f"├─ fy (ogniskowa Y): {self.camera_matrix[1, 1]:.5f} pikseli")
        print(f"├─ cx (punkt główny X): {self.camera_matrix[0, 2]:.5f} pikseli")
        print(f"└─ cy (punkt główny Y): {self.camera_matrix[1, 2]:.5f} pikseli")
        print(f"\n📊 PORÓWNANIE Z OBECNYMI PARAMETRAMI:")
        try:
            with open("camera_server_192.168.1.10_config.json", "r") as f:
                current_config = json.load(f)
                current_params = current_config["camera_configuration"]["camera_params"]
                print(
                    f"├─ Obecne fx: {current_params[0]:.5f} -> Nowe fx: {self.camera_matrix[0, 0]:.5f}"
                )
                print(
                    f"├─ Obecne fy: {current_params[1]:.5f} -> Nowe fy: {self.camera_matrix[1, 1]:.5f}"
                )
                print(
                    f"├─ Obecne cx: {current_params[2]:.5f} -> Nowe cx: {self.camera_matrix[0, 2]:.5f}"
                )
                print(
                    f"└─ Obecne cy: {current_params[3]:.5f} -> Nowe cy: {self.camera_matrix[1, 2]:.5f}"
                )
        except:
            pass
        print(f"=" * 60)

    def cleanup(self):
        """Sprząta zasoby."""
        if self.pipeline:
            try:
                self.pipeline.stop()
            except:
                pass


def main():
    """Główna funkcja kalibracji."""
    print("🎯 KALIBRACJA KAMERY ORBEC GEMINI 335LE (bez GUI)")
    print("=" * 50)

    # Parametry kalibracji
    chessboard_size = (9, 6)  # Narożniki wewnętrzne (szerokość x wysokość)
    square_size = 25.0  # Rozmiar kwadratu w mm
    min_images = 20  # Minimalna liczba obrazów

    print(f"📋 Parametry kalibracji:")
    print(
        f"├─ Wzorzec szachownicy: {chessboard_size[0]}x{chessboard_size[1]} narożników"
    )
    print(f"├─ Rozmiar kwadratu: {square_size}mm")
    print(f"└─ Minimalna liczba obrazów: {min_images}")

    # Stwórz kalibrator
    calibrator = CameraCalibratorNoGUI(
        chessboard_size=chessboard_size, square_size=square_size
    )

    try:
        # Inicjalizuj kamerę
        if not calibrator.init_camera():
            print("❌ Nie można zainicjalizować kamery")
            return 1

        # Wybór trybu zbierania obrazów
        print(f"\n🎛️  Wybierz tryb zbierania obrazów:")
        print(f"1. Automatyczny (co 2 sekundy)")
        print(f"2. Ręczny (naciśnij ENTER)")

        while True:
            choice = input("Wybór (1 lub 2): ").strip()
            if choice == "1":
                success = calibrator.collect_calibration_images_auto(min_images)
                break
            elif choice == "2":
                success = calibrator.collect_calibration_images_manual(min_images)
                break
            else:
                print("Nieprawidłowy wybór, spróbuj ponownie")

        if not success:
            print("❌ Nie zebrano wystarczającej liczby obrazów")
            return 1

        # Wykonaj kalibrację
        if not calibrator.calibrate_camera():
            print("❌ Kalibracja nie powiodła się")
            return 1

        # Wyświetl wyniki
        calibrator.print_results()

        # Zapisz wyniki
        calib_file = calibrator.save_calibration()

        # Zapytaj o aktualizację konfiguracji
        response = input(
            "\n❓ Czy chcesz zaktualizować plik konfiguracji kamery? (t/n): "
        )
        if response.lower() in ["t", "tak", "y", "yes"]:
            calibrator.update_camera_config()

        print(f"\n✅ Kalibracja zakończona pomyślnie!")
        print(f"📁 Plik kalibracji: {calib_file}")
        print(f"📁 Obrazy kalibracyjne: {calibrator.output_dir}")

        return 0

    except KeyboardInterrupt:
        print(f"\n⚠️  Kalibracja przerwana przez użytkownika")
        return 1
    except Exception as e:
        print(f"\n❌ Błąd podczas kalibracji: {e}")
        return 1
    finally:
        calibrator.cleanup()


if __name__ == "__main__":
    exit(main())
