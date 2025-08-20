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
    },

    /**
     * Zapisuje aktualny stan drzewa (rozwinięte węzły, scroll)
     * @param {HTMLElement} container - Kontener drzewa
     * @return {Object} Obiekt ze stanem drzewa
     */
    saveTreeState(container) {
        const state = {
            expandedNodes: [],
            scrollTop: 0,
            scrollLeft: 0
        };

        try {
            // Zapisz pozycję scrolla
            const modalBody = container.closest('.modal-body');
            if (modalBody) {
                state.scrollTop = modalBody.scrollTop;
                state.scrollLeft = modalBody.scrollLeft;
            }

            // Znajdź wszystkie rozwinięte węzły i zapisz ich ścieżki
            const expandedItems = container.querySelectorAll('.tree-item:not(.collapsed)');
            expandedItems.forEach(item => {
                const path = this.getNodePath(item);
                if (path) {
                    state.expandedNodes.push(path);
                }
            });

            console.debug('💾 Zapisano stan drzewa:', state);
            return state;

        } catch (error) {
            console.warn('⚠️ Błąd zapisywania stanu drzewa:', error);
            return state;
        }
    },

    /**
     * Przywraca zapisany stan drzewa
     * @param {HTMLElement} container - Kontener drzewa  
     * @param {Object} state - Zapisany stan drzewa
     */
    restoreTreeState(container, state) {
        if (!state || !container) return;

        try {
            // Przywróć stan rozwinięcia węzłów
            state.expandedNodes.forEach(path => {
                const node = this.findNodeByPath(container, path);
                if (node) {
                    node.classList.remove('collapsed');
                }
            });

            // Przywróć pozycję scrolla z małym opóźnieniem (żeby DOM się zaktualizował)
            setTimeout(() => {
                const modalBody = container.closest('.modal-body');
                if (modalBody && (state.scrollTop > 0 || state.scrollLeft > 0)) {
                    modalBody.scrollTop = state.scrollTop;
                    modalBody.scrollLeft = state.scrollLeft;
                }
            }, 50);

            console.debug('♻️ Przywrócono stan drzewa:', state);

        } catch (error) {
            console.warn('⚠️ Błąd przywracania stanu drzewa:', error);
        }
    },

    /**
     * Generuje ścieżkę do węzła w drzewie na podstawie kluczy/indeksów
     * @param {HTMLElement} treeItem - Element węzła drzewa
     * @return {string|null} Ścieżka do węzła
     */
    getNodePath(treeItem) {
        const path = [];
        let current = treeItem;

        while (current && current.classList.contains('tree-item')) {
            const keyElement = current.querySelector('.tree-key');
            if (keyElement) {
                let key = keyElement.textContent.replace(':', '').trim();
                // Dla tablic usuń nawiasy kwadratowe
                if (key.startsWith('[') && key.endsWith(']')) {
                    key = key.slice(1, -1);
                }
                path.unshift(key);
            }
            
            // Przejdź do rodzica
            current = current.parentElement?.closest('.tree-item');
        }

        return path.length > 0 ? path.join('.') : null;
    },

    /**
     * Znajduje węzeł drzewa na podstawie ścieżki
     * @param {HTMLElement} container - Kontener drzewa
     * @param {string} path - Ścieżka do węzła
     * @return {HTMLElement|null} Znaleziony węzeł
     */
    findNodeByPath(container, path) {
        const parts = path.split('.');
        let current = container;

        for (const part of parts) {
            const items = current.querySelectorAll(':scope > .tree-object > .tree-item, :scope > .tree-array > .tree-item');
            let found = false;

            for (const item of items) {
                const keyElement = item.querySelector('.tree-key');
                if (keyElement) {
                    let key = keyElement.textContent.replace(':', '').trim();
                    // Dla tablic usuń nawiasy kwadratowe
                    if (key.startsWith('[') && key.endsWith(']')) {
                        key = key.slice(1, -1);
                    }
                    
                    if (key === part) {
                        current = item;
                        found = true;
                        break;
                    }
                }
            }

            if (!found) {
                return null;
            }
        }

        return current;
    },

    /**
     * Inteligentnie aktualizuje zawartość drzewa zachowując stan
     * @param {HTMLElement} container - Kontener drzewa
     * @param {*} newData - Nowe dane do wyświetlenia
     */
    updateTreeContent(container, newData) {
        if (!container) return;

        try {
            // Zapisz aktualny stan
            const treeContainer = container.querySelector('.tree-container');
            const savedState = treeContainer ? this.saveTreeState(treeContainer) : null;

            // Wygeneruj nową zawartość
            const newHTML = this.generateTreeHTML(newData);
            
            // Zastąp zawartość
            container.innerHTML = newHTML;

            // Przywróć stan po krótkim opóźnieniu
            if (savedState) {
                setTimeout(() => {
                    const newTreeContainer = container.querySelector('.tree-container');
                    if (newTreeContainer) {
                        this.restoreTreeState(newTreeContainer, savedState);
                    }
                }, 100);
            }

            console.debug('🔄 Zaktualizowano zawartość drzewa z zachowaniem stanu');

        } catch (error) {
            console.error('❌ Błąd aktualizacji drzewa:', error);
            // Fallback - zwykła regeneracja
            container.innerHTML = this.generateTreeHTML(newData);
        }
    }
};

// Udostępnij moduł globalnie
window.DashboardTree = DashboardTree;

console.info('📦 Moduł Dashboard Tree załadowany'); 