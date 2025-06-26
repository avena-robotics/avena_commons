# Koncepcja Systemu Nadzorczego (Orchestrator)

## 1. Wprowadzenie

Niniejszy dokument opisuje architekturę i funkcjonalności centralnego komponentu nadzorczego, zwanego **Orchestrator**. Jego celem jest orkiestracja, monitorowanie i zarządzanie cyklem życia rozproszonych komponentów systemu opartych na klasie `EventListener`.

Orchestrator stanowi centralny punkt kontrolny, który zapewnia stabilność, odporność na błędy i przewidywalność całego ekosystemu.

## 2. Główne Założenia i Odpowiedzialności

Orchestrator dziedziczy po klasie `EventListener`, co pozwala mu na bezproblemową komunikację z innymi komponentami przy użyciu tego samego protokołu zdarzeń. Jego główne zadania to:

*   **Monitoring stanu i wydajności:** Aktywne zbieranie i agregowanie danych o kondycji każdego komponentu.
*   **Zarządzanie maszyną stanów (FSM):** Zdalne sterowanie stanami poszczególnych `EventListenerów` (np. `INITIALIZING`, `STARTED`, `STOPPING`, `MAINTENANCE`).
*   **Reakcja na awarie:** Automatyczne wykonywanie predefiniowanych scenariuszy (tzw. *playbooks*) w odpowiedzi na wykryte błędy, anomalie lub brak odpowiedzi.
*   **Centralizacja wiedzy:** Działanie jako "źródło prawdy" o aktualnej topologii i stanie systemu.

## 3. Proponowane Funkcjonalności

### 3.1. Zaawansowany Monitoring (Health & Performance)

Mechanizm `health_check` zostanie rozbudowany o następujące elementy:

*   **Agregacja Stanu:** Orchestrator będzie utrzymywał wewnętrzną mapę stanu wszystkich podległych mu komponentów.
    ```json
    {
      "komponent_A": {
        "status": "ONLINE", // ONLINE, OFFLINE, UNRESPONSIVE, DEGRADED
        "last_seen": "2023-10-27T10:00:00Z",
        "metrics": {
          "cpu_percent": 15.5,
          "memory_rss_mb": 256.4
        }
      }
    }
    ```
*   **Wykrywanie braku odpowiedzi (Timeout):** Jeśli komponent nie odpowie na `N` kolejnych zapytań `health_check`, jego status zostanie zmieniony na `UNRESPONSIVE`, co zainicjuje odpowiedni scenariusz błędu.
*   **Analiza Trendów:** Orchestrator będzie przechowywać historyczne dane metryk, aby wykrywać długofalowe problemy, takie jak wycieki pamięci.

### 3.2. Zarządzanie Maszyną Stanów (FSM)

Zarządzanie stanem komponentów będzie realizowane poprzez dedykowane zdarzenia.

*   **Zdarzenie `set_fsm_state`:** Orchestrator będzie wysyłał to zdarzenie, aby instruować komponenty do zmiany swojego wewnętrznego stanu.
*   **Operacje Grupowe:** Zostanie wprowadzona możliwość targetowania grup komponentów (np. po typie lub funkcji), aby jednocześnie zmienić ich stan.
*   **Sekwencje Stanów:** Orchestrator umożliwi definiowanie złożonych sekwencji operacji, np. "zatrzymaj A, poczekaj na potwierdzenie, uruchom B".

### 3.3. Scenariusze Reakcji na Błędy (Playbooks)

Logika reakcji na awarie będzie zdefiniowana w zewnętrznym, łatwo modyfikowalnym pliku konfiguracyjnym (np. `scenarios.yaml`), aby unikać "hardkodowania" jej w Orchestratorze.

**Przykład (`scenarios.yaml`):**
```yaml
- name: "Obsługa niedostępnego komponentu"
  condition:
    - type: "component_status"
      component: "database_connector"
      status: "UNRESPONSIVE"
  actions:
    - type: "log_event"
      level: "critical"
      message: "Krytyczny błąd: utracono połączenie z database_connector!"
    - type: "send_notification"
      channel: "email"
      recipient: "admin@example.com"
    - type: "set_group_fsm_state"
      group_tag: "db_dependent"
      state: "DEGRADED_MODE"
      message: "Praca w trybie awaryjnym z powodu problemów z bazą danych."
```

