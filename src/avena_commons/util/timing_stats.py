# AI: Utility class for collecting and analyzing timing statistics from Catchtime measurements
"""
Klasa do zbierania i analizowania statystyk czasów wykonywania z pomiarów Catchtime.

Pozwala na gromadzenie czasów wykonywania z różnych części kodu i obliczanie
podstawowych statystyk: średnia, minimum, maksimum.
"""

import statistics
from typing import Dict, List, Optional


class TimingStatsCollector:
    """Kolektor statystyk czasów wykonywania.

    Zbiera pomiary czasów z różnych operacji i pozwala na obliczanie
    podstawowych statystyk: średnia, minimum, maksimum.

    Attributes:
        measurements (Dict[str, List[float]]): Słownik przechowujący pomiary
            zgrupowane według nazw operacji.
    """

    def __init__(self):
        """Inicjalizuje pusty kolektor statystyk."""
        self.measurements: Dict[str, List[float]] = {}

    def add_measurement(self, operation_name: str, time_value: float) -> None:
        """Dodaje pomiar czasu dla określonej operacji.

        Args:
            operation_name: Nazwa operacji/funkcji/metody.
            time_value: Czas wykonywania w sekundach lub milisekundach.

        Raises:
            ValueError: Gdy time_value jest ujemne lub nie jest liczbą.
        """
        if not isinstance(time_value, (int, float)):
            raise ValueError(f"time_value must be a number, got {type(time_value)}")

        if time_value < 0:
            raise ValueError("time_value cannot be negative")

        if operation_name not in self.measurements:
            self.measurements[operation_name] = []

        self.measurements[operation_name].append(float(time_value))

    def get_stats(self, operation_name: str) -> Optional[Dict[str, float]]:
        """Oblicza statystyki dla określonej operacji.

        Args:
            operation_name: Nazwa operacji do analizy.

        Returns:
            Dict[str, float] | None: Słownik z kluczami 'mean', 'min', 'max', 'count'
            lub None jeśli brak pomiarów dla tej operacji.
        """
        if (
            operation_name not in self.measurements
            or not self.measurements[operation_name]
        ):
            return None

        values = self.measurements[operation_name]

        return {
            "mean": statistics.mean(values),
            "min": min(values),
            "max": max(values),
            "count": len(values),
        }

    def get_all_stats(self) -> Dict[str, Dict[str, float]]:
        """Oblicza statystyki dla wszystkich operacji.

        Returns:
            Dict[str, Dict[str, float]]: Słownik gdzie klucze to nazwy operacji,
            a wartości to słowniki ze statystykami.
        """
        stats = {}
        for operation_name in self.measurements:
            operation_stats = self.get_stats(operation_name)
            if operation_stats:
                stats[operation_name] = operation_stats
        return stats

    def clear(self) -> None:
        """Czyści wszystkie zgromadzone pomiary."""
        self.measurements.clear()

    def clear_operation(self, operation_name: str) -> None:
        """Czyści pomiary dla określonej operacji.

        Args:
            operation_name: Nazwa operacji do wyczyszczenia.
        """
        if operation_name in self.measurements:
            del self.measurements[operation_name]

    def get_operation_names(self) -> List[str]:
        """Zwraca listę nazw wszystkich operacji z pomiarami.

        Returns:
            List[str]: Lista nazw operacji.
        """
        return list(self.measurements.keys())

    def print_summary(self) -> None:
        """Wyświetla podsumowanie wszystkich statystyk w czytelnej formie."""
        stats = self.get_all_stats()

        if not stats:
            print("Brak zgromadzonych statystyk.")
            return

        print("\n=== PODSUMOWANIE STATYSTYK CZASÓW WYKONYWANIA ===")
        print(
            f"{'Operacja':<30} {'Średnia (ms)':<12} {'Min (ms)':<12} {'Max (ms)':<12} {'Liczba':<8}"
        )
        print("-" * 78)

        for operation_name, operation_stats in stats.items():
            print(
                f"{operation_name:<30} "
                f"{operation_stats['mean']:<12.2f} "
                f"{operation_stats['min']:<12.2f} "
                f"{operation_stats['max']:<12.2f} "
                f"{operation_stats['count']:<8}"
            )
        print("-" * 78)

    def print_detailed_analysis(self) -> None:
        """Wyświetla szczegółową analizę wydajności."""
        stats = self.get_all_stats()

        if not stats:
            print("Brak danych do analizy.")
            return

        print("\n=== SZCZEGÓŁOWA ANALIZA WYDAJNOŚCI ===")

        # Sortuj według średniego czasu
        sorted_by_time = sorted(stats.items(), key=lambda x: x[1]["mean"], reverse=True)

        print("\n🐌 Ranking według średniego czasu wykonywania:")
        for i, (operation, op_stats) in enumerate(sorted_by_time, 1):
            mean_ms = op_stats["mean"]
            variance_ms = op_stats["max"] - op_stats["min"]
            print(f"   {i}. {operation}")
            print(f"      Średnia: {mean_ms:8.2f} ms")
            print(f"      Rozrzut: ±{variance_ms:7.2f} ms")
            print(f"      Próbek:  {op_stats['count']:8}")

            if op_stats["count"] > 1:
                stability = (
                    1 - (op_stats["max"] - op_stats["min"]) / op_stats["mean"]
                ) * 100
                print(f"      Stabilność: {stability:5.1f}%")
            print()

        # Analiza stabilności
        print("📊 Analiza stabilności (operacje z wieloma próbkami):")
        stable_ops = [
            (name, stats_data)
            for name, stats_data in stats.items()
            if stats_data["count"] > 1
        ]

        if stable_ops:
            stable_ops.sort(key=lambda x: (x[1]["max"] - x[1]["min"]) / x[1]["mean"])

            for operation, op_stats in stable_ops:
                variance_ms = op_stats["max"] - op_stats["min"]
                stability = (
                    1 - (op_stats["max"] - op_stats["min"]) / op_stats["mean"]
                ) * 100
                print(
                    f"   {operation}: {stability:5.1f}% stabilności (±{variance_ms:.1f}ms)"
                )
        else:
            print("   Brak operacji z wieloma próbkami do analizy stabilności.")

    def get_slowest_operations(self, count: int = 3) -> List[tuple]:
        """Zwraca najwolniejsze operacje.

        Args:
            count: Liczba operacji do zwrócenia.

        Returns:
            List[tuple]: Lista krotek (nazwa_operacji, średni_czas_ms).
        """
        stats = self.get_all_stats()
        if not stats:
            return []

        sorted_ops = sorted(stats.items(), key=lambda x: x[1]["mean"], reverse=True)
        return [(name, data["mean"]) for name, data in sorted_ops[:count]]

    def get_most_unstable_operations(self, count: int = 3) -> List[tuple]:
        """Zwraca najbardziej niestabilne operacje (największy rozrzut).

        Args:
            count: Liczba operacji do zwrócenia.

        Returns:
            List[tuple]: Lista krotek (nazwa_operacji, rozrzut_ms, stabilność_%).
        """
        stats = self.get_all_stats()
        if not stats:
            return []

        # Tylko operacje z wieloma próbkami
        multi_sample_ops = [
            (name, data) for name, data in stats.items() if data["count"] > 1
        ]

        if not multi_sample_ops:
            return []

        # Sortuj według względnego rozrzutu (niestabilności)
        unstable_ops = []
        for name, data in multi_sample_ops:
            variance = data["max"] - data["min"]
            relative_variance = variance / data["mean"]
            variance_ms = variance
            stability = (1 - relative_variance) * 100
            unstable_ops.append((name, variance_ms, stability, relative_variance))

        unstable_ops.sort(
            key=lambda x: x[3], reverse=True
        )  # Sortuj według względnego rozrzutu

        return [
            (name, variance_ms, stability)
            for name, variance_ms, stability, _ in unstable_ops[:count]
        ]

    def export_to_csv(self, filename: str = "timing_stats.csv") -> None:
        """Eksportuje statystyki do pliku CSV.

        Args:
            filename: Nazwa pliku do zapisu.
        """
        import csv
        from datetime import datetime

        stats = self.get_all_stats()
        if not stats:
            print("Brak danych do eksportu.")
            return

        with open(filename, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "operacja",
                "srednia_ms",
                "min_ms",
                "max_ms",
                "liczba_probek",
                "stabilnosc_%",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()
            for operation_name, operation_stats in stats.items():
                stability = None
                if operation_stats["count"] > 1:
                    stability = (
                        1
                        - (operation_stats["max"] - operation_stats["min"])
                        / operation_stats["mean"]
                    ) * 100

                writer.writerow({
                    "operacja": operation_name,
                    "srednia_ms": round(operation_stats["mean"], 2),
                    "min_ms": round(operation_stats["min"], 2),
                    "max_ms": round(operation_stats["max"], 2),
                    "liczba_probek": operation_stats["count"],
                    "stabilnosc_%": round(stability, 1)
                    if stability is not None
                    else "N/A",
                })

        print(f"✅ Statystyki wyeksportowane do: {filename}")
        print(f"   Eksportowano dane dla {len(stats)} operacji")
        print(f"   Czas eksportu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# Globalna instancja kolektora dla łatwego użycia
global_timing_stats = TimingStatsCollector()
