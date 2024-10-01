import numpy as np


class QuantizerLogPower:

    def __init__(
        self,
        x_min: float = 0.0006,
        x_max: float = 6.0,
        num_intervals: int = 33,
        power: int = 3,
    ) -> None:
        self.x_min = x_min
        self.x_max = x_max
        self.num_intervals = num_intervals
        self.power = power
        if self.num_intervals < 1 or not isinstance(self.num_intervals, int):
            raise ValueError("num_intervals must be int greater than 0")
        if self.power < 1 or not isinstance(self.power, int):
            raise ValueError("power must be int greater than 0")
        self.dequantize_list, self.mid_point_list = self._generate_dequantize_list()

    def _find_change_points_linspace(self):
        x_values = np.linspace(
            self.x_min, self.x_max, 100000
        )  # Using linspace for a more uniform distribution

        # Initialize previous value and change points list
        prev_value = self.quantize(x_values[0])
        change_points = [self.x_min]

        # Iterate through x_values and identify change points
        for x in x_values[1:]:
            curr_value = self.quantize(x)
            if curr_value != prev_value:
                change_points.append(x)
            prev_value = curr_value

        return np.array(change_points)

    def _generate_dequantize_list(self) -> np.array:

        if self.num_intervals == 1:
            return np.array([0.0]), np.array([0.0])
        if self.num_intervals == 2:
            return np.array([-self.x_max, self.x_max]), np.array(
                [-self.x_max, self.x_max]
            )
        if self.num_intervals == 3:
            return np.array([-self.x_max, 0.0, self.x_max]), np.array(
                [-self.x_max, 0.0, self.x_max]
            )
        if self.num_intervals == 4:
            return np.array(
                [-self.x_max, -self.x_max / 2, self.x_max / 2, self.x_max]
            ), np.array([-self.x_max, -self.x_max / 2, self.x_max / 2, self.x_max])

        # sytuacja num_intervals = 5 (pierwsza normalna sytuacja)

        # na razie rozwazamy num_intervals nieparzyste i >= 5
        ilosc_sektorow_parzysta = 1 if self.num_intervals % 2 == 0 else 0

        srodek = (
            [0.0] if ilosc_sektorow_parzysta == 0 else [-self.x_min / 2, self.x_min / 2]
        )  # srodek przedzialu

        x_values = np.linspace(
            self.x_min, self.x_max, 100000
        )  # Using linspace for a more uniform distribution

        # Initialize previous value and change points list
        prev_value = self.quantize(x_values[0])
        # change_points = [self.x_min]
        change_points = [self.x_min] if ilosc_sektorow_parzysta == 0 else []

        # Iterate through x_values and identify change points
        for x in x_values[1:]:
            curr_value = self.quantize(x)
            if curr_value != prev_value:
                change_points.append(x)
            prev_value = curr_value
        change_points = np.array(change_points)

        midpoints_np = np.convolve(change_points, [0.5, 0.5], mode="valid")

        dequantize_list = np.concatenate(
            [-1 * change_points[::-1], srodek, change_points]
        )
        mid_point_list = np.concatenate(
            [[-self.x_max], -1 * midpoints_np[::-1], srodek, midpoints_np, [self.x_max]]
        )
        return dequantize_list, mid_point_list

    def quantize(self, x: float) -> int:

        # sytuacja num_intervals = 1 - zawsze zwracaj 0
        if self.num_intervals == 1:
            return 0

        # sytuacja num_intervals = 2 - 0 dla x < 0, 1 dla x => x_max
        if self.num_intervals == 2:
            return 0 if x < 0 else 1

        # sytuacja num_intervals = 3 - 0 dla x <= -x_max, 2 dla x => x_max, 1 dla reszty
        if self.num_intervals == 3:
            if x > -self.x_max and x < self.x_max:
                return 1

        # sytuacja num_intervals = 4 - 0 dla x <= -x_max, 3 dla x => x_max, 1 dla x_max < x < 0, 2 dla 0 >= x > x_max
        if self.num_intervals == 3:
            if x > -self.x_max and x < 0:
                return 1
            if x >= 0 and x < self.x_max:
                return 2

        # sytuacja num_intervals = 5 (pierwsza normalna sytuacja)

        # na razie rozwazamy num_intervals nieparzyste i >= 5
        znak = (
            1 if x >= 0 else -1
        )  # ustalenie czesci kwantow sla argumentow dodatnich/ujemnych
        ilosc_sektorow_parzysta = 1 if self.num_intervals % 2 == 0 else 0
        positive_intervals_in_function = (
            int(self.num_intervals / 2) - 1
        )  # okreslenie ilosci kwantow po stronie dodatniej liczonych z funkcji

        # kwanty brzegowe (z poza funkcji)
        if x <= -self.x_max:
            return 0
        if x >= self.x_max:
            return self.num_intervals - 1

        # kwanty srodkowe (z poza funkcji)
        if x > -self.x_min and x < self.x_min and ilosc_sektorow_parzysta == 0:
            return (
                positive_intervals_in_function + 1
            )  # srodkowy kwant dla nieparzystej ilosci
        if x > -self.x_min and x < 0 and ilosc_sektorow_parzysta == 1:
            return positive_intervals_in_function  # srodkowy kwant ujemny dla parzystej ilosci
        if x >= 0 and x < self.x_min and ilosc_sektorow_parzysta == 1:
            return (
                positive_intervals_in_function + 1
            )  # srodkowy kwant dodatni dla parzystej ilosci

        # kwanty nie brzegowe i srodkowe (w funkcji)
        # if ilosc_sektorow_parzysta == 0:
        result = (
            (np.log10(abs(x)) ** self.power - np.log10(self.x_min) ** self.power)
            * (positive_intervals_in_function - 1)
            / (np.log10(self.x_max) ** self.power - np.log10(self.x_min) ** self.power)
        ) + 1

        # wybor kwantu
        quant = min(int(round(result)), positive_intervals_in_function)

        quant = (
            quant + positive_intervals_in_function + 1 - ilosc_sektorow_parzysta
            if znak == 1
            else positive_intervals_in_function - quant + 1
        )
        return quant

    def dequantize(self, quant: int) -> float:
        if quant < 0 or not isinstance(quant, int):
            raise ValueError(f"quant must be int from 0 to {self.num_intervals - 1}")
        return self.mid_point_list[quant]


