/**
 * ======================================
 * DASHBOARD UTILITIES MODULE
 * Rozszerzone funkcje pomocnicze dla dashboard'a
 * ======================================
 */

'use strict';

/**
 * Moduł funkcji pomocniczych dla dashboard'a
 */
const DashboardUtils = {
    
    // ======================================
    // NOTYFIKACJE TOAST
    // ======================================
    
    /**
     * Pokazuje notyfikację toast
     * @param {string} message - Treść wiadomości
     * @param {string} type - Typ notyfikacji (success, error, warning, info)
     * @param {number} duration - Czas wyświetlania w ms (0 = nie znika automatycznie)
     */
    showToast(message, type = 'info', duration = 5000) {
        console.log(`Toast [${type}]: ${message}`);
        
        // Znajdź lub utwórz kontener toast'ów
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = this.createToastContainer();
            document.body.appendChild(toastContainer);
        }
        
        // Utwórz element toast
        const toast = this.createToastElement(message, type);
        toastContainer.appendChild(toast);
        
        // Animacja pojawiania się
        requestAnimationFrame(() => {
            toast.classList.add('show');
        });
        
        // Auto-usuwanie
        if (duration > 0) {
            setTimeout(() => {
                this.removeToast(toast);
            }, duration);
        }
        
        return toast;
    },
    
    /**
     * Tworzy kontener dla toast'ów
     * @return {HTMLElement} Element kontenera
     */
    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        return container;
    },
    
    /**
     * Tworzy element toast
     * @param {string} message - Treść wiadomości
     * @param {string} type - Typ toast'a
     * @return {HTMLElement} Element toast
     */
    createToastElement(message, type) {
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${this.getToastBootstrapClass(type)} border-0`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
        toast.setAttribute('aria-atomic', 'true');
        
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <i class="${this.getToastIcon(type)} me-2"></i>
                    ${this.escapeHTML(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" 
                        onclick="window.DashboardUtils.removeToast(this.closest('.toast'))"></button>
            </div>
        `;
        
        return toast;
    },
    
    /**
     * Usuwa toast z animacją
     * @param {HTMLElement} toast - Element toast do usunięcia
     */
    removeToast(toast) {
        if (!toast) return;
        
        toast.classList.remove('show');
        toast.classList.add('hide');
        
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 500);
    },
    
    /**
     * Zwraca klasę Bootstrap dla typu toast'a
     * @param {string} type - Typ toast'a
     * @return {string} Klasa Bootstrap
     */
    getToastBootstrapClass(type) {
        const classes = {
            'success': 'success',
            'error': 'danger',
            'warning': 'warning',
            'info': 'info'
        };
        return classes[type] || 'info';
    },
    
    /**
     * Zwraca ikonę Font Awesome dla typu toast'a
     * @param {string} type - Typ toast'a
     * @return {string} Klasa ikony
     */
    getToastIcon(type) {
        const icons = {
            'success': 'fas fa-check-circle',
            'error': 'fas fa-exclamation-triangle',
            'warning': 'fas fa-exclamation-circle',
            'info': 'fas fa-info-circle'
        };
        return icons[type] || 'fas fa-info-circle';
    },

    // ======================================
    // FORMATOWANIE DANYCH
    // ======================================
    
    /**
     * Formatuje liczby z separatorem tysięcy
     * @param {number} num - Liczba do sformatowania
     * @param {Object} options - Opcje formatowania
     * @return {string} Sformatowana liczba
     */
    formatNumber(num, options = {}) {
        if (typeof num !== 'number' || isNaN(num)) {
            return 'N/A';
        }
        
        const defaultOptions = {
            locale: 'pl-PL',
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        };
        
        const finalOptions = { ...defaultOptions, ...options };
        
        return new Intl.NumberFormat(finalOptions.locale, finalOptions).format(num);
    },
    
    /**
     * Formatuje rozmiar pliku w czytelny format
     * @param {number} bytes - Rozmiar w bajtach
     * @param {number} decimals - Liczba miejsc po przecinku
     * @return {string} Sformatowany rozmiar
     */
    formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 B';
        if (typeof bytes !== 'number' || bytes < 0) return 'N/A';
        
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
        
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    },
    
    /**
     * Formatuje czas w czytelny format
     * @param {number} seconds - Czas w sekundach
     * @return {string} Sformatowany czas
     */
    formatDuration(seconds) {
        if (typeof seconds !== 'number' || seconds < 0) return 'N/A';
        
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        
        if (hours > 0) {
            return `${hours}h ${minutes}m ${secs}s`;
        } else if (minutes > 0) {
            return `${minutes}m ${secs}s`;
        } else {
            return `${secs}s`;
        }
    },
    
    /**
     * Formatuje procenty
     * @param {number} value - Wartość (0-1 lub 0-100)
     * @param {boolean} isDecimal - Czy wartość jest w formacie dziesiętnym (0-1)
     * @return {string} Sformatowane procenty
     */
    formatPercentage(value, isDecimal = true) {
        if (typeof value !== 'number' || isNaN(value)) return 'N/A';
        
        const percentage = isDecimal ? value * 100 : value;
        return `${percentage.toFixed(1)}%`;
    },

    // ======================================
    // WALIDACJA DANYCH
    // ======================================
    
    /**
     * Sprawdza czy wartość jest prawidłowym URL
     * @param {string} url - URL do sprawdzenia
     * @return {boolean} True jeśli URL jest prawidłowy
     */
    isValidUrl(url) {
        if (typeof url !== 'string') return false;
        
        try {
            new URL(url);
            return true;
        } catch {
            return false;
        }
    },
    
    /**
     * Sprawdza czy wartość jest prawidłowym email
     * @param {string} email - Email do sprawdzenia
     * @return {boolean} True jeśli email jest prawidłowy
     */
    isValidEmail(email) {
        if (typeof email !== 'string') return false;
        
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        return emailRegex.test(email);
    },
    
    /**
     * Sprawdza czy wartość jest prawidłowym numerem IP
     * @param {string} ip - Adres IP do sprawdzenia
     * @return {boolean} True jeśli IP jest prawidłowy
     */
    isValidIP(ip) {
        if (typeof ip !== 'string') return false;
        
        const ipRegex = /^(\d{1,3}\.){3}\d{1,3}$/;
        if (!ipRegex.test(ip)) return false;
        
        const parts = ip.split('.');
        return parts.every(part => {
            const num = parseInt(part, 10);
            return num >= 0 && num <= 255;
        });
    },

    // ======================================
    // MANIPULACJA DOM
    // ======================================
    
    /**
     * Bezpiecznie eskejpuje HTML
     * @param {string} text - Tekst do eskejpowania
     * @return {string} Eskejpowany tekst
     */
    escapeHTML(text) {
        if (typeof text !== 'string') return String(text);
        
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
    
    /**
     * Tworzy element HTML z atrybutami
     * @param {string} tag - Nazwa tagu
     * @param {Object} attributes - Atrybuty elementu
     * @param {string} content - Zawartość elementu
     * @return {HTMLElement} Utworzony element
     */
    createElement(tag, attributes = {}, content = '') {
        const element = document.createElement(tag);
        
        // Ustaw atrybuty
        Object.entries(attributes).forEach(([key, value]) => {
            if (key === 'className') {
                element.className = value;
            } else if (key === 'style' && typeof value === 'object') {
                Object.assign(element.style, value);
            } else {
                element.setAttribute(key, value);
            }
        });
        
        // Ustaw zawartość
        if (content) {
            element.innerHTML = content;
        }
        
        return element;
    },
    
    /**
     * Znajduje element po selektorze z timeout
     * @param {string} selector - Selektor CSS
     * @param {number} timeout - Timeout w ms
     * @return {Promise<HTMLElement>} Element lub null
     */
    waitForElement(selector, timeout = 5000) {
        return new Promise((resolve) => {
            const element = document.querySelector(selector);
            
            if (element) {
                resolve(element);
                return;
            }
            
            const observer = new MutationObserver(() => {
                const element = document.querySelector(selector);
                if (element) {
                    observer.disconnect();
                    resolve(element);
                }
            });
            
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
            
            // Timeout
            setTimeout(() => {
                observer.disconnect();
                resolve(null);
            }, timeout);
        });
    },

    // ======================================
    // OBSŁUGA LOKALNEGO STORAGE
    // ======================================
    
    /**
     * Zapisuje dane do localStorage z obsługą błędów
     * @param {string} key - Klucz
     * @param {*} value - Wartość do zapisania
     * @return {boolean} True jeśli sukces
     */
    saveToStorage(key, value) {
        try {
            const jsonValue = JSON.stringify(value);
            localStorage.setItem(key, jsonValue);
            return true;
        } catch (error) {
            console.warn('Błąd zapisu do localStorage:', error);
            return false;
        }
    },
    
    /**
     * Odczytuje dane z localStorage z obsługą błędów
     * @param {string} key - Klucz
     * @param {*} defaultValue - Wartość domyślna
     * @return {*} Odczytana wartość lub domyślna
     */
    loadFromStorage(key, defaultValue = null) {
        try {
            const item = localStorage.getItem(key);
            return item ? JSON.parse(item) : defaultValue;
        } catch (error) {
            console.warn('Błąd odczytu z localStorage:', error);
            return defaultValue;
        }
    },
    
    /**
     * Usuwa klucz z localStorage
     * @param {string} key - Klucz do usunięcia
     * @return {boolean} True jeśli sukces
     */
    removeFromStorage(key) {
        try {
            localStorage.removeItem(key);
            return true;
        } catch (error) {
            console.warn('Błąd usuwania z localStorage:', error);
            return false;
        }
    },

    // ======================================
    // FUNKCJE CZASOWE
    // ======================================
    
    /**
     * Debounce funkcji - opóźnia wykonanie
     * @param {Function} func - Funkcja do wykonania
     * @param {number} wait - Czas oczekiwania w ms
     * @return {Function} Debounced funkcja
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },
    
    /**
     * Throttle funkcji - ogranicza częstotliwość wykonania
     * @param {Function} func - Funkcja do wykonania
     * @param {number} limit - Limit czasu w ms
     * @return {Function} Throttled funkcja
     */
    throttle(func, limit) {
        let inThrottle;
        return function executedFunction(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    },

    // ======================================
    // EKSPORT STARYCH FUNKCJI (KOMPATYBILNOŚĆ)
    // ======================================
    
    /**
     * Stara funkcja showToast dla kompatybilności wstecznej
     * @deprecated Użyj DashboardUtils.showToast() zamiast tego
     */
    showToast_legacy(message, type = 'info') {
        return this.showToast(message, type);
    },
    
    /**
     * Stara funkcja formatNumber dla kompatybilności wstecznej
     * @deprecated Użyj DashboardUtils.formatNumber() zamiast tego
     */
    formatNumber_legacy(num) {
        return this.formatNumber(num);
    }
};

// ======================================
// EKSPORT GLOBALNY
// ======================================

// Zachowaj kompatybilność z poprzednią wersją
window.DashboardUtils = DashboardUtils;

// Eksportuj też stare funkcje dla kompatybilności
window.showToast = DashboardUtils.showToast.bind(DashboardUtils);
window.formatNumber = DashboardUtils.formatNumber.bind(DashboardUtils);

console.info('📦 Moduł Dashboard Utils załadowany z', Object.keys(DashboardUtils).length, 'funkcjami'); 