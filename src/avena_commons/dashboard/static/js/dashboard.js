/**
 * ======================================
 * DASHBOARD LEGACY COMPATIBILITY MODULE
 * Moduł zachowania kompatybilności z poprzednimi wersjami dashboard'a
 * ======================================
 */

'use strict';

/**
 * Legacy funkcje dashboard'a dla zachowania kompatybilności wstecznej
 * 
 * UWAGA: Ten plik zapewnia kompatybilność z poprzednimi wersjami.
 * Dla nowych implementacji użyj bezpośrednio modułów:
 * - dashboard-app.js (główna logika aplikacji)
 * - dashboard-tree.js (drzewo JSON) 
 * - dashboard-utils.js (funkcje pomocnicze)
 */

// ======================================
// SPRAWDZENIE DOSTĘPNOŚCI NOWYCH MODUŁÓW
// ======================================

/**
 * Sprawdza czy nowe moduły są załadowane
 * @return {Object} Status załadowania modułów
 */
function checkModulesAvailability() {
    const modules = {
        dashboardApp: typeof window.dashboardApp === 'function',
        dashboardTree: typeof window.DashboardTree === 'object',
        dashboardUtils: typeof window.DashboardUtils === 'object'
    };
    
    console.debug('📊 Status modułów Dashboard:', modules);
    return modules;
}

// ======================================
// LEGACY TOAST NOTIFICATIONS
// ======================================

/**
 * Legacy helper funkcja dla toast notifications
 * @deprecated Użyj DashboardUtils.showToast() bezpośrednio
 * @param {string} message - Treść wiadomości
 * @param {string} type - Typ notyfikacji
 */
function showToast(message, type = 'info') {
    console.warn('⚠️ Używasz przestarzałej funkcji showToast(). Przejdź na DashboardUtils.showToast()');
    
    if (typeof window.DashboardUtils !== 'undefined' && window.DashboardUtils.showToast) {
        return window.DashboardUtils.showToast(message, type);
    } else {
        // Fallback dla braku nowego modułu
        console.log(`Legacy Toast [${type}]: ${message}`);
        
        // Prostą implementacja fallback
        if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            // Użyj Bootstrap toast jeśli dostępny
            const toastHTML = `
                <div class="toast align-items-center text-white bg-${type === 'error' ? 'danger' : type}" role="alert">
                    <div class="d-flex">
                        <div class="toast-body">${message}</div>
                        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                    </div>
                </div>
            `;
            
            // TODO: Implement simple Bootstrap toast fallback
            console.info('Bootstrap toast fallback:', message);
        } else {
            // Najproszty fallback - alert
            alert(`${type.toUpperCase()}: ${message}`);
        }
    }
}

// ======================================
// LEGACY NUMBER FORMATTING
// ======================================

/**
 * Legacy helper funkcja dla formatowania liczb
 * @deprecated Użyj DashboardUtils.formatNumber() bezpośrednio
 * @param {number} num - Liczba do sformatowania
 * @return {string} Sformatowana liczba
 */
function formatNumber(num) {
    console.warn('⚠️ Używasz przestarzałej funkcji formatNumber(). Przejdź na DashboardUtils.formatNumber()');
    
    if (typeof window.DashboardUtils !== 'undefined' && window.DashboardUtils.formatNumber) {
        return window.DashboardUtils.formatNumber(num);
    } else {
        // Fallback dla braku nowego modułu
        if (typeof num !== 'number' || isNaN(num)) {
            return 'N/A';
        }
        
        try {
            return new Intl.NumberFormat('pl-PL').format(num);
        } catch (error) {
            console.warn('Błąd formatowania liczby:', error);
            return num.toString();
        }
    }
}

// ======================================
// LEGACY DASHBOARD INITIALIZATION
// ======================================

/**
 * Legacy funkcja inicjalizacji dashboard'a
 * @deprecated Użyj dashboardApp() bezpośrednio w Alpine.js
 * @param {number} apiPort - Port API
 */
function initializeDashboard(apiPort) {
    console.warn('⚠️ Używasz przestarzałej funkcji initializeDashboard(). Przejdź na dashboardApp() w Alpine.js');
    
    const modules = checkModulesAvailability();
    
    if (!modules.dashboardApp) {
        console.error('❌ Moduł dashboard-app.js nie jest załadowany. Nie można zainicjalizować dashboard\'a');
        showToast('Błąd: Brak głównego modułu dashboard\'a', 'error');
        return null;
    }
    
    try {
        // Próbuj użyć nowego modułu
        const app = window.dashboardApp(apiPort);
        console.info('✅ Dashboard zainicjalizowany z nowym modułem');
        return app;
    } catch (error) {
        console.error('❌ Błąd inicjalizacji dashboard\'a:', error);
        showToast('Błąd inicjalizacji dashboard\'a', 'error');
        return null;
    }
}