### 3.3.1. Składnia Scenariuszy: Wyzwalacze, Akcje i Selektory

Aby zapewnić spójność i modularność, scenariusze opierają się na zdefiniowanej strukturze:

*   **Wyzwalacze (Triggers):** Określają warunek, który musi zostać spełniony, aby uruchomić listę akcji. Przykłady użyte w dokumencie:
    *   `component_status`: Reaguje na zmianę statusu konkretnego komponentu.
    *   `all_components_ready`: Uruchamiany, gdy wszystkie komponenty osiągną określony stan (np. `READY`).
    *   `event_received`: Reaguje na konkretne zdarzenie wysłane przez dowolny komponent (np. monitor UPS).

*   **Akcje (Actions):** Definiują operacje do wykonania. Przykłady: `log_event`, `send_command`, `wait_for_state`.

*   **Selektory (Selectors):** Precyzują, do których komponentów skierowana jest dana akcja. Składnia powinna być ujednolicona:
    *   `component: "id_komponentu"`: Celuje w pojedynczy, konkretny komponent.
    *   `group: "nazwa_grupy"`: Celuje w jedną grupę komponentów.
    *   `groups: ["grupa1", "grupa2"]`: Celuje w wiele grup.
    *   `target: "@all"`: Specjalny selektor oznaczający wszystkie zarejestrowane komponenty.

### 3.4. Uporządkowane Zgłaszanie Błędów

Aby Orchestrator mógł podejmować inteligentne decyzje, takie jak restart usługi, jej reinicjalizacja czy kontrolowane zatrzymanie systemu, musi otrzymywać od komponentów szczegółowe i ustrukturyzowane informacje o błędach. W tym celu definiuje się standardowy format zgłoszenia.

#### 3.4.1. Zdarzenie `EVENT_ERROR_REPORTED`

Komponenty, zamiast wysyłać proste sygnały o awarii, powinny emitować bogate w kontekst zdarzenie `EVENT_ERROR_REPORTED`. Pozwala to na precyzyjne sterowanie logiką reakcji.

**Struktura zdarzenia (przykład):**
```json
{
  "event_type": "EVENT_ERROR_REPORTED",
  "source": "database_connector",
  "payload": {
    "severity": "critical",         // "critical", "error", "warning"
    "error_code": "DB_CONN_TIMEOUT",  // Unikalny, maszynowy kod błędu
    "message": "Nie udało się połączyć z bazą danych po 3 próbach.",
    "can_recover": false,           // Flaga, czy komponent uważa, że może sam wrócić do normy
    "metadata": {                   // Dowolne dodatkowe dane przydatne w diagnostyce
      "host": "db.example.com",
      "port": 5432,
      "attempts": 3
    }
  }
}
```

#### 3.4.2. Integracja ze Scenariuszami Reakcji (Playbooks)

Zgłoszenia błędów w tym formacie stają się precyzyjnymi wyzwalaczami dla scenariuszy. Orchestrator może na podstawie `error_code` lub `severity` uruchomić odpowiedni playbook, realizując zadaną logikę.

**Przykład (`error_handling_scenarios.yaml`):**

Poniższy scenariusz pokazuje, jak Orchestrator może zareagować na konkretny błąd, próbując najpierw procedury naprawczej, a w przypadku jej niepowodzenia – eskalując problem.

