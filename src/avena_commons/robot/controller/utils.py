"""
AI Header: Utility dla obliczeń ciśnienia z napięcia z buforem mediany.
Wejście: napięcie 0-10V; Wyjście: ciśnienie w kPa [-100..0].
Używany w kontrolerach robotów do przetwarzania sygnałów z czujników podciśnienia.
"""

from typing import List


class PressureCalculator:
    """Kalkulator ciśnienia z napięcia z filtrem mediany.

    Konwertuje napięcie wejściowe (0-10V) na ciśnienie w kPa z użyciem
    bufora kołowego i mediany dla stabilizacji odczytów.

    Attributes:
        adc_resolution (float): Rozdzielczość ADC (domyślnie 4096 dla 12-bit).
        adc_supply_voltage (float): Napięcie zasilania ADC w V (domyślnie 4.5V).
        buffer_size (int): Rozmiar bufora mediany (domyślnie 100 próbek).
        kpa_low (float): Dolna granica zakresu ciśnienia w kPa (domyślnie -100.0).
        kpa_high (float): Górna granica zakresu ciśnienia w kPa (domyślnie 0.0).
    """

    def __init__(
        self,
        adc_resolution: float = 4096.0,
        adc_supply_voltage: float = 4.5,
        buffer_size: int = 100,
        kpa_low: float = -100.0,
        kpa_high: float = 0.0,
    ) -> None:
        """Inicjalizuje kalkulator ciśnienia.

        Args:
            adc_resolution: Rozdzielczość ADC (np. 4096 dla 12-bit).
            adc_supply_voltage: Napięcie zasilania ADC w V.
            buffer_size: Rozmiar bufora dla filtru mediany.
            kpa_low: Dolna granica ciśnienia w kPa (podciśnienie).
            kpa_high: Górna granica ciśnienia w kPa.

        Raises:
            ValueError: Gdy parametry są poza dopuszczalnym zakresem.
        """
        if adc_resolution <= 0:
            raise ValueError("adc_resolution must be positive")
        if adc_supply_voltage <= 0:
            raise ValueError("adc_supply_voltage must be positive")
        if buffer_size <= 0:
            raise ValueError("buffer_size must be positive")
        if kpa_low >= kpa_high:
            raise ValueError("kpa_low must be less than kpa_high")

        self._adc_resolution = float(adc_resolution)
        self._adc_supply_voltage = float(adc_supply_voltage)
        self._buffer_size = int(buffer_size)
        self._kpa_low = float(kpa_low)
        self._kpa_high = float(kpa_high)

        self._voltage_buffer: List[int] = []
        self._buffer_index: int = 0

    def reset(self) -> None:
        """Czyści bufor mediany.

        Używane przy zmianie stanu systemu lub zmianie chwytaka,
        aby odrzucić stare próbki.
        """
        self._voltage_buffer.clear()
        self._buffer_index = 0

    def calculate_pressure(self, voltage_in: float) -> float:
        """Oblicza ciśnienie w kPa z napięcia wejściowego.

        Proces konwersji:
        1) Mapowanie napięcia 0-10V do zakresu ADC
        2) Ograniczenie do zakresu ADC (0 - adc_supply_voltage)
        3) Konwersja do wartości ADC (0 - adc_resolution-1)
        4) Bufor kołowy z medianą (stabilizacja)
        5) Skalowanie do kPa

        Args:
            voltage_in: Napięcie wejściowe w zakresie 0-10V.

        Returns:
            float: Ciśnienie w kPa (ujemne dla podciśnienia).
                  Zakres: [kpa_low, kpa_high], domyślnie [-100.0, 0.0].

        Raises:
            ValueError: Nigdy - wartości są automatycznie ograniczane do zakresu.
        """
        # 1) Clamp napięcia wejściowego do 0-10V
        v_clamped = max(0.0, min(10.0, voltage_in))

        # 2) Clamp do zakresu ADC (0 - adc_supply_voltage)
        v_adc = min(v_clamped, self._adc_supply_voltage)

        # 3) Konwersja V -> ADC counts (0 - adc_resolution-1)
        adc_count = int(
            (v_adc / self._adc_supply_voltage) * (self._adc_resolution - 1.0)
        )
        adc_count = max(0, min(int(self._adc_resolution - 1), adc_count))

        # 4) Bufor kołowy + mediana
        if len(self._voltage_buffer) < self._buffer_size:
            self._voltage_buffer.append(adc_count)
        else:
            self._voltage_buffer[self._buffer_index] = adc_count
            self._buffer_index = (self._buffer_index + 1) % self._buffer_size

        # Mediana z posortowanego bufora
        sorted_buffer = sorted(self._voltage_buffer)
        median_index = len(sorted_buffer) // 2
        adc_median = sorted_buffer[median_index]

        # 5) Skalowanie ADC -> kPa
        scale = (self._kpa_high - self._kpa_low) / (self._adc_resolution - 1.0)
        pressure_kpa = scale * adc_median + self._kpa_low

        return float(pressure_kpa)

    @property
    def buffer_fill_level(self) -> float:
        """Zwraca stopień zapełnienia bufora jako procent.

        Returns:
            float: Procent zapełnienia bufora (0.0 - 100.0).
        """
        return (len(self._voltage_buffer) / self._buffer_size) * 100.0

    @property
    def is_buffer_full(self) -> bool:
        """Sprawdza czy bufor jest pełny.

        Returns:
            bool: True jeśli bufor zawiera buffer_size próbek.
        """
        return len(self._voltage_buffer) >= self._buffer_size
