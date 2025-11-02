import { ArgumentEditorPanel } from './ArgumentEditorPanel.js';

export class LeftRail {
    constructor(app) {
        this.app = app;
        this.isVisible = false;
        this.isCollapsed = true;
        this.entityTree = null;
        this.selectedEntityId = null;
        this.snippetCache = new Map();
        this.currentTab = 'entities';
        console.log('LeftRail constructor - isVisible:', this.isVisible);
        
        this.createElement();
        this.setupEventListeners();
        // Don't update entity tree on init - wait for it to be shown
        // this.updateEntityTree();
        
        // Initialize argument editor panel after DOM is ready
        try {
            this.argumentEditor = new ArgumentEditorPanel(app);
            const argsTab = document.querySelector('#arguments-tab');
            if (argsTab && this.argumentEditor && this.argumentEditor.getElement) {
                argsTab.appendChild(this.argumentEditor.getElement());
            }
        } catch (error) {
            console.warn('Could not initialize ArgumentEditorPanel:', error);
        }
    }
    
    createElement() {
        // Create the left rail container
        const leftRail = document.createElement('div');
        leftRail.id = 'left-rail';
        leftRail.className = 'left-rail';
        
        leftRail.innerHTML = `
            <div class="rail-trigger" id="rail-trigger">
                <div class="trigger-icon">⫸</div>
            </div>
            
            <div class="rail-content">
                <div class="rail-header">
                    <div class="rail-tabs">
                        <button class="tab-button active" data-tab="entities">Entities</button>
                        <button class="tab-button" data-tab="arguments">Arguments</button>
                    </div>
                    <div class="rail-controls">
                        <button id="refresh-index" class="icon-btn" title="Refresh Index">↻</button>
                        <button id="bulk-actions" class="icon-btn" title="Bulk Actions">⚙</button>
                        <button id="close-rail" class="close-rail-btn" title="Close">×</button>
                    </div>
                </div>
                
                <div class="tab-content active" id="entities-tab">
                    <div class="entity-search">
                        <input type="text" id="entity-search" placeholder="Search entities..." />
                    </div>
                    
                    <div class="entity-stats">
                        <div id="entity-count">0 entities</div>
                        <div id="index-status">Ready</div>
                    </div>
                    
                    <div class="entity-tree" id="entity-tree">
                        <div class="loading">Building entity index...</div>
                    </div>
                </div>
                
                <div class="tab-content" id="arguments-tab">
                    <!-- Argument editor content will be inserted here -->
                </div>
            </div>
            
            <div class="snippet-pane" id="snippet-pane" style="display: none;">
                <div class="snippet-header">
                    <h4 class="snippet-entity-name"></h4>
                    <button id="close-snippet" class="close-snippet-btn">×</button>
                </div>
                <div class="snippet-controls">
                    <button id="jump-to-mention" class="snippet-btn">Jump to First</button>
                </div>
                <div class="snippet-list" id="snippet-list">
                    <!-- Snippets will be populated here -->
                </div>
            </div>
        `;
        
        document.body.appendChild(leftRail);
        
        // Store references
        this.element = leftRail;
        this.trigger = leftRail.querySelector('#rail-trigger');
        this.content = leftRail.querySelector('.rail-content');
        this.snippetPane = leftRail.querySelector('#snippet-pane');
        
        console.log('LeftRail createElement - initial classes:', this.element.className);
        
        // Debug: Monitor class changes
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.attributeName === 'class') {
                    console.log('LeftRail class changed to:', this.element.className);
                    console.trace('Class change stack trace');
                }
            });
        });
        observer.observe(this.element, { attributes: true, attributeFilter: ['class'] });
        
        // Insert argument editor panel (defer until after setup)
        const argsTab = leftRail.querySelector('#arguments-tab');
        // Will be populated after argument editor is ready
    }
    
    setupEventListeners() {
        // Trigger hover/click - removed auto-show on hover to prevent unwanted opening
        // this.trigger.addEventListener('mouseenter', () => {
        //     if (!this.isVisible) {
        //         this.show();
        //     }
        // });
        
        this.trigger.addEventListener('click', () => {
            this.toggle();
        });
        
        // Close button
        const closeBtn = this.element.querySelector('#close-rail');
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.hide();
            });
        }
        
        // Tab switching
        this.element.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', () => {
                this.switchTab(button.dataset.tab);
            });
        });
        
        // Auto-hide on mouse leave (with delay)
        let hideTimeout;
        this.element.addEventListener('mouseleave', () => {
            hideTimeout = setTimeout(() => {
                if (!this.element.matches(':hover') && !this.isCollapsed) {
                    this.hide();
                }
            }, 1000);
        });
        
        this.element.addEventListener('mouseenter', () => {
            clearTimeout(hideTimeout);
        });
        
        // Search
        document.getElementById('entity-search').addEventListener('input', (e) => {
            this.filterEntities(e.target.value);
        });
        
        // Control buttons
        const refreshBtn = document.getElementById('refresh-index');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.refreshIndex();
            });
        }
        
        const bulkActionsBtn = document.getElementById('bulk-actions');
        if (bulkActionsBtn) {
            bulkActionsBtn.addEventListener('click', () => {
                this.showBulkActions();
            });
        }
        
        // Snippet pane
        const closeSnippetBtn = document.getElementById('close-snippet');
        if (closeSnippetBtn) {
            closeSnippetBtn.addEventListener('click', () => {
                this.hideSnippetPane();
            });
        }
        
        const jumpToMentionBtn = document.getElementById('jump-to-mention');
        if (jumpToMentionBtn) {
            jumpToMentionBtn.addEventListener('click', () => {
                this.jumpToFirstMention();
            });
        }
        
        
        // Listen for entity index updates
        document.addEventListener('entityIndexUpdated', () => {
            this.updateEntityTree();
        });
        
        // Handle entity selection from other components
        document.addEventListener('entitySelected', (e) => {
            this.selectEntity(e.detail.entityId);
        });
    }
    
    show() {
        console.log('LeftRail show() called');
        this.isVisible = true;
        this.element.classList.add('visible');
        this.trigger.querySelector('.trigger-icon').textContent = '⫷';
        
        // Update entity tree when showing
        if (!this.entityTree) {
            this.updateEntityTree();
        }
    }
    
    hide() {
        console.log('LeftRail hide() called');
        this.isVisible = false;
        this.element.classList.remove('visible');
        this.trigger.querySelector('.trigger-icon').textContent = '⫸';
        this.hideSnippetPane();
        console.log('LeftRail classes after hide:', this.element.className);
    }
    
    toggle() {
        if (this.isVisible) {
            this.hide();
        } else {
            this.show();
        }
    }
    
    async updateEntityTree() {
        console.log('[LeftRail] updateEntityTree called');
        if (!this.app.entityIndexer) {
            console.log('[LeftRail] No entityIndexer available');
            return;
        }
        
        const stats = this.app.entityIndexer.getIndexStats();
        console.log('[LeftRail] Entity stats:', stats);
        const entityTree = this.app.entityIndexer.getEntityTree();
        
        // Update stats
        document.getElementById('entity-count').textContent = 
            `${stats.totalEntities} entities`;
        
        document.getElementById('index-status').textContent = 
            stats.isIndexing ? 'Indexing...' : 'Ready';
        
        // Build tree HTML
        const treeContainer = document.getElementById('entity-tree');
        treeContainer.innerHTML = this.buildTreeHTML(entityTree);
        
        // Add event listeners to tree items
        this.setupTreeEventListeners();
        
        this.entityTree = entityTree;
    }
    
    buildTreeHTML(entityTree) {
        if (Object.keys(entityTree).length === 0) {
            return '<div class="empty-state">No entities found. Start typing to build the index.</div>';
        }
        
        let html = '<ul class="entity-type-list">';
        
        for (const [type, data] of Object.entries(entityTree)) {
            const displayType = this.capitalizeType(type);
            const isExpanded = this.isTypeExpanded(type);
            
            html += `
                <li class="entity-type ${isExpanded ? 'expanded' : 'collapsed'}" data-type="${type}">
                    <div class="type-header" data-type="${type}">
                        <span class="type-toggle">${isExpanded ? '▼' : '▶'}</span>
                        <span class="type-name">${displayType}</span>
                        <span class="type-count">(${data.count})</span>
                    </div>
                    <ul class="entity-list ${isExpanded ? 'visible' : 'hidden'}">
                        ${this.buildEntityListHTML(data.entities)}
                    </ul>
                </li>
            `;
        }
        
        html += '</ul>';
        return html;
    }
    
    buildEntityListHTML(entities) {
        return entities.map(entity => {
            const mentions = this.app.entityIndexer.getMentions(entity.id);
            const displayText = this.truncateText(entity.text, 30);
            
            return `
                <li class="entity-item" data-entity-id="${entity.id}">
                    <div class="entity-content">
                        <span class="entity-text" title="${entity.text}">${displayText}</span>
                        <span class="mention-count">(${mentions.length})</span>
                    </div>
                    <div class="entity-actions">
                        <button class="view-snippets" title="View Context">👁</button>
                    </div>
                </li>
            `;
        }).join('');
    }
    
    capitalizeType(type) {
        const typeMap = {
            person: 'People',
            organization: 'Organizations',
            phone: 'Phone Numbers',
            email: 'Email Addresses',
            url: 'URLs',
            footnote: 'Footnotes',
            heading: 'Headings',
            date: 'Dates',
            location: 'Locations',
            custom: 'Custom'
        };
        
        return typeMap[type] || type.charAt(0).toUpperCase() + type.slice(1);
    }
    
    truncateText(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength - 3) + '...';
    }
    
    isTypeExpanded(type) {
        // Default expanded types
        const defaultExpanded = ['person', 'organization'];
        const savedState = localStorage.getItem(`edith-rail-expanded-${type}`);
        
        if (savedState !== null) {
            return JSON.parse(savedState);
        }
        
        return defaultExpanded.includes(type);
    }
    
    saveTypeExpanded(type, expanded) {
        localStorage.setItem(`edith-rail-expanded-${type}`, JSON.stringify(expanded));
    }
    
    setupTreeEventListeners() {
        // Type toggle
        document.querySelectorAll('.type-header').forEach(header => {
            header.addEventListener('click', (e) => {
                const type = e.currentTarget.dataset.type;
                this.toggleType(type);
            });
        });
        
        // Entity item clicks
        document.querySelectorAll('.entity-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('view-snippets')) {
                    return; // Handle button clicks separately
                }
                
                const entityId = item.dataset.entityId;
                this.selectEntity(entityId);
            });
        });
        
        // Action buttons
        document.querySelectorAll('.view-snippets').forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const entityId = e.target.closest('.entity-item').dataset.entityId;
                this.showEntitySnippets(entityId);
            });
        });
        
        /* Bulk edit removed - AI handles bulk operations through natural commands
        document.querySelectorAll('.bulk-edit').forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const entityId = e.target.closest('.entity-item').dataset.entityId;
                this.bulkEditEntity(entityId);
            });
        });
        */
    }
    
    toggleType(type) {
        const typeElement = document.querySelector(`[data-type="${type}"]`);
        const entityList = typeElement.querySelector('.entity-list');
        const toggle = typeElement.querySelector('.type-toggle');
        
        const isExpanded = typeElement.classList.contains('expanded');
        
        if (isExpanded) {
            typeElement.classList.remove('expanded');
            typeElement.classList.add('collapsed');
            entityList.classList.remove('visible');
            entityList.classList.add('hidden');
            toggle.textContent = '▶';
        } else {
            typeElement.classList.remove('collapsed');
            typeElement.classList.add('expanded');
            entityList.classList.remove('hidden');
            entityList.classList.add('visible');
            toggle.textContent = '▼';
        }
        
        this.saveTypeExpanded(type, !isExpanded);
    }
    
    selectEntity(entityId) {
        // Update visual selection
        document.querySelectorAll('.entity-item.selected').forEach(item => {
            item.classList.remove('selected');
        });
        
        const entityItem = document.querySelector(`[data-entity-id="${entityId}"]`);
        if (entityItem) {
            entityItem.classList.add('selected');
        }
        
        this.selectedEntityId = entityId;
        
        // Dispatch selection event
        document.dispatchEvent(new CustomEvent('railEntitySelected', {
            detail: { entityId }
        }));
    }
    
    async showEntitySnippets(entityId) {
        const entity = this.app.entityIndexer.getEntityById(entityId);
        const mentions = this.app.entityIndexer.getMentions(entityId);
        
        if (!entity || mentions.length === 0) {
            return;
        }
        
        // Build snippets
        const snippets = await this.buildSnippets(entity, mentions);
        
        // Show snippet pane
        const snippetTitle = this.snippetPane.querySelector('.snippet-entity-name');
        const snippetList = document.getElementById('snippet-list');
        
        if (snippetTitle) {
            snippetTitle.textContent = `"${entity.text}" (${mentions.length} mentions)`;
        }
        
        if (snippetList) {
            snippetList.innerHTML = snippets;
        }
        
        this.snippetPane.style.display = 'block';
        this.snippetPane.classList.add('visible');
        this.selectedEntityId = entityId;
    }
    
    async buildSnippets(entity, mentions) {
        const editor = document.getElementById('main-text-editor');
        if (!editor) return 'No editor found';
        
        const text = editor.value;
        const snippets = [];
        
        for (const mention of mentions.slice(0, 5)) { // Show max 5 mentions
            const snippet = this.extractSnippet(text, mention.offset, entity.text.length);
            snippets.push(`
                <div class="snippet-item" data-offset="${mention.offset}">
                    <div class="snippet-text">${snippet.html}</div>
                    <div class="snippet-meta">Position ${mention.offset}</div>
                </div>
            `);
        }
        
        if (mentions.length > 5) {
            snippets.push(`<div class="snippet-more">...and ${mentions.length - 5} more</div>`);
        }
        
        return snippets.join('');
    }
    
    extractSnippet(text, offset, entityLength) {
        const contextLength = 50; // Characters before and after
        const start = Math.max(0, offset - contextLength);
        const end = Math.min(text.length, offset + entityLength + contextLength);
        
        let snippet = text.substring(start, end);
        
        // Highlight the entity
        const relativeStart = offset - start;
        const relativeEnd = relativeStart + entityLength;
        
        const highlightedSnippet = 
            snippet.substring(0, relativeStart) +
            `<mark class="entity-highlight">${snippet.substring(relativeStart, relativeEnd)}</mark>` +
            snippet.substring(relativeEnd);
        
        // Add ellipsis if truncated
        const prefix = start > 0 ? '...' : '';
        const suffix = end < text.length ? '...' : '';
        
        return {
            html: prefix + highlightedSnippet + suffix,
            fullText: snippet
        };
    }
    
    hideSnippetPane() {
        if (this.snippetPane) {
            this.snippetPane.classList.remove('visible');
            this.snippetPane.style.display = 'none';
        }
    }
    
    jumpToFirstMention() {
        if (!this.selectedEntityId) return;
        
        const mentions = this.app.entityIndexer.getMentions(this.selectedEntityId);
        if (mentions.length === 0) return;
        
        const firstMention = mentions[0];
        this.jumpToPosition(firstMention.offset);
    }
    
    jumpToPosition(offset) {
        const editor = document.getElementById('main-text-editor');
        if (editor) {
            editor.focus();
            editor.setSelectionRange(offset, offset);
            
            // Scroll to position
            const lineHeight = 20;
            const textBeforePosition = editor.value.substring(0, offset);
            const lineNumber = textBeforePosition.split('\n').length;
            const scrollTop = Math.max(0, (lineNumber - 5) * lineHeight);
            editor.scrollTop = scrollTop;
            
            // Hide rail after jumping
            this.hide();
        }
    }
    
    filterEntities(query) {
        if (!query.trim()) {
            // Show all entities
            document.querySelectorAll('.entity-item').forEach(item => {
                item.style.display = 'block';
            });
            return;
        }
        
        const lowerQuery = query.toLowerCase();
        
        document.querySelectorAll('.entity-item').forEach(item => {
            const entityText = item.querySelector('.entity-text').textContent.toLowerCase();
            const matches = entityText.includes(lowerQuery);
            item.style.display = matches ? 'block' : 'none';
        });
    }
    
    refreshIndex() {
        if (this.app.entityIndexer) {
            this.app.entityIndexer.scheduleHeavyPass();
            document.getElementById('index-status').textContent = 'Refreshing...';
        }
    }
    
    showBulkActions() {
        if (this.app.bulkOperationManager) {
            this.app.bulkOperationManager.showDialog();
        }
    }
    
    bulkEditEntity(entityId = null) {
        const targetEntityId = entityId || this.selectedEntityId;
        if (!targetEntityId) return;
        
        if (this.app.bulkOperationManager) {
            this.app.bulkOperationManager.showDialog(targetEntityId);
        }
    }
    
    // Public API
    
    highlightEntity(entityId) {
        this.selectEntity(entityId);
        
        if (!this.isVisible) {
            this.show();
        }
        
        // Expand the type if needed
        const entity = this.app.entityIndexer.getEntityById(entityId);
        if (entity) {
            const typeElement = document.querySelector(`[data-type="${entity.type}"]`);
            if (typeElement && typeElement.classList.contains('collapsed')) {
                this.toggleType(entity.type);
            }
        }
    }
    
    getSelectedEntity() {
        return this.selectedEntityId;
    }
    
    switchTab(tabName) {
        this.currentTab = tabName;
        
        // Update tab buttons
        this.element.querySelectorAll('.tab-button').forEach(button => {
            button.classList.toggle('active', button.dataset.tab === tabName);
        });
        
        // Update tab content
        this.element.querySelectorAll('.tab-content').forEach(content => {
            content.classList.toggle('active', content.id === `${tabName}-tab`);
        });
        
        // Initialize tab-specific content
        if (tabName === 'arguments') {
            this.argumentEditor.initialize();
        }
        
        // Hide snippet pane when switching tabs
        this.hideSnippetPane();
    }
    
    setCollapsed(collapsed) {
        this.isCollapsed = collapsed;
        if (collapsed) {
            this.hide();
        }
    }
}