```yaml
- name: "Obsługa błędu połączenia z bazą danych"
  trigger:
    type: "event_received"
    event_type: "EVENT_ERROR_REPORTED"
    condition: "payload.error_code == 'DB_CONN_TIMEOUT'" # Warunek na danych z payloadu

  actions:
    - type: "log_event"
      level: "warning"
      # Użycie zmiennych z wyzwalacza do tworzenia dynamicznych komunikatów
      message: "Wykryto błąd '{{ trigger.payload.error_code }}' w komponencie '{{ trigger.source }}'. Próbuję automatycznej re-inicjalizacji."

    # KROK 1: Próba re-inicjalizacji komponentu, który zgłosił błąd
    - type: "send_command"
      component: "{{ trigger.source }}" # Dynamiczne targetowanie na źródło błędu
      command: "CMD_RESET"

    # KROK 2: Oczekiwanie na powrót do stanu gotowości
    - type: "wait_for_state"
      component: "{{ trigger.source }}"
      target_state: "READY"
      timeout: "30s"
      # Definicja akcji w przypadku niepowodzenia (timeout)
      on_failure:
        - type: "log_event"
          level: "critical"
          message: "Krytyczna awaria! Automatyczny reset komponentu '{{ trigger.source }}' nie powiódł się. Eskaluję problem."
        - type: "send_notification"
          channel: "on_call_admins"
          subject: "[PILNE] Awaria komponentu {{ trigger.source }}"
          message: "Automatyczny reset komponentu '{{ trigger.source }}' po błędzie '{{ trigger.payload.error_code }}' nie powiódł się. Wymagana interwencja!"
        # Uruchomienie scenariusza bezpiecznego zamknięcia systemu
        - type: "execute_scenario"
          name: "graceful_shutdown.yaml" # Nazwa innego pliku ze scenariuszem
```

### 3.5. Scenariusze Systemowe: Orkiestracja Uruchamiania

Jednym z kluczowych zadań Orchestratora jest zarządzanie złożonymi procesami obejmującymi wiele komponentów, takimi jak zsynchronizowany start całego systemu. Zamiast pozwalać komponentom na samodzielne, chaotyczne przechodzenie przez etapy inicjalizacji, Orchestrator realizuje to jako precyzyjny, wieloetapowy scenariusz.

#### 3.5.1. Maszyna Stanów (FSM) Komponentu

Aby scenariusze mogły poprawnie działać, każdy zarządzany komponent musi implementować spójną maszynę stanów.

**Definicja Stanów (Kompletna):**

*   `READY`: Stan początkowy po uruchomieniu procesu. Komponent zarejestrował się w Orchestratorze, jest gotowy na przyjęcie poleceń, ale nie zużywa znaczących zasobów. Jest to pasywny stan oczekiwania.
*   `INITIALIZING`: Stan aktywny. Komponent otrzymał polecenie inicjalizacji i wykonuje swoje zadania startowe (np. łączy się ze sprzętem, alokuje pamięć, ładuje konfigurację).
*   `INIT_COMPLETE`: Stan pasywny. Inicjalizacja zakończyła się pomyślnie. Komponent jest w pełni gotowy do rozpoczęcia pracy operacyjnej i czeka na finalny sygnał "start".
*   `STARTED`: Główny stan operacyjny. Komponent wykonuje swoje docelowe zadania biznesowe (np. steruje robotem, obsługuje interfejs użytkownika).
*   `STOPPING`: Stan przejściowy, aktywny. Komponent otrzymał polecenie zamknięcia. **Przestaje przyjmować nowe zadania i żądania**, ale kontynuuje i finalizuje te, które są już w toku. Po zakończeniu wszystkich bieżących operacji, komponent samodzielnie przechodzi w stan `STOPPED`. *Uwaga: Logika blokowania nowych zadań powinna być zunifikowana, idealnie dostarczona przez bazową klasę `EventListener`, aby zapewnić spójne zachowanie w całym systemie.*
*   `STOPPED`: Stan pasywny. Komponent zakończył wszystkie zadania, zwolnił zasoby i jest gotowy do bezpiecznego zakończenia procesu. Z tego stanu może zostać ponownie zainicjowany.
*   `FAULT`: Stan błędu. Komponent napotkał krytyczny błąd, który uniemożliwia mu dalszą pracę (np. nieudana inicjalizacja). Wymaga interwencji.

**Przejścia Między Stanami (Zdarzenia i Komendy):**