class QuantizerTanh:

    def __init__(
        self, x_min: float, x_max: float, num_intervals: int, power: float
    ) -> None:
        self.x_min = x_min
        self.x_max = x_max
        self.num_intervals = num_intervals
        self.power = power

    # Function to quantize the value, n- number of intervals, k- quantization factor
    def quantize(self, x: float) -> int:
        # Normalizing the value
        x_norm = ((x - self.x_min) / (self.x_max - self.x_min)) * 2 - 1
        # Applying tanh function
        y = np.tanh(self.power * x_norm)
        # Scaling to the range of 0 to n-1
        interval_number = ((y + 1) / 2) * (self.num_intervals - 1)
        return int(round(interval_number))

    # Function to reverse quantize the interval number, n- number of intervals, k- quantization factor
    def dequantize(self, quant: int) -> float:
        # Handling edge cases for extreme intervals
        if quant == 0:
            return self.x_min
        elif quant == self.num_intervals - 1:
            return self.x_max
        # Scaling to the range of -1 to 1
        y = (quant / (self.num_intervals - 1)) * 2 - 1
        # Calculating the inverse of tanh
        x_norm = (1 / self.power) * np.arctanh(y)
        # Scaling back to the original range
        x = (x_norm + 1) * (self.x_max - self.x_min) / 2 + self.x_min
        return x


class QuantizerLinear:

    def __init__(self, x_min: float, x_max: float, num_intervals: int) -> None:
        self.x_min = x_min
        self.x_max = x_max
        self.num_intervals = num_intervals

    def quantize(self, x: float) -> int:
        # Step 1: Value below range
        if x <= self.x_min:
            return 0

        # Step 2: Value above range
        if x >= self.x_max:
            return self.num_intervals - 1

        # Step 3: Quantize value
        # Find the range of each quantization level
        interval = (self.x_max - self.x_min) / (self.num_intervals - 1)

        # Determine which quantization level the value falls into
        quantized_value = round((x - self.x_min) / interval)

        return int(quantized_value)

    def dequantize(self, quant: int) -> float:
        interval = (self.x_max - self.x_min) / (self.num_intervals - 1)
        continuous_value = quant * interval + self.x_min - (self.x_max + self.x_min) / 2
        return continuous_value


class QuantizerPolynomial:

    def __init__(
        self, x_min: float, x_max: float, num_intervals: int, power: int
    ) -> None:
        self.x_min = x_min
        self.x_max = x_max
        self.num_intervals = num_intervals
        self.power = power
        self.middle_quant = (self.num_intervals - 1) // 2
        self.poly_max = self.x_max**self.power

    def quantize(self, x: float) -> int:
        middle_quant = (self.num_intervals - 1) // 2

        # Jeśli x jest poza zakresem x_min i x_max, zwróć odpowiednio 0 lub ilosc_kwantow - 1
        if x < self.x_min:
            return 0
        if x > self.x_max:
            return self.num_intervals - 1

        # Oblicz wartość wielomianu dla wartości bezwzględnej x
        poly_val = abs(x) ** self.power
        poly_max = self.x_max**self.power

        # Normalizacja wartości wielomianu do zakresu 0-1
        normalized_val = poly_val / poly_max

        # Jeśli x jest dodatnie, mapuj na zakres od środkowego kwantu do ilosc_kwantow-1
        if x >= 0:
            quantized_val = middle_quant + int(
                normalized_val * (self.num_intervals - 1 - middle_quant)
            )
        # Jeśli x jest ujemne, mapuj na zakres od 0 do środkowego kwantu
        else:
            quantized_val = middle_quant - int(normalized_val * middle_quant)

        return quantized_val

    def dequantize(self, quant: int) -> float:
        if quant == 0:
            return self.x_min

        # Using the symmetry property for quants below the middle quant
        if quant < self.middle_quant:
            x_val = self.dequantize_for_positive(
                self.middle_quant + (self.middle_quant - quant)
            )
            return -x_val

        return self.dequantize_for_positive(quant)

    def dequantize_for_positive(self, quant: int) -> float:
        if quant <= self.middle_quant:
            normalized_upper = 1 - (quant / self.middle_quant)
            normalized_lower = (
                1 - ((quant + 1) / self.middle_quant)
                if quant != self.middle_quant
                else 0
            )
        else:
            normalized_lower = (quant - self.middle_quant) / (
                self.num_intervals - 1 - self.middle_quant
            )
            normalized_upper = (
                (quant + 1 - self.middle_quant)
                / (self.num_intervals - 1 - self.middle_quant)
                if quant != self.num_intervals - 1
                else 1
            )

        poly_lower = normalized_lower * self.poly_max
        poly_upper = normalized_upper * self.poly_max

        x_lower = poly_lower ** (1 / self.power)
        x_upper = poly_upper ** (1 / self.power)

        return (x_lower + x_upper) / 2
