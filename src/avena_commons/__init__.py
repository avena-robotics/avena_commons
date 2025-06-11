"""
Avena Commons
===================================================

Kompleksowy zbiór narzędzi do robotyki i monitorowania systemów
zapewniający komunikację czasu rzeczywistego, zarządzanie konfiguracją i możliwości monitorowania.

## Moduły

#### config - Zarządzanie Konfiguracją
Scentralizowane zarządzanie konfiguracją z automatycznym parsowaniem i walidacją plików INI.
- `Config`: Bazowa klasa konfiguracji z obsługą odczytu/zapisu
- `ControllerConfig`: Wyspecjalizowana konfiguracja dla kontrolerów

#### connection - Komunikacja Międzyprocesowa
Wysokowydajna komunikacja wykorzystująca pamięć współdzieloną POSIX i semafory.
- `AvenaComm`: Synchronizowany dostęp do pamięci współdzielonej z obsługą serializacji

#### event_listener - System Zdarzeń
Architektura sterowana zdarzeniami oparta na FastAPI z asynchronicznym przetwarzaniem.
- `EventListener`: Serwer HTTP z kolejkami priorytetowymi i zarządzaniem stanem
- Typy zdarzeń: `IoAction`, `KdsAction`, `SupervisorMoveAction`, `SupervisorGripperAction`, `SupervisorPumpAction`

#### io - System Wejść/Wyjść
Zarządzanie urządzeniami przemysłowymi przez różne protokoły komunikacyjne.
- Protokoły: EtherCAT, ModbusRTU, ModbusTCP
- Typy urządzeń: moduły I/O, sterowniki silników, sensory
- `IO_server`: Scentralizowane zarządzanie urządzeniami
- `VirtualDevice`: Interfejsy do symulacji i testowania

#### sequence - Maszyny Stanów
Zarządzanie złożonymi operacjami sekwencyjnymi z logiką ponawiania i obsługą błędów.
- `Sequence`: Wykonanie krok po kroku ze śledzeniem stanu
- `SequenceStatus`, `SequenceStepStatus`, `StepState`: Śledzenie postępu i stanów

#### system_dashboard - Dashboard Webowy
Interfejs monitorowania systemu w czasie rzeczywistym oparty na Flask.
- Monitorowanie CPU, pamięci, dysku i procesów
- Uwierzytelnianie użytkownika i aktualizacje AJAX
- Responsywny interfejs z wykresami Chart.js

#### util - Narzędzia Pomocnicze
Funkcje matematyczne, pomiar wydajności i narzędzia systemowe.
- `MeasureTime`: Pomiar czasu wykonania kodu
- Funkcje 3D: transformacje, interpolacja, obliczenia robotyczne
- Filtry sygnałów i systemy sterowania

"""
