# Instrukcja kalibracji kamery Orbec Gemini 335LE

## Rozwiązanie
Wykonaj kalibrację kamery za pomocą wzorca szachownicy.

## Wymagania

### 1. Wzorzec szachownicy
- **Rozmiar:** 9x6 narożników wewnętrznych (10x7 kwadratów)
- **Wymiary kwadratu:** 25mm x 25mm
- **Materiał:** Biały papier z czarnymi kwadratami
- **Jakość:** Ostry druk, płaska powierzchnia

### 2. Środowisko
- Kamera Orbec Gemini 335LE podłączona i działająca
- Równomierne oświetlenie (unikaj cieni i odblaśków)
- Stabilne mocowanie kamery

## Proces kalibracji

### Krok 1: Przygotowanie wzorca
```bash
# Pobierz i wydrukuj wzorzec szachownicy
# Rozmiar: 9x6 narożników, 25mm kwadrat
# Przykład: https://github.com/opencv/opencv/blob/master/doc/pattern.png
```

### Krok 2: Uruchomienie kalibracji
```bash
cd ~/avena_commons
source .venv/bin/activate
python calibrate_camera_nogui.py
```

### Krok 3: Zbieranie obrazów
1. **Wybierz tryb ręczny (2)**
2. **Umieść wzorzec przed kamerą**
3. **Poruszaj wzorcem w różnych pozycjach:**
   - Centrum kadru
   - Lewy/prawy róg
   - Górny/dolny róg
   - Pod różnymi kątami (obrót w płaszczyźnie)
   - Różne odległości (30-70cm od kamery)
   - Pochylenie wzorca

### Krok 4: Wykrywanie narożników
- Skrypt automatycznie wykrywa narożniki szachownicy
- **Zielony status:** "✓ Wykryto narożniki szachownicy"
- **Pomarańczowy status:** "⚠ Brak narożników - dostosuj pozycję"

### Krok 5: Zapisywanie obrazów
- Naciśnij **ENTER** gdy widzisz "✓ Wykryto narożniki"
- Potrzebujesz **minimum 20 dobrych obrazów**
- Obrazy zapisywane w katalogu `calibration_images_YYYYMMDD_HHMMSS/`

### Krok 6: Kalibracja
Po zebraniu 20+ obrazów:
1. Skrypt automatycznie wykona kalibrację
2. Wyświetli nowe parametry kamery
3. Zapyta o aktualizację pliku konfiguracji

## Wyniki kalibracji

### Oczekiwane parametry
Po kalibracji otrzymasz nowe wartości:
```json
{
  "camera_params": [fx, fy, cx, cy],
  "distortion_coefficients": [k1, k2, p1, p2, k3]
}
```

### Weryfikacja jakości
- **Błąd RMS:** < 1.0 piksela (im mniejszy, tym lepiej)
- **Liczba obrazów:** 20+ (więcej = lepsze wyniki)
- **Punkt główny (cx, cy):** powinien być blisko centrum obrazu

### Przykład poprawnych wartości
```
Obecne (błędne):
camera_params: [1378.84831, 1375.17821, 956.711425, 573.043875]

Po kalibracji (oczekiwane):
camera_params: [~1200, ~1200, ~640, ~400]
```

## Aktualizacja konfiguracji

### Automatyczna aktualizacja
```bash
# Skrypt zapyta:
❓ Czy chcesz zaktualizować plik konfiguracji kamery? (t/n): t
```

### Ręczna aktualizacja
Edytuj plik `camera_server_192.168.1.10_config.json`:
```json
{
  "camera_configuration": {
    "camera_params": [NOWE_WARTOŚCI],
    "distortion_coefficients": [NOWE_WARTOŚCI]
  }
}
```

## Weryfikacja poprawności

### Test odległości
Po kalibracji sprawdź:
1. Umieść obiekt w odległości 50cm od kamery
2. Uruchom detekcję
3. Sprawdź Z-wartość 


## Rozwiązywanie problemów

### "Brak narożników"
- **Oświetlenie:** Dodaj więcej światła, unikaj cieni
- **Ostrość:** Sprawdź czy wzorzec jest ostry
- **Pozycja:** Przesuń wzorzec bliżej/dalej od kamery
- **Kąt:** Umieść wzorzec równolegle do kamery

### "Za mało obrazów"
- Zbierz więcej obrazów z różnych pozycji
- Upewnij się, że wzorzec zajmuje 20-80% kadru
- Używaj stabilnego uchwwytu wzorca

### "Wysoki błąd RMS"
- Zbierz więcej obrazów (30-50)
- Upewnij się o jakość druku wzorca
- Sprawdź równomierność oświetlenia

### "Qt platform plugin error"
- Użyj wersji `calibrate_camera_nogui.py` (bez GUI)
- Problem występuje w środowiskach bez X11

## Skrypty pomocnicze

### `calibrate_camera.py`
- Wersja z GUI (okno podglądu)
- Wymaga środowiska graficznego

### `calibrate_camera_nogui.py`
- Wersja bez GUI (tylko tekst)
- Działa w terminalu i SSH

## Uwagi bezpieczeństwa

### Kopia zapasowa
Skrypt automatycznie tworzy kopię zapasową:
```
camera_server_192.168.1.10_config.json.backup_YYYYMMDD_HHMMSS
```

### Przywracanie
W przypadku problemów:
```bash
cp camera_server_192.168.1.10_config.json.backup_YYYYMMDD_HHMMSS camera_server_192.168.1.10_config.json
```

## Kolejne kroki

Po udanej kalibracji:
1. **Restart systemu kamery**
2. **Test dokładności pomiarów**
3. **Sprawdzenie stabilności detekcji**
4. **Dokumentacja nowych parametrów**

---

**Autor:** AI Assistant  
**Data:** 23.09.2025  
**Wersja:** 1.0