*   `[Uruchomienie procesu]` --- (Rejestracja w Orchestratorze) ---> **`READY`**
*   **`READY`** --- (Otrzymuje `CMD_INITIALIZE`) ---> **`INITIALIZING`**
*   **`INITIALIZING`** --- (Sukces) ---> **`INIT_COMPLETE`** (i wysyła `EVENT_INIT_SUCCESS`)
*   **`INITIALIZING`** --- (Błąd) ---> **`FAULT`** (i wysyła `EVENT_INIT_FAILURE`)
*   **`INIT_COMPLETE`** --- (Otrzymuje `CMD_START`) ---> **`STARTED`**
*   **`STARTED`** --- (Otrzymuje `CMD_GRACEFUL_STOP`) ---> **`STOPPING`**
*   **`STARTED`** --- (Wykrycie błędu krytycznego) ---> **`FAULT`** (i wysyła `EVENT_CRITICAL_ERROR`)
*   **`STOPPING`** --- (Zakończenie zadań) ---> **`STOPPED`** (i wysyła `EVENT_STOP_SUCCESS`)
*   **`STOPPED`** --- (Otrzymuje `CMD_INITIALIZE`) ---> **`INITIALIZING`**
*   **`FAULT`** --- (Otrzymuje `CMD_RESET`) ---> **`READY`**

#### 3.5.2. Przykładowy Scenariusz Uruchomienia (`system_startup.yaml`)

Poniższy scenariusz wykorzystuje opisaną powyżej maszynę stanów do przeprowadzenia zsynchronizowanego startu.

```yaml
- name: "Zsynchronizowana Sekwencja Uruchomieniowa Systemu"
  trigger:
    type: "all_components_ready"
    state: "READY" # Zaczynamy, gdy wszystkie komponenty są w stanie READY

  actions:
    - type: "log_event"
      level: "info"
      message: "Rozpoczynam sekwencję startową systemu. Wszystkie komponenty w stanie READY."

    # --- KROK 1: Inicjalizacja I/O i Supervisorów ---
    - type: "log_event"
      level: "info"
      message: "Krok 1: Wysyłanie polecenia CMD_INITIALIZE do IO i Supervisorów."
    - type: "send_command" # Bardziej generyczna nazwa akcji
      groups: ["base_io", "supervisors"]
      command: "CMD_INITIALIZE"
    - type: "wait_for_state"
      groups: ["base_io", "supervisors"]
      target_state: "INIT_COMPLETE"
      timeout: "60s"

    # --- KROK 2: Inicjalizacja KDS i Kiosk ---
    - type: "log_event"
      level: "info"
      message: "Krok 2: Wysyłanie polecenia CMD_INITIALIZE do KDS i Kiosk."
    - type: "send_command"
      groups: ["core_services", "user_interfaces"] # kds, kiosk
      command: "CMD_INITIALIZE"
    - type: "wait_for_state"
      groups: ["core_services", "user_interfaces"]
      target_state: "INIT_COMPLETE"
      timeout: "45s"

    # --- KROK 3: Inicjalizacja głównej logiki biznesowej ---
    - type: "log_event"
      level: "info"
      message: "Krok 3: Wysyłanie polecenia CMD_INITIALIZE do Munchies Algo."
    - type: "send_command"
      group: "main_logic" # munchies_lgo
      command: "CMD_INITIALIZE"
    - type: "wait_for_state"
      group: "main_logic"
      target_state: "INIT_COMPLETE"
      timeout: "30s"

    # --- KROK 4: Finalne uruchomienie systemu ---
    - type: "log_event"
      level: "info"
      message: "Wszystkie komponenty pomyślnie zainicjalizowane. Wysyłanie polecenia CMD_START."
    - type: "send_command"
      target: "@all"
      command: "CMD_START"
    - type: "wait_for_state"
      target: "@all"
      target_state: "STARTED"
      timeout: "10s"
    - type: "log_event"
      level: "success"
      message: "System w pełni operacyjny."
```

### 3.6. Scenariusze Systemowe: Kontrolowane Zamykanie (Graceful Shutdown)

Równie ważne jak zsynchronizowany start jest kontrolowane zamknięcie systemu, zwłaszcza w sytuacjach awaryjnych. Orchestrator realizuje ten proces w odwrotnej kolejności do startu, zapewniając, że żaden komponent nie zostanie zamknięty, zanim zależne od niego usługi nie zakończą bezpiecznie swojej pracy.

#### 3.6.1. Wykorzystanie Stanów FSM do Zamykania

Proces kontrolowanego zamykania opiera się na stanach `STOPPING` i `STOPPED`, które są częścią głównej maszyny stanów (sekcja 3.5.1). Kluczowe przejścia dla tego scenariusza to:

