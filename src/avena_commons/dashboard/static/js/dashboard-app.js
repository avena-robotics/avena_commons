/**
 * ======================================
 * DASHBOARD APPLICATION MAIN MODULE
 * Główna logika aplikacji dashboard'a monitorującego serwisy
 * ======================================
 */

'use strict';

/**
 * Główna funkcja aplikacji Dashboard używana przez Alpine.js
 * @param {number} apiPort - Port API dla połączeń z backend'em
 * @return {Object} Obiekt stanu i metod aplikacji Alpine.js
 */
function dashboardApp(apiPort) {
    return {
        // ======================================
        // STAN APLIKACJI
        // ======================================
        
        /** @type {Object} Dane serwisów pobrane z API */
        services: {},
        
        /** @type {boolean} Flaga stanu ładowania danych */
        loading: false,
        
        /** @type {boolean} Czy auto-odświeżanie jest włączone */
        autoRefresh: true,
        
        /** @type {number|null} ID interwału auto-odświeżania */
        refreshInterval: null,
        
        /** @type {string} Tekst ostatniej aktualizacji */
        lastUpdate: '',
        
        /** @type {Object} Filtry wyszukiwania i statusu */
        filters: {
            search: '',
            status: ''
        },
        
        /** @type {Object} Dane modala */
        modal: {
            title: '',
            content: ''
        },
        
        /** @type {Object} Metryki systemu */
        metrics: {
            online: 0,
            offline: 0,
            waiting: 0,
            total: 0
        },

        // ======================================
        // INICJALIZACJA APLIKACJI
        // ======================================
        
        /**
         * Inicjalizuje aplikację dashboard'a
         * Wywoływana przez Alpine.js po zamontowaniu komponentu
         */
        init() {
            console.info('🚀 Inicjalizacja Dashboard App...');
            
            try {
                // Pierwsze pobranie danych
                this.refreshData();
                
                // Uruchomienie auto-odświeżania
                this.startAutoRefresh();
                
                // Nasłuchiwanie na zdarzenia błędów API
                this.setupErrorHandling();
                
                console.info('✅ Dashboard App zainicjalizowany pomyślnie');
            } catch (error) {
                console.error('❌ Błąd inicjalizacji Dashboard App:', error);
                this.showError('Błąd inicjalizacji aplikacji');
            }
        },

        // ======================================
        // ZARZĄDZANIE DANYMI
        // ======================================
        
        /**
         * Odświeża dane serwisów z API
         * @return {Promise<void>}
         */
        async refreshData() {
            this.loading = true;
            
            try {
                console.debug('📡 Pobieranie danych z API...');
                
                const response = await fetch(`http://localhost:${apiPort}/api/dashboard/status`, {
                    method: 'GET',
                    headers: {
                        'Accept': 'application/json',
                        'Cache-Control': 'no-cache'
                    },
                    // Timeout po 10 sekundach
                    signal: AbortSignal.timeout(10000)
                });
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const data = await response.json();
                
                // Walidacja otrzymanych danych
                if (typeof data !== 'object' || data === null) {
                    throw new Error('Nieprawidłowy format danych z API');
                }
                
                this.services = data;
                this.updateMetrics();
                this.updateLastUpdateTime();
                
                console.debug('✅ Dane pobrane pomyślnie:', Object.keys(data).length, 'serwisów');
                
            } catch (error) {
                console.error('❌ Błąd pobierania danych:', error);
                
                // Jeśli to błąd timeout lub sieci, pokaż odpowiedni komunikat
                if (error.name === 'AbortError') {
                    this.showError('Timeout połączenia z API (10s)');
                } else if (error.message.includes('fetch')) {
                    this.showError('Brak połączenia z serwerem API');
                } else {
                    this.showError(`Błąd API: ${error.message}`);
                }
                
            } finally {
                this.loading = false;
            }
        },
        
        /**
         * Aktualizuje metryki systemu na podstawie danych serwisów
         */
        updateMetrics() {
            const servicesList = Object.values(this.services);
            
            this.metrics.total = servicesList.length;
            this.metrics.online = servicesList.filter(s => s.status === 'connected').length;
            this.metrics.offline = servicesList.filter(s => 
                ['no_response', 'timeout'].includes(s.status)
            ).length;
            this.metrics.waiting = servicesList.filter(s => s.status === 'waiting').length;
            
            console.debug('📊 Metryki zaktualizowane:', this.metrics);
        },
        
        /**
         * Aktualizuje czas ostatniej aktualizacji
         */
        updateLastUpdateTime() {
            const now = new Date();
            this.lastUpdate = `Ostatnia aktualizacja: ${now.toLocaleTimeString('pl-PL')}`;
        },

        // ======================================
        // FILTROWANIE I WYSZUKIWANIE
        // ======================================
        
        /**
         * Computed property - zwraca przefiltrowane serwisy
         * @return {Array} Tablica [nazwa, dane] przefiltrowanych serwisów
         */
        get filteredServices() {
            return Object.entries(this.services).filter(([name, service]) => {
                // Filtr wyszukiwania - sprawdza nazwę serwisu (case-insensitive)
                const matchesSearch = !this.filters.search || 
                    name.toLowerCase().includes(this.filters.search.toLowerCase());
                
                // Filtr statusu - sprawdza czy status jest w wybranej grupie
                const matchesStatus = !this.filters.status || 
                    this.filters.status.split(',').includes(service.status);
                
                return matchesSearch && matchesStatus;
            });
        },

        // ======================================
        // FUNKCJE POMOCNICZE UI
        // ======================================
        
        /**
         * Zwraca czytelny tekst statusu serwisu
         * @param {string} status - Status serwisu
         * @return {string} Czytelny tekst statusu
         */
        getStatusText(status) {
            const statusTexts = {
                'connected': 'Online',
                'waiting': 'Oczekuje',
                'timeout': 'Timeout',
                'no_response': 'Brak odpowiedzi'
            };
            return statusTexts[status] || 'Nieznany';
        },
        
        /**
         * Zwraca klasę CSS dla karty serwisu na podstawie statusu
         * @param {Object} service - Dane serwisu
         * @return {Object} Obiekt z klasami CSS
         */
        getServiceCardClass(service) {
            return {
                'border-success': service.status === 'connected',
                'border-danger': ['no_response', 'timeout'].includes(service.status),
                'border-warning': service.status === 'waiting',
                'border-secondary': !['connected', 'no_response', 'timeout', 'waiting'].includes(service.status)
            };
        },
        
        /**
         * Zwraca klasę CSS dla badge'a statusu
         * @param {Object} service - Dane serwisu
         * @return {string} Klasa CSS dla badge'a
         */
        getStatusBadgeClass(service) {
            switch (service.status) {
                case 'connected': 
                    return 'bg-success';
                case 'waiting': 
                    return 'bg-warning text-dark';
                case 'timeout':
                case 'no_response': 
                    return 'bg-danger';
                default: 
                    return 'bg-secondary';
            }
        },
        
        /**
         * Zwraca ikonę Font Awesome dla statusu serwisu
         * @param {Object} service - Dane serwisu
         * @return {string} Klasy CSS ikony
         */
        getStatusIcon(service) {
            switch (service.status) {
                case 'connected':
                    return 'fas fa-check-circle';
                case 'waiting':
                    return 'fas fa-clock';
                case 'timeout':
                case 'no_response':
                    return 'fas fa-times-circle';
                default:
                    return 'fas fa-question-circle';
            }
        },
        
        /**
         * Formatuje datę do czytelnego formatu polskiego
         * @param {string|Date} dateString - Data do sformatowania
         * @return {string} Sformatowana data
         */
        formatDate(dateString) {
            if (!dateString) return 'Nigdy';
            
            try {
                const date = new Date(dateString);
                if (isNaN(date.getTime())) return 'Nieprawidłowa data';
                
                return date.toLocaleString('pl-PL', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
            } catch (error) {
                console.warn('Błąd formatowania daty:', dateString, error);
                return 'Błąd daty';
            }
        },
        
        /**
         * Sprawdza czy serwis ma dane do wyświetlenia
         * @param {Object} service - Dane serwisu
         * @return {boolean} True jeśli serwis ma dane
         */
        hasServiceData(service) {
            return service.data && 
                   typeof service.data === 'object' && 
                   Object.keys(service.data).length > 0;
        },
        
        /**
         * Zwraca liczbę kluczy danych serwisu
         * @param {Object} service - Dane serwisu
         * @return {number} Liczba kluczy
         */
        getDataKeysCount(service) {
            if (!this.hasServiceData(service)) return 0;
            return Object.keys(service.data).length;
        },

        // ======================================
        // OBSŁUGA MODALI
        // ======================================
        
        /**
         * Pokazuje modal ze szczegółami serwisu
         * @param {string} serviceName - Nazwa serwisu
         * @param {Object} service - Dane serwisu
         */
        showServiceDetails(serviceName, service) {
            this.modal.title = `🔍 Szczegóły: ${serviceName}`;
            this.modal.content = this.generateServiceDetailsHTML(serviceName, service);
            
            // Pokaż modal używając Bootstrap
            const modalElement = document.getElementById('detailsModal');
            const modal = new bootstrap.Modal(modalElement);
            modal.show();
            
            console.debug('📋 Pokazano szczegóły serwisu:', serviceName);
        },
        
        /**
         * Pokazuje modal z danymi stanu serwisu w formie drzewa
         * @param {string} serviceName - Nazwa serwisu
         * @param {Object} data - Dane stanu serwisu
         */
        showServiceData(serviceName, data) {
            this.modal.title = `📊 Dane stanu: ${serviceName}`;
            
            // Używamy funkcji z dashboard-tree.js do wygenerowania drzewa
            if (typeof window.DashboardTree !== 'undefined' && window.DashboardTree.generateTreeHTML) {
                this.modal.content = window.DashboardTree.generateTreeHTML(data);
            } else {
                console.warn('⚠️ Moduł DashboardTree nie został załadowany, używam fallback');
                this.modal.content = `
                    <div class="alert alert-warning">
                        <i class="fas fa-exclamation-triangle me-2"></i>
                        Moduł drzewa nie został załadowany. Dane wyświetlone jako JSON:
                    </div>
                    <pre class="bg-light p-3 rounded">${JSON.stringify(data, null, 2)}</pre>
                `;
            }
            
            // Pokaż modal
            const modalElement = document.getElementById('detailsModal');
            const modal = new bootstrap.Modal(modalElement);
            modal.show();
            
            console.debug('🌳 Pokazano drzewo danych serwisu:', serviceName);
        },
        
        /**
         * Generuje HTML dla szczegółów serwisu
         * @param {string} serviceName - Nazwa serwisu
         * @param {Object} service - Dane serwisu
         * @return {string} HTML szczegółów
         */
        generateServiceDetailsHTML(serviceName, service) {
            const details = [
                ['Nazwa serwisu', serviceName],
                ['Status', `<span class="badge ${this.getStatusBadgeClass(service)}">${this.getStatusText(service.status)}</span>`],
                ['Adres', service.address || 'Brak danych'],
                ['Online', service.online ? '✅ Tak' : '❌ Nie']
            ];
            
            // Dodaj opcjonalne pola jeśli istnieją
            if (service.last_response) {
                details.push(['Ostatnia odpowiedź', this.formatDate(service.last_response)]);
            }
            if (service.response_time_ms) {
                details.push(['Czas odpowiedzi', `${service.response_time_ms} ms`]);
            }
            if (service.elapsed_seconds) {
                details.push(['Czas oczekiwania', `${service.elapsed_seconds.toFixed(2)} s`]);
            }
            if (service.timeout_threshold) {
                details.push(['Próg timeout', `${service.timeout_threshold} s`]);
            }
            if (service.event_id) {
                details.push(['ID zdarzenia', service.event_id]);
            }
            
            const rows = details.map(([label, value]) => 
                `<tr><td><strong>${label}:</strong></td><td>${value}</td></tr>`
            ).join('');
            
            return `
                <div class="table-responsive">
                    <table class="table table-striped service-details-table">
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            `;
        },

        // ======================================
        // AUTO-ODŚWIEŻANIE
        // ======================================
        
        /**
         * Konfiguruje system auto-odświeżania
         */
        startAutoRefresh() {
            // Obserwuj zmiany w autoRefresh
            this.$watch('autoRefresh', (value) => {
                if (value) {
                    console.info('▶️ Auto-odświeżanie włączone (co 5s)');
                    this.refreshInterval = setInterval(() => {
                        this.refreshData();
                    }, 5000);
                } else {
                    console.info('⏸️ Auto-odświeżanie wyłączone');
                    if (this.refreshInterval) {
                        clearInterval(this.refreshInterval);
                        this.refreshInterval = null;
                    }
                }
            });
            
            // Uruchom od razu jeśli autoRefresh jest włączony
            if (this.autoRefresh) {
                this.refreshInterval = setInterval(() => {
                    this.refreshData();
                }, 5000);
            }
        },

        // ======================================
        // OBSŁUGA BŁĘDÓW
        // ======================================
        
        /**
         * Konfiguruje obsługę błędów aplikacji
         */
        setupErrorHandling() {
            // Obsługa błędów fetch globalnie
            window.addEventListener('unhandledrejection', (event) => {
                console.error('Nieobsłużony błąd Promise:', event.reason);
                this.showError('Wystąpił nieoczekiwany błąd aplikacji');
            });
        },
        
        /**
         * Pokazuje komunikat błędu użytkownikowi
         * @param {string} message - Treść błędu
         */
        showError(message) {
            // Jeśli dostępny jest system toast notifications, użyj go
            if (typeof window.DashboardUtils !== 'undefined' && window.DashboardUtils.showToast) {
                window.DashboardUtils.showToast(message, 'error');
            } else {
                // Fallback do console.error
                console.error('🚨 Błąd aplikacji:', message);
                
                // Opcjonalnie możesz dodać prostą notyfikację w UI
                // np. przez dodanie elementu do DOM
            }
        }
    };
}

// ======================================
// KOMPONENT ZEGARA (Alpine.js)
// ======================================

/**
 * Inicjalizuje komponenty pomocnicze gdy Alpine.js jest gotowy
 */
document.addEventListener('alpine:init', () => {
    console.info('🕐 Inicjalizacja komponentu zegara...');
    
    Alpine.data('clock', () => ({
        /** @type {string} Aktualny czas sformatowany */
        currentTime: new Date().toLocaleTimeString('pl-PL'),
        
        /**
         * Inicjalizuje zegar z aktualizacją co sekundę
         */
        init() {
            // Aktualizuj czas co sekundę
            setInterval(() => {
                this.currentTime = new Date().toLocaleTimeString('pl-PL', {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit'
                });
            }, 1000);
            
            console.debug('✅ Komponent zegara zainicjalizowany');
        }
    }));
});

// ======================================
// EKSPORT GLOBALNY
// ======================================

// Udostępnij funkcję globalnie dla użycia w template
window.dashboardApp = dashboardApp;

console.info('📦 Moduł Dashboard App załadowany'); 