// ======================================
// MIGRATION HELPERS
// ======================================

/**
 * Sprawdza kompatybilność i pokazuje ostrzeżenia migracji
 */
function checkCompatibilityAndWarn() {
    const modules = checkModulesAvailability();
    const missingModules = Object.entries(modules)
        .filter(([name, available]) => !available)
        .map(([name]) => name);
    
    if (missingModules.length > 0) {
        console.warn('⚠️ Brakujące moduły Dashboard:', missingModules);
        console.warn('📖 Sprawdź czy wszystkie pliki JS są prawidłowo załadowane:');
        console.warn('   - dashboard-app.js (główna logika)');
        console.warn('   - dashboard-tree.js (drzewo JSON)');
        console.warn('   - dashboard-utils.js (funkcje pomocnicze)');
    }
    
    // Sprawdź czy używane są przestarzałe funkcje
    if (typeof window.showToast === 'function' && window.showToast === showToast) {
        console.info('ℹ️ Używasz przestarzałych funkcji. Rozważ migrację na nowe moduły.');
    }
}

/**
 * Pokazuje przewodnik migracji
 */
function showMigrationGuide() {
    console.group('📚 Przewodnik migracji Dashboard');
    console.info('Stare użycie → Nowe użycie:');
    console.info('showToast(msg, type) → DashboardUtils.showToast(msg, type)');
    console.info('formatNumber(num) → DashboardUtils.formatNumber(num)');
    console.info('initializeDashboard(port) → x-data="dashboardApp(port)" w HTML');
    console.info('Więcej informacji w dokumentacji nowych modułów.');
    console.groupEnd();
}

// ======================================
// POLYFILLS I FALLBACKS
// ======================================

/**
 * Polyfill dla AbortSignal.timeout jeśli nie jest dostępny
 */
if (typeof AbortSignal !== 'undefined' && !AbortSignal.timeout) {
    AbortSignal.timeout = function(ms) {
        const controller = new AbortController();
        setTimeout(() => controller.abort(), ms);
        return controller.signal;
    };
    console.debug('🔧 Dodano polyfill dla AbortSignal.timeout');
}

/**
 * Sprawdza dostępność wymaganych API
 */
function checkBrowserSupport() {
    const features = {
        fetch: typeof fetch !== 'undefined',
        promises: typeof Promise !== 'undefined',
        localStorage: typeof localStorage !== 'undefined',
        css: typeof CSS !== 'undefined' && CSS.supports && CSS.supports('display', 'grid')
    };
    
    const unsupported = Object.entries(features)
        .filter(([feature, supported]) => !supported)
        .map(([feature]) => feature);
    
    if (unsupported.length > 0) {
        console.warn('⚠️ Nieobsługiwane funkcje przeglądarki:', unsupported);
        showToast('Twoja przeglądarka może nie obsługiwać wszystkich funkcji', 'warning');
    }
    
    return features;
}

// ======================================
// AUTO-INITIALIZATION
// ======================================

// Sprawdź kompatybilność po załadowaniu
document.addEventListener('DOMContentLoaded', () => {
    checkCompatibilityAndWarn();
    checkBrowserSupport();
    
    // Pokaż przewodnik migracji w konsoli deweloperskiej
    if (console.groupCollapsed) {
        console.groupCollapsed('📚 Dashboard - Przewodnik migracji');
        showMigrationGuide();
        console.groupEnd();
    }
});

// ======================================
// EKSPORT GLOBALNY (LEGACY)
// ======================================

// Eksportuj legacy funkcje globalnie dla kompatybilności wstecznej
window.showToast = showToast;
window.formatNumber = formatNumber;
window.initializeDashboard = initializeDashboard;
window.checkModulesAvailability = checkModulesAvailability;
window.showMigrationGuide = showMigrationGuide;

// Eksportuj również jako DashboardLegacy dla jasności
window.DashboardLegacy = {
    showToast,
    formatNumber,
    initializeDashboard,
    checkCompatibilityAndWarn,
    showMigrationGuide,
    checkBrowserSupport
};

console.info('📦 Moduł Dashboard Legacy Compatibility załadowany');
console.info('💡 TIP: Dla lepszej wydajności rozważ migrację na nowe moduły dashboard\'a'); 