*   **`STARTED`** --- (Otrzymuje komendę `CMD_GRACEFUL_STOP` od Orchestratora) ---> **`STOPPING`**
    *   *Opis: Orchestrator rozpoczyna scenariusz zamykania. Komponent w stanie `STOPPING` przestaje przyjmować nowe zadania, ale dokańcza już rozpoczęte.*

*   **`STOPPING`** --- (Wewnętrzne zdarzenie: Wszystkie zadania zakończone) ---> **`STOPPED`**
    *   *Opis: Komponent kończy pracę, zwalnia zasoby i wysyła do Orchestratora zdarzenie `EVENT_STOP_SUCCESS`, potwierdzając gotowość do zamknięcia.*

#### 3.6.2. Scenariusz `graceful_shutdown.yaml`

**Zasada Działania:**

1.  **Wyzwalacz:** Scenariusz jest uruchamiany przez zewnętrzne zdarzenie, np. z dedykowanej usługi `ups_monitor`, która wykryła, że poziom baterii w UPS jest krytycznie niski.
2.  **Odwrócona Kolejność:** Kroki są wykonywane w kolejności odwrotnej do startu: najpierw zamykane są komponenty "frontowe" (przyjmujące zlecenia), a na samym końcu te "bazowe" (I/O).

```yaml
- name: "Kontrolowane Zamknięcie Systemu z Powodu Zaniku Zasilania"
  trigger:
    type: "event_received"
    source: "ups_monitor"
    event_type: "power_failure_imminent"
    # Można dodać warunek, np. gdy bateria UPS < 15%
    # data_condition: "battery_level < 15"

  actions:
    - type: "log_event"
      level: "critical"
      message: "ZANIK ZASILANIA! Rozpoczynam procedurę kontrolowanego zamknięcia systemu."

    # --- KROK 1: Zablokowanie nowych zadań ---
    # Zamykamy interfejsy i główną logikę, by nic nowego nie weszło do systemu.
    - type: "log_event"
      level: "info"
      message: "Krok 1: Zatrzymywanie przyjmowania nowych zadań (Munchies Algo, Kiosk)."
    - type: "send_command"
      groups: ["main_logic", "user_interfaces"]
      command: "CMD_GRACEFUL_STOP"
    # Czekamy aż zakończą bieżące zadania i przejdą w stan STOPPED.
    - type: "wait_for_state"
      groups: ["main_logic", "user_interfaces"]
      target_state: "STOPPED"
      timeout: "60s" # Dajemy czas na dokończenie operacji

    # --- KROK 2: Zatrzymanie usług podstawowych ---
    # Gdy logika biznesowa jest już zatrzymana, możemy wyłączyć KDS.
    - type: "log_event"
      level: "info"
      message: "Krok 2: Zatrzymywanie usług podstawowych (KDS)."
    - type: "send_command"
      group: "core_services"
      command: "CMD_GRACEFUL_STOP"
    - type: "wait_for_state"
      group: "core_services"
      target_state: "STOPPED"
      timeout: "30s"

    # --- KROK 3: Zatrzymanie Supervisorów i warstwy I/O ---
    # Na samym końcu zatrzymujemy komponenty niskopoziomowe.
    # To gwarantuje, że np. robot zdążył dojechać do pozycji bezpiecznej,
    # zanim straci komunikację.
    - type: "log_event"
      level: "info"
      message: "Krok 3: Zatrzymywanie Supervisorów i warstwy I/O."
    - type: "send_command"
      groups: ["supervisors", "base_io"]
      command: "CMD_GRACEFUL_STOP"
    - type: "wait_for_state"
      groups: ["supervisors", "base_io"]
      target_state: "STOPPED"
      timeout: "45s"

    # --- KROK 4: Finalne potwierdzenie ---
    - type: "log_event"
      level: "success"
      message: "System został bezpiecznie zatrzymany. Gotowy na odcięcie zasilania."
    - type: "send_notification"
      channel: "on_call_admins"
      subject: "[AUTO] System został bezpiecznie wyłączony"
      message: "Procedura graceful shutdown zakończona powodzeniem po wykryciu zaniku zasilania."
```

**Zalety i Kluczowe Aspekty:**

