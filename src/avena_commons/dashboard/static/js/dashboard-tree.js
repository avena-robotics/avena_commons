/**
 * ======================================
 * DASHBOARD TREE MODULE
 * Moduł do generowania i obsługi rozwijanego drzewa JSON
 * ======================================
 */

'use strict';

/**
 * Główny moduł drzewa JSON dla dashboard'a
 */
const DashboardTree = {
    
    /**
     * Generuje kompletny HTML dla drzewa JSON z kontenerem i stylami
     * @param {*} data - Dane do wyświetlenia jako drzewo
     * @return {string} Kompletny HTML drzewa
     */
    generateTreeHTML(data) {
        try {
            console.debug('🌳 Generowanie drzewa JSON...', typeof data);
            
            if (data === undefined) {
                return this.generateErrorHTML('Brak danych do wyświetlenia');
            }
            
            const treeHTML = this.createTreeView(data, 0);
            
            return `
                <div class="tree-container">
                    <div class="tree-content">
                        ${treeHTML}
                    </div>
                </div>
                <script>
                    setTimeout(() => window.DashboardTree?.initializeTreeInteractions?.(), 100);
                </script>
            `;
            
        } catch (error) {
            console.error('❌ Błąd generowania drzewa:', error);
            return this.generateErrorHTML(`Błąd generowania drzewa: ${error.message}`);
        }
    },
    
    /**
     * Tworzy widok drzewa dla dowolnego typu danych
     * @param {*} obj - Obiekt do wyświetlenia
     * @param {number} level - Poziom zagnieżdżenia
     * @return {string} HTML reprezentacja drzewa
     */
    createTreeView(obj, level = 0) {
        if (level > 10) {
            return `<span class="tree-depth-limit">... (maksymalna głębokość 10)</span>`;
        }
        
        if (typeof obj !== 'object' || obj === null) {
            return `<span class="tree-value">${this.formatValue(obj)}</span>`;
        }
        
        if (Array.isArray(obj)) {
            return this.createArrayView(obj, level);
        }
        
        return this.createObjectView(obj, level);
    },
    
    /**
     * Tworzy widok dla tablicy
     * @param {Array} arr - Tablica do wyświetlenia
     * @param {number} level - Poziom zagnieżdżenia
     * @return {string} HTML tablicy
     */
    createArrayView(arr, level) {
        if (arr.length === 0) {
            return '<span class="tree-value">[]</span>';
        }
        
        let html = '<div class="tree-array">';
        
        arr.forEach((item, index) => {
            const hasChildren = this.isComplexType(item);
            
            html += `
                <div class="tree-item" style="margin-left: ${level * 20}px;">
                    <div class="tree-node" ${hasChildren ? 'onclick="window.DashboardTree.toggleNode(this)"' : ''}>
                        ${hasChildren ? '<span class="tree-toggle"></span>' : '<span class="tree-bullet"></span>'}
                        <span class="tree-key">[${index}]:</span>
                        ${!hasChildren ? this.createTreeView(item, level + 1) : ''}
                    </div>
                    ${hasChildren ? `<div class="tree-children">${this.createTreeView(item, level + 1)}</div>` : ''}
                </div>
            `;
        });
        
        html += '</div>';
        return html;
    },
    
    /**
     * Tworzy widok dla obiektu
     * @param {Object} obj - Obiekt do wyświetlenia
     * @param {number} level - Poziom zagnieżdżenia
     * @return {string} HTML obiektu
     */
    createObjectView(obj, level) {
        const keys = Object.keys(obj);
        
        if (keys.length === 0) {
            return '<span class="tree-value">{}</span>';
        }
        
        let html = '<div class="tree-object">';
        
        keys.forEach(key => {
            const value = obj[key];
            const hasChildren = this.isComplexType(value);
            
            html += `
                <div class="tree-item" style="margin-left: ${level * 20}px;">
                    <div class="tree-node" ${hasChildren ? 'onclick="window.DashboardTree.toggleNode(this)"' : ''}>
                        ${hasChildren ? '<span class="tree-toggle"></span>' : '<span class="tree-bullet"></span>'}
                        <span class="tree-key">${this.escapeHTML(key)}:</span>
                        ${!hasChildren ? this.createTreeView(value, level + 1) : ''}
                    </div>
                    ${hasChildren ? `<div class="tree-children">${this.createTreeView(value, level + 1)}</div>` : ''}
                </div>
            `;
        });
        
        html += '</div>';
        return html;
    },
    
    /**
     * Formatuje wartości do wyświetlenia w drzewie
     * @param {*} value - Wartość do sformatowania
     * @return {string} Sformatowana wartość z odpowiednimi klasami CSS
     */
    formatValue(value) {
        if (value === null) return '<span class="null">null</span>';
        if (value === undefined) return '<span class="undefined">undefined</span>';
        if (typeof value === 'boolean') return `<span class="boolean">${value}</span>`;
        if (typeof value === 'number') return `<span class="number">${value}</span>`;
        if (typeof value === 'string') return `<span class="string">"${this.escapeHTML(value)}"</span>`;
        return `<span class="unknown">${this.escapeHTML(String(value))}</span>`;
    },
    
    /**
     * Przełącza stan węzła (rozwinięty/zwinięty)
     * @param {HTMLElement} nodeElement - Element węzła do przełączenia
     */
    toggleNode(nodeElement) {
        const treeItem = nodeElement.closest('.tree-item');
        if (!treeItem) return;
        
        treeItem.classList.toggle('collapsed');
        console.debug('🔄 Przełączono węzeł');
    },
    
    /**
     * Inicjalizuje interakcje dla wszystkich drzew na stronie
     */
    initializeTreeInteractions() {
        console.debug('🎯 Interakcje drzewa zainicjalizowane');
    },
    
    /**
     * Sprawdza czy wartość jest typu złożonego (obiekt/tablica)
     * @param {*} value - Wartość do sprawdzenia
     * @return {boolean} True jeśli typ złożony
     */
    isComplexType(value) {
        return value !== null && 
               (typeof value === 'object' || Array.isArray(value));
    },
    
    /**
     * Eskejpuje HTML w tekście
     * @param {string} text - Tekst do eskejpowania
     * @return {string} Eskejpowany tekst
     */
    escapeHTML(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
    
    /**
     * Generuje HTML komunikatu błędu
     * @param {string} message - Komunikat błędu
     * @return {string} HTML błędu
     */
    generateErrorHTML(message) {
        return `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle me-2"></i>
                <strong>Błąd wyświetlania drzewa:</strong> ${this.escapeHTML(message)}
            </div>
        `;
    }
};

// Udostępnij moduł globalnie
window.DashboardTree = DashboardTree;

console.info('📦 Moduł Dashboard Tree załadowany'); 