*   **Integralność Danych:** Zatrzymanie przyjmowania nowych zleceń jako pierwszy krok jest fundamentalne. Zapobiega to sytuacji, w której system przyjmuje zamówienie, którego nie jest w stanie zrealizować.
*   **Bezpieczeństwo Fizyczne:** W systemach sterujących robotyką (`supervisor_1`, `supervisor_2`), scenariusz zapewnia, że roboty mają czas na osiągnięcie bezpiecznej pozycji "domowej" przed utratą sterowania.
*   **Odporność na Błędy:** Jeśli któryś z komponentów nie przejdzie w stan `STOPPED` w zadanym czasie (`timeout`), Orchestrator może to zalogować i eskalować problem, zamiast czekać w nieskończoność.

## 4. Architektura Konfiguracji i Zależności

W systemie o zdefiniowanej i stabilnej liczbie komponentów (5-10), kluczem do niezawodności jest jawne i centralne zarządzanie konfiguracją. Zamiast dynamicznego odkrywania usług, przyjmujemy model statyczny, w którym cała topologia systemu, grupy funkcyjne i zależności są zdefiniowane w jednym, centralnym pliku konfiguracyjnym.

### 4.1. Centralny Plik Konfiguracyjny (`orchestrator_config.yaml`)

Orchestrator przy starcie wczytuje plik konfiguracyjny (np. `orchestrator_config.yaml`), który staje się "źródłem prawdy" o architekturze systemu. Definiuje on każdy komponent, jego przynależność do grup oraz jawne zależności.

**Przykładowa konfiguracja dla systemu:**

Na podstawie zdefiniowanych komponentów (`io`, `kds`, `kiosk`, `supervisor_1`, `supervisor_2`, `munchies_algo`), plik konfiguracyjny mógłby wyglądać następująco:

```yaml
# orchestrator_config.yaml
# Definicja wszystkich komponentów, ich grup i zależności.

components:
  # --- Warstwa podstawowa ---
  - id: "io"
    group: "base_io"
    # Brak zależności, to jest podstawa systemu

  # --- Główna logika biznesowa ---
  - id: "munchies_algo"
    group: "main_logic"
    depends_on:
      - "io" # Logika zależy od dostępu do warstwy I/O

  # --- Komponenty wykonawcze (Supervisory) ---
  - id: "supervisor_1"
    group: "supervisors"
    depends_on:
      - "io"
      - "munchies_algo"

  - id: "supervisor_2"
    group: "supervisors"
    depends_on:
      - "io"
      - "munchies_algo"

  # --- Usługi i interfejsy ---
  - id: "kds"
    group: "core_services"
    depends_on:
      - "munchies_algo"

  - id: "kiosk"
    group: "user_interfaces"
    depends_on:
      - "munchies_algo"
```

### 4.2. Korzyści z Zarządzania Zależnościami

Posiadanie jawnej mapy zależności pozwala Orchestratorowi na:
*   **Inteligentne uruchamianie:** Automatyczne uruchamianie komponentów w prawidłowej kolejności (najpierw `io`, potem `munchies_algo`, potem reszta).
*   **Inteligentne zamykanie:** Zamykanie systemu w odwróconej kolejności, co gwarantuje integralność operacji.
*   **Proaktywne zarządzanie awarią:** Jeśli `io` ulegnie awarii, Orchestrator natychmiast wie, że wszystkie inne komponenty są zagrożone i może podjąć skoordynowane działania, zamiast czekać na kaskadę błędów.

### 4.3. Centralne Zarządzanie Konfiguracją Komponentów

Orchestrator może również pełnić rolę centralnego punktu dystrybucji konfiguracji dla poszczególnych komponentów. Administrator może wgrać nową konfigurację (np. czasy operacji dla `munchies_algo`) do Orchestratora, a ten rozesłałby ją do odpowiedniej usługi za pomocą dedykowanego zdarzenia `update_configuration`. Upraszcza to zarządzanie systemem i eliminuje potrzebę restartowania usług po zmianie parametrów.

### 4.4. Panel Wizualizacyjny (Dashboard)

Istniejący `system_dashboard` może zostać rozbudowany, aby czerpać dane z Orchestratora i prezentować:
*   Graficzną mapę systemu z aktualnym stanem każdego komponentu.
*   Wykresy kluczowych metryk wydajnościowych.
*   Centralny dziennik zdarzeń i decyzji podjętych przez Orchestratora. 