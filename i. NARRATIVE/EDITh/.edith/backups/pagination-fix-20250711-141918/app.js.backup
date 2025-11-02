// Import entity system modules
import('./assets/js/modules/EntityIndexer.js').then(module => window.EntityIndexer = module.EntityIndexer);
import('./assets/js/modules/EntityDetailPanel.js').then(module => window.EntityDetailPanel = module.EntityDetailPanel);
import('./assets/js/modules/FactExtractor.js').then(module => window.FactExtractor = module.FactExtractor);
import('./assets/js/modules/LeftRail.js').then(module => window.LeftRail = module.LeftRail);
import('./assets/js/modules/EntityDetailPanelIntegration.js').then(module => window.integrateEntityDetailPanel = module.integrateEntityDetailPanel);
// Removed BulkOperationManager - not requested feature
import('./assets/js/modules/SmartCommandProcessor.js').then(module => window.SmartCommandProcessor = module.SmartCommandProcessor);
import('./assets/js/modules/BlueprintManager.js').then(module => window.BlueprintManager = module.BlueprintManager);

class DocumentUnitManager {
    constructor() {
        this.units = [];
        this.unitMap = new Map();
        this.currentContent = '';
    }
    
    parseDocument(content) {
        this.currentContent = content;
        this.units = [];
        this.unitMap.clear();
        
        // Split by lines to find headings
        const lines = content.split('\n');
        let currentUnit = null;
        let unitId = 0;
        
        lines.forEach((line, index) => {
            const headingMatch = line.match(/^#\s+(.+)$/);
            
            if (headingMatch) {
                // Save previous unit if exists
                if (currentUnit) {
                    currentUnit.endLine = index - 1;
                    currentUnit.content = this.extractUnitContent(currentUnit);
                    this.units.push(currentUnit);
                    this.unitMap.set(currentUnit.id, currentUnit);
                }
                
                // Start new unit
                currentUnit = {
                    id: `unit-${unitId++}`,
                    title: headingMatch[1],
                    level: 1,
                    startLine: index,
                    endLine: null,
                    content: '',
                    tokens: 0
                };
            }
        });
        
        // Save last unit
        if (currentUnit) {
            currentUnit.endLine = lines.length - 1;
            currentUnit.content = this.extractUnitContent(currentUnit);
            this.units.push(currentUnit);
            this.unitMap.set(currentUnit.id, currentUnit);
        }
        
        // If no headings, treat entire document as one unit
        if (this.units.length === 0) {
            const unit = {
                id: 'unit-0',
                title: 'Document',
                level: 0,
                startLine: 0,
                endLine: lines.length - 1,
                content: content,
                tokens: this.estimateTokens(content)
            };
            this.units.push(unit);
            this.unitMap.set(unit.id, unit);
        }
        
        // Calculate tokens for each unit
        this.units.forEach(unit => {
            unit.tokens = this.estimateTokens(unit.content);
        });
        
        return this.units;
    }
    
    extractUnitContent(unit) {
        const lines = this.currentContent.split('\n');
        return lines.slice(unit.startLine, unit.endLine + 1).join('\n');
    }
    
    estimateTokens(text) {
        // Rough estimate: 1 token ≈ 4 characters
        return Math.ceil(text.length / 4);
    }
    
    getUnitById(id) {
        return this.unitMap.get(id);
    }
    
    getUnitAtPosition(lineNumber) {
        return this.units.find(unit => 
            lineNumber >= unit.startLine && lineNumber <= unit.endLine
        );
    }
    
    getTotalTokens() {
        return this.units.reduce((sum, unit) => sum + unit.tokens, 0);
    }
    
    replaceUnitContent(unitId, newContent) {
        const unit = this.unitMap.get(unitId);
        if (!unit) return null;
        
        const lines = this.currentContent.split('\n');
        const newLines = newContent.split('\n');
        
        // Replace the unit's lines
        lines.splice(unit.startLine, unit.endLine - unit.startLine + 1, ...newLines);
        
        // Update the content and reparse to maintain consistency
        this.currentContent = lines.join('\n');
        this.parseDocument(this.currentContent);
        
        return this.currentContent;
    }
}

class VersionHistoryManager {
    constructor() {
        this.dbName = 'EDIThVersionHistory';
        this.dbVersion = 1;
        this.db = null;
        this.currentDocumentId = null;
        this.currentBranch = 'main';
        this.branches = {};
        this.isPreviewMode = false;
        
        this.initDB();
    }
    
    async initDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                resolve();
            };
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                if (!db.objectStoreNames.contains('versions')) {
                    const store = db.createObjectStore('versions', {
                        keyPath: 'id',
                        autoIncrement: true
                    });
                    
                    store.createIndex('documentId', 'documentId', { unique: false });
                    store.createIndex('branchId', 'branchId', { unique: false });
                    store.createIndex('timestamp', 'timestamp', { unique: false });
                }
                
                if (!db.objectStoreNames.contains('documents')) {
                    const docStore = db.createObjectStore('documents', {
                        keyPath: 'documentId'
                    });
                    
                    docStore.createIndex('title', 'title', { unique: false });
                }
            };
        });
    }
    
    async saveVersion(documentId, title, content, parentVersionId = null, branchId = null) {
        if (!this.db) await this.initDB();
        
        // Generate excerpt (first 50 characters)
        const textContent = content.replace(/<[^>]*>/g, '').trim();
        const excerpt = textContent.substring(0, 50) + (textContent.length > 50 ? '...' : '');
        
        // Count words
        const wordCount = textContent.split(/\s+/).filter(word => word.length > 0).length;
        
        // Create new branch if editing from historical version
        if (!branchId) {
            branchId = parentVersionId ? this.generateBranchId() : 'main';
        }
        
        const version = {
            documentId,
            title,
            content,
            timestamp: Date.now(),
            parentVersionId,
            branchId,
            wordCount,
            excerpt
        };
        
        const transaction = this.db.transaction(['versions'], 'readwrite');
        const store = transaction.objectStore('versions');
        
        return new Promise((resolve, reject) => {
            const request = store.add(version);
            request.onsuccess = () => {
                version.id = request.result;
                this.updateDocumentMetadata(documentId, title, branchId, version.id);
                resolve(version);
            };
            request.onerror = () => reject(request.error);
        });
    }
    
    async updateDocumentMetadata(documentId, title, currentBranch, currentVersionId) {
        const transaction = this.db.transaction(['documents'], 'readwrite');
        const store = transaction.objectStore('documents');
        
        const docData = {
            documentId,
            title,
            currentBranch,
            currentVersionId,
            lastModified: Date.now()
        };
        
        return new Promise((resolve, reject) => {
            const request = store.put(docData);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    }
    
    generateBranchId() {
        const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        const existingBranches = Object.keys(this.branches);
        
        for (let i = 0; i < letters.length; i++) {
            const branchId = `branch-${letters[i]}`;
            if (!existingBranches.includes(branchId)) {
                return branchId;
            }
        }
        
        // Fallback to timestamp-based ID
        return `branch-${Date.now()}`;
    }
    
    async loadVersionHistory(documentId) {
        if (!this.db) await this.initDB();
        
        this.currentDocumentId = documentId;
        const transaction = this.db.transaction(['versions'], 'readonly');
        const store = transaction.objectStore('versions');
        const index = store.index('documentId');
        
        return new Promise((resolve, reject) => {
            const request = index.getAll(documentId);
            request.onsuccess = () => {
                const versions = request.result.sort((a, b) => a.timestamp - b.timestamp);
                this.organizeBranches(versions);
                resolve(this.branches);
            };
            request.onerror = () => reject(request.error);
        });
    }
    
    organizeBranches(versions) {
        this.branches = {};
        
        versions.forEach(version => {
            if (!this.branches[version.branchId]) {
                this.branches[version.branchId] = [];
            }
            this.branches[version.branchId].push(version);
        });
        
        // Sort versions within each branch by timestamp
        Object.keys(this.branches).forEach(branchId => {
            this.branches[branchId].sort((a, b) => a.timestamp - b.timestamp);
        });
    }
    
    async deleteVersion(versionId) {
        if (!this.db) await this.initDB();
        
        const transaction = this.db.transaction(['versions'], 'readwrite');
        const store = transaction.objectStore('versions');
        
        return new Promise((resolve, reject) => {
            const request = store.delete(versionId);
            request.onsuccess = () => {
                // Reload history to update branches
                this.loadVersionHistory(this.currentDocumentId);
                resolve();
            };
            request.onerror = () => reject(request.error);
        });
    }
    
    async deleteBranch(branchId) {
        if (!this.db) await this.initDB();
        
        const versionsToDelete = this.branches[branchId] || [];
        const transaction = this.db.transaction(['versions'], 'readwrite');
        const store = transaction.objectStore('versions');
        
        const deletePromises = versionsToDelete.map(version => {
            return new Promise((resolve, reject) => {
                const request = store.delete(version.id);
                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });
        });
        
        await Promise.all(deletePromises);
        delete this.branches[branchId];
    }
    
    getRelativeTime(timestamp) {
        const now = Date.now();
        const diff = now - timestamp;
        
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);
        
        if (days > 0) return `${days}d ago`;
        if (hours > 0) return `${hours}h ago`;
        if (minutes > 0) return `${minutes}m ago`;
        return 'Just now';
    }
}

class FootnoteManager {
    constructor() {
        this.footnotes = [];
        this.dbName = 'EDIThFootnotes';
        this.dbVersion = 1;
        this.db = null;
        
        this.initDB();
    }
    
    async initDB() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);
            
            request.onerror = () => reject(request.error);
            request.onsuccess = () => {
                this.db = request.result;
                resolve();
            };
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                if (!db.objectStoreNames.contains('footnotes')) {
                    const store = db.createObjectStore('footnotes', { 
                        keyPath: 'id', 
                        autoIncrement: true 
                    });
                    
                    store.createIndex('url', 'url', { unique: false });
                    store.createIndex('timestamp', 'timestamp', { unique: false });
                    store.createIndex('documentId', 'documentId', { unique: false });
                }
            };
        });
    }
    
    async saveFootnote(footnote) {
        if (!this.db) await this.initDB();
        
        const transaction = this.db.transaction(['footnotes'], 'readwrite');
        const store = transaction.objectStore('footnotes');
        
        const footnoteData = {
            ...footnote,
            timestamp: Date.now()
        };
        
        return new Promise((resolve, reject) => {
            const request = store.add(footnoteData);
            request.onsuccess = () => {
                footnoteData.id = request.result;
                this.footnotes.push(footnoteData);
                resolve(footnoteData);
            };
            request.onerror = () => reject(request.error);
        });
    }
    
    async loadFootnotes() {
        if (!this.db) await this.initDB();
        
        const transaction = this.db.transaction(['footnotes'], 'readonly');
        const store = transaction.objectStore('footnotes');
        
        return new Promise((resolve, reject) => {
            const request = store.getAll();
            request.onsuccess = () => {
                this.footnotes = request.result;
                resolve(this.footnotes);
            };
            request.onerror = () => reject(request.error);
        });
    }
    
    searchFootnotes(query) {
        const lowercaseQuery = query.toLowerCase();
        return this.footnotes.filter(footnote => 
            footnote.url.toLowerCase().includes(lowercaseQuery) ||
            footnote.text.toLowerCase().includes(lowercaseQuery) ||
            (footnote.title && footnote.title.toLowerCase().includes(lowercaseQuery))
        );
    }
}

class MarkdownEditor {
    constructor() {
        this.titleField = document.getElementById('title-field');
        this.editor = document.getElementById('editor');
        this.statusBar = document.getElementById('status');
        
        this.saveTimeout = null;
        this.lastContent = '';
        this.lastTitle = '';
        
        // Undo/Redo system
        this.undoStack = [];
        this.redoStack = [];
        this.currentSnapshot = null;
        this.isUndoRedo = false;
        
        // Version History system
        this.versionHistoryManager = new VersionHistoryManager();
        this.lastParagraphCount = 0;
        
        // Document Unit Manager
        this.documentUnitManager = new DocumentUnitManager();
        
        // Blueprint Manager
        this.blueprintManager = null; // Will be initialized when module loads
        
        // AI Command system
        this.pendingChanges = [];
        this.currentChangeIndex = 0;
        this.isProcessingCommand = false;
        this.directEditsApplied = 0;
        
        // Add debounce timer for formatting
        this.formattingTimer = null;
        this.isActivelyTyping = false;
        this.typingTimer = null;
        
        this.footnoteManager = new FootnoteManager();
        
        // Initialize entity system
        this.initializeEntitySystem();
        // Disabled old entity panel - using LeftRail now
        // this.setupEntityIndexPanel();
        this.entityProfileMode = false;
        this.currentEntityProfile = null;
        this.entityMentionIndex = new Map(); // Track current mention position per entity
        
        // Initialize LeftRail for entity browsing
        this.leftRail = null;
        this.initializeLeftRail();
        
        // BulkOperationManager removed - not requested
        
        // Initialize SmartCommandProcessor
        this.smartCommandProcessor = null;
        this.initializeSmartProcessor();
        
        // Initialize cutting room floor
        this.cuttingRoomFloor = [];
        this.cuttingRoomPositions = new Map();
        this.cuttingRoomContent = '';
        this.cuttingRoomEditor = null;
        
        // Initialize pagination
        this.currentPage = 1;
        this.pages = new Map([[1, document.querySelector('.page-wrapper')]]);
        this.pageHeight = 297 * 3.7795275591; // A4 height in pixels (297mm)
        
        this.setupMenuHandlers();
        this.setupUndoRedo();
        this.setupVersionHistory();
        this.setupCommandSystem();
        this.setupCuttingRoomFloor();
        this.setupPagination();
        this.setupContextPanel();
        this.setupMetaMode();
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadLastDocument();
    }
    
    setupMenuHandlers() {
        const menuButton = document.getElementById('menu-button');
        const menuDropdown = document.getElementById('menu-dropdown');
        const footnoteBrowser = document.getElementById('footnote-browser');
        const closeButton = footnoteBrowser.querySelector('.close-button');
        const newFileButton = document.getElementById('new-file-button');
        const deleteButton = document.getElementById('delete-button');
        
        // Toggle menu dropdown
        menuButton.addEventListener('click', (e) => {
            e.stopPropagation();
            menuDropdown.classList.toggle('visible');
        });
        
        // Close menu when clicking outside
        document.addEventListener('click', () => {
            menuDropdown.classList.remove('visible');
        });
        
        // Handle menu items
        menuDropdown.addEventListener('click', async (e) => {
            const item = e.target.closest('.menu-item');
            if (!item) return;
            
            const action = item.dataset.action;
            if (action === 'footnotes') {
                menuDropdown.classList.remove('visible');
                await this.showFootnoteBrowser();
            } else if (action === 'entities') {
                menuDropdown.classList.remove('visible');
                this.showEntityIndex();
            } else if (action === 'cutting-room') {
                menuDropdown.classList.remove('visible');
                this.openCuttingRoomFloor();
            } else if (action === 'ai-command') {
                menuDropdown.classList.remove('visible');
                this.openCommandChatbox();
            } else if (action === 'load') {
                menuDropdown.classList.remove('visible');
                await this.showDocumentLoader();
            } else if (action === 'context-panel') {
                menuDropdown.classList.remove('visible');
                this.showContextPanel();
            }
        });
        
        // Close modal
        closeButton.addEventListener('click', () => {
            footnoteBrowser.classList.remove('visible');
        });
        
        footnoteBrowser.addEventListener('click', (e) => {
            if (e.target === footnoteBrowser) {
                footnoteBrowser.classList.remove('visible');
            }
        });
        
        // New file button
        newFileButton.addEventListener('click', () => {
            this.createNewFile();
        });
        
        // Delete button
        deleteButton.addEventListener('click', () => {
            this.deleteCurrentFile();
        });
    }
    
    setupUndoRedo() {
        // Create undo/redo panel
        this.setupHoverPanel();
        
        // Take initial snapshot
        this.takeSnapshot();
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
                e.preventDefault();
                this.undo();
            } else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
                e.preventDefault();
                this.redo();
            }
        });
        
        // Track changes for undo/redo
        let changeTimer = null;
        const trackChange = () => {
            if (this.isUndoRedo) return;
            
            clearTimeout(changeTimer);
            changeTimer = setTimeout(() => {
                this.takeSnapshot();
            }, 1000); // Take snapshot 1 second after user stops typing
        };
        
        this.editor.addEventListener('input', trackChange);
        this.titleField.addEventListener('input', trackChange);
    }
    
    setupHoverPanel() {
        const panel = document.getElementById('hover-panel');
        
        // Add event listeners
        document.getElementById('undo-btn').addEventListener('click', () => this.undo());
        document.getElementById('redo-btn').addEventListener('click', () => this.redo());
        document.getElementById('command-btn').addEventListener('click', () => this.toggleCommandChatbox());
        document.getElementById('version-history-button').addEventListener('click', () => this.toggleVersionHistoryPanel());
        document.getElementById('add-to-context-btn').addEventListener('click', () => this.addCurrentDocToContext());
        
        // Show/hide on mouse movement
        let hideTimer = null;
        
        document.addEventListener('mousemove', (e) => {
            // Show panel when mouse moves to top area
            if (e.clientY < 100) {
                panel.classList.add('visible');
                clearTimeout(hideTimer);
            } else {
                // Hide panel when mouse moves away
                clearTimeout(hideTimer);
                hideTimer = setTimeout(() => {
                    panel.classList.remove('visible');
                }, 1000);
            }
        });
        
        // Keep panel visible when hovering over it
        panel.addEventListener('mouseenter', () => {
            clearTimeout(hideTimer);
            panel.classList.add('visible');
        });
        
        panel.addEventListener('mouseleave', () => {
            hideTimer = setTimeout(() => {
                panel.classList.remove('visible');
            }, 1000);
        });
    }
    
    takeSnapshot() {
        const snapshot = {
            title: this.titleField.value,
            content: this.editor.innerHTML,
            timestamp: Date.now()
        };
        
        // Don't create duplicate snapshots
        if (this.currentSnapshot && 
            this.currentSnapshot.title === snapshot.title && 
            this.currentSnapshot.content === snapshot.content) {
            return;
        }
        
        // If we have a current snapshot, push it to undo stack
        if (this.currentSnapshot) {
            this.undoStack.push(this.currentSnapshot);
        }
        
        this.currentSnapshot = snapshot;
        
        // Clear redo stack when new changes are made
        this.redoStack = [];
        
        // Update button states
        this.updateUndoRedoButtons();
    }
    
    undo() {
        if (this.undoStack.length === 0) return;
        
        this.isUndoRedo = true;
        
        // Push current state to redo stack
        if (this.currentSnapshot) {
            this.redoStack.push(this.currentSnapshot);
        }
        
        // Get previous state
        const previousSnapshot = this.undoStack.pop();
        this.currentSnapshot = previousSnapshot;
        
        // Restore state
        this.titleField.value = previousSnapshot.title;
        this.editor.innerHTML = previousSnapshot.content;
        
        // Update button states
        this.updateUndoRedoButtons();
        
        this.isUndoRedo = false;
        this.showStatus('Undo', 1000);
    }
    
    redo() {
        if (this.redoStack.length === 0) return;
        
        this.isUndoRedo = true;
        
        // Push current state to undo stack
        if (this.currentSnapshot) {
            this.undoStack.push(this.currentSnapshot);
        }
        
        // Get next state
        const nextSnapshot = this.redoStack.pop();
        this.currentSnapshot = nextSnapshot;
        
        // Restore state
        this.titleField.value = nextSnapshot.title;
        this.editor.innerHTML = nextSnapshot.content;
        
        // Update button states
        this.updateUndoRedoButtons();
        
        this.isUndoRedo = false;
        this.showStatus('Redo', 1000);
    }
    
    updateUndoRedoButtons() {
        const undoBtn = document.getElementById('undo-btn');
        const redoBtn = document.getElementById('redo-btn');
        
        if (undoBtn) {
            undoBtn.disabled = this.undoStack.length === 0;
            // FORCE ENABLE IF THERE'S CONTENT
            if (this.editor && this.editor.textContent.length > 0) {
                undoBtn.disabled = false;
            }
        }
        
        if (redoBtn) {
            redoBtn.disabled = this.redoStack.length === 0;
        }
    }
    
    setupVersionHistory() {
        // Version history panel close button
        const versionPanel = document.getElementById('version-history-panel');
        const closePanelBtn = document.getElementById('close-version-panel');
        
        closePanelBtn.addEventListener('click', () => {
            this.closeVersionHistoryPanel();
        });
        
        // Close panel when clicking outside
        document.addEventListener('click', (e) => {
            if (versionPanel.classList.contains('visible') && 
                !versionPanel.contains(e.target) && 
                !document.getElementById('version-history-button').contains(e.target)) {
                this.closeVersionHistoryPanel();
            }
        });
        
        // Paragraph detection for version saving
        let paragraphTimer = null;
        this.editor.addEventListener('input', () => {
            // Clear existing timer
            if (paragraphTimer) {
                clearTimeout(paragraphTimer);
            }
            
            // Check for paragraph completion immediately
            if (this.detectParagraphCompletion()) {
                this.saveCurrentVersion();
            } else {
                // Set timer for delayed save (in case user pauses)
                paragraphTimer = setTimeout(() => {
                    const currentParagraphCount = this.countParagraphs();
                    if (currentParagraphCount > this.lastParagraphCount) {
                        this.saveCurrentVersion();
                    }
                }, 3000); // Save after 3 seconds of inactivity
            }
        });
        
        // Load version history for current document
        this.loadVersionHistoryForCurrentDocument();
        
        // Delete selected versions button
        const deleteSelectedBtn = document.getElementById('delete-selected-versions');
        deleteSelectedBtn.addEventListener('click', () => {
            this.deleteSelectedVersions();
        });
    }
    
    detectParagraphCompletion() {
        const content = this.editor.textContent;
        const currentParagraphCount = this.countParagraphs();
        
        // Check if we have more paragraphs than before
        if (currentParagraphCount > this.lastParagraphCount) {
            this.lastParagraphCount = currentParagraphCount;
            return true;
        }
        
        // Check for double newlines (paragraph break)
        if (content.includes('\n\n')) {
            return true;
        }
        
        return false;
    }
    
    countParagraphs() {
        const content = this.editor.textContent.trim();
        if (!content) return 0;
        
        // Split by double newlines or single newlines and filter out empty strings
        const paragraphs = content.split(/\n\s*\n|\n/).filter(p => p.trim().length > 0);
        return paragraphs.length;
    }
    
    async saveCurrentVersion() {
        const title = this.titleField.value || 'Untitled';
        const content = this.editor.innerHTML;
        
        // Don't save empty content
        if (!content.trim()) return;
        
        try {
            const documentId = this.generateDocumentId(title);
            console.log('Saving version to branch:', this.versionHistoryManager.currentBranch);
            
            // Determine parentVersionId based on preview mode
            let parentVersionId = null;
            if (this.versionHistoryManager.isPreviewMode) {
                // Find the currently previewed version
                const previewedItem = document.querySelector('.version-item.preview-mode');
                if (previewedItem) {
                    parentVersionId = parseInt(previewedItem.dataset.versionId);
                }
            }
            
            const savedVersion = await this.versionHistoryManager.saveVersion(
                documentId, 
                title, 
                content,
                parentVersionId,
                this.versionHistoryManager.currentBranch
            );
            
            // Update current document tracking
            this.versionHistoryManager.currentDocumentId = documentId;
            
            // Switch to new branch if one was created
            if (savedVersion.branchId !== this.versionHistoryManager.currentBranch) {
                this.versionHistoryManager.currentBranch = savedVersion.branchId;
            }
            
            // Exit preview mode after saving
            if (this.versionHistoryManager.isPreviewMode) {
                this.versionHistoryManager.isPreviewMode = false;
                this.editor.classList.remove('preview-mode');
            }
            
            console.log('Version saved automatically');
        } catch (error) {
            console.error('Error saving version:', error);
        }
    }
    
    generateDocumentId(title) {
        // Create a consistent ID based on title
        return title.toLowerCase().replace(/[^a-z0-9]/g, '_') || 'untitled';
    }
    
    async loadVersionHistoryForCurrentDocument() {
        const title = this.titleField.value || 'Untitled';
        const documentId = this.generateDocumentId(title);
        
        try {
            await this.versionHistoryManager.loadVersionHistory(documentId);
        } catch (error) {
            console.error('Error loading version history:', error);
        }
    }
    
    toggleVersionHistoryPanel() {
        const panel = document.getElementById('version-history-panel');
        
        if (panel.classList.contains('visible')) {
            this.closeVersionHistoryPanel();
        } else {
            this.openVersionHistoryPanel();
        }
    }
    
    async openVersionHistoryPanel() {
        const panel = document.getElementById('version-history-panel');
        
        // Load current document's version history
        await this.loadVersionHistoryForCurrentDocument();
        
        // Render the timeline
        this.renderVersionTimeline();
        
        // Show panel
        panel.classList.add('visible');
    }
    
    closeVersionHistoryPanel() {
        const panel = document.getElementById('version-history-panel');
        panel.classList.remove('visible');
        
        // Exit preview mode if active
        if (this.versionHistoryManager.isPreviewMode) {
            this.exitPreviewMode();
        }
    }
    
    renderVersionTimeline() {
        const timeline = document.getElementById('version-timeline');
        timeline.innerHTML = '';
        
        const branches = this.versionHistoryManager.branches;
        const branchKeys = Object.keys(branches);
        
        console.log('Rendering timeline with branches:', branchKeys);
        console.log('Branch data:', branches);
        console.log('Total branches found:', branchKeys.length);
        
        // Sort branches: main first, then others
        branchKeys.sort((a, b) => {
            if (a === 'main') return -1;
            if (b === 'main') return 1;
            return a.localeCompare(b);
        });
        
        branchKeys.forEach((branchId, branchIndex) => {
            const branchVersions = branches[branchId];
            if (branchVersions.length === 0) return;
            
            // Create branch group with connections
            const branchGroup = document.createElement('div');
            branchGroup.className = 'branch-group';
            branchGroup.dataset.branchId = branchId;
            
            // Add branch connection line for non-main branches
            if (branchId !== 'main') {
                const connectionLine = document.createElement('div');
                connectionLine.className = `branch-connection ${branchId}`;
                branchGroup.appendChild(connectionLine);
            }
            
            // Branch header with enhanced styling
            const branchHeader = document.createElement('div');
            branchHeader.className = `branch-header ${branchId}`;
            
            const branchInfo = document.createElement('div');
            branchInfo.className = 'branch-info';
            
            const branchName = document.createElement('span');
            branchName.className = 'branch-name';
            branchName.textContent = branchId === 'main' ? 'main' : branchId.replace('branch-', 'Branch ');
            
            const branchStats = document.createElement('span');
            branchStats.className = 'branch-stats';
            branchStats.textContent = `${branchVersions.length} version${branchVersions.length !== 1 ? 's' : ''}`;
            
            branchInfo.appendChild(branchName);
            branchInfo.appendChild(branchStats);
            
            const branchControls = document.createElement('div');
            branchControls.className = 'branch-controls';
            
            if (branchId !== 'main') {
                const deleteBranchBtn = document.createElement('button');
                deleteBranchBtn.className = 'delete-branch-btn';
                deleteBranchBtn.textContent = 'Delete';
                deleteBranchBtn.addEventListener('click', () => this.deleteBranch(branchId));
                branchControls.appendChild(deleteBranchBtn);
            }
            
            branchHeader.appendChild(branchInfo);
            branchHeader.appendChild(branchControls);
            
            // Make branch header clickable to switch branches
            branchHeader.addEventListener('click', (e) => {
                if (e.target.closest('.delete-branch-btn')) return; // Don't switch when deleting
                this.switchToBranch(branchId);
            });
            
            branchGroup.appendChild(branchHeader);
            
            // Add timeline line
            const timelineLine = document.createElement('div');
            timelineLine.className = `timeline-line ${branchId}`;
            branchGroup.appendChild(timelineLine);
            
            // Add versions with enhanced connections
            branchVersions.slice().reverse().forEach((version, index) => {
                const versionItem = this.createVersionItem(version, branchId, index, branchVersions.length);
                branchGroup.appendChild(versionItem);
            });
            
            timeline.appendChild(branchGroup);
        });
        
        // Update branch display to show current branch
        this.updateBranchDisplay();
    }
    
    createVersionItem(version, branchId, index = 0, totalVersions = 1) {
        const item = document.createElement('div');
        item.className = 'version-item';
        item.dataset.versionId = version.id;
        item.dataset.branchId = branchId;
        
        // Add position class for styling
        if (index === 0) item.classList.add('version-latest');
        if (index === totalVersions - 1) item.classList.add('version-first');
        
        // Checkbox for selection
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'version-checkbox';
        checkbox.addEventListener('change', this.updateDeleteButton.bind(this));
        
        // Version connector line (except for first item)
        if (index > 0) {
            const connector = document.createElement('div');
            connector.className = `version-connector ${branchId}`;
            item.appendChild(connector);
        }
        
        // Version node (colored circle) with enhanced styling
        const node = document.createElement('div');
        node.className = `version-node ${branchId}`;
        if (index === 0) node.classList.add('current');
        
        // Add branch indicator for non-main branches
        if (branchId !== 'main') {
            const branchIndicator = document.createElement('div');
            branchIndicator.className = 'branch-indicator';
            branchIndicator.textContent = branchId.replace('branch-', '').toUpperCase();
            node.appendChild(branchIndicator);
        }
        
        // Version info
        const info = document.createElement('div');
        info.className = 'version-info';
        
        const meta = document.createElement('div');
        meta.className = 'version-meta';
        
        const time = document.createElement('span');
        time.className = 'version-time';
        time.textContent = this.versionHistoryManager.getRelativeTime(version.timestamp);
        
        const stats = document.createElement('span');
        stats.className = 'version-stats';
        stats.textContent = `${version.wordCount} words`;
        
        meta.appendChild(time);
        meta.appendChild(stats);
        
        const excerpt = document.createElement('div');
        excerpt.className = 'version-excerpt';
        excerpt.textContent = version.excerpt;
        
        info.appendChild(meta);
        info.appendChild(excerpt);
        
        // Event listeners
        item.addEventListener('mouseenter', () => this.previewVersion(version));
        item.addEventListener('mouseleave', () => this.exitPreviewMode());
        item.addEventListener('click', (e) => {
            if (!e.target.classList.contains('version-checkbox')) {
                this.selectVersionForEditing(version);
            }
        });
        
        item.appendChild(checkbox);
        item.appendChild(node);
        item.appendChild(info);
        
        return item;
    }
    
    updateDeleteButton() {
        const checkboxes = document.querySelectorAll('.version-checkbox:checked');
        const deleteBtn = document.getElementById('delete-selected-versions');
        
        deleteBtn.disabled = checkboxes.length === 0;
        deleteBtn.textContent = checkboxes.length > 0 ? 
            `Delete ${checkboxes.length} Selected` : 'Delete Selected';
    }
    
    previewVersion(version) {
        if (this.versionHistoryManager.isPreviewMode) return;
        
        this.versionHistoryManager.isPreviewMode = true;
        
        // Store current content
        this.versionHistoryManager.originalTitle = this.titleField.value;
        this.versionHistoryManager.originalContent = this.editor.innerHTML;
        
        // Show version content in grey
        this.titleField.value = version.title;
        this.editor.innerHTML = version.content;
        this.editor.classList.add('preview-mode');
        
        // Highlight the previewed version
        document.querySelectorAll('.version-item').forEach(item => {
            item.classList.remove('preview-mode');
        });
        
        const versionItem = document.querySelector(`[data-version-id="${version.id}"]`);
        if (versionItem) {
            versionItem.classList.add('preview-mode');
        }
    }
    
    switchToBranch(branchId) {
        this.versionHistoryManager.currentBranch = branchId;
        
        // Get the latest version from the target branch
        const branchVersions = this.versionHistoryManager.branches[branchId];
        if (branchVersions && branchVersions.length > 0) {
            const latestVersion = branchVersions[branchVersions.length - 1];
            
            // Load the latest version content
            this.titleField.value = latestVersion.title;
            this.editor.innerHTML = latestVersion.content;
            
            // Update UI to show current branch
            this.updateBranchDisplay();
            
            console.log(`Switched to branch: ${branchId}`);
        }
    }
    
    updateBranchDisplay() {
        // Highlight current branch in the timeline
        document.querySelectorAll('.branch-header').forEach(header => {
            header.classList.remove('current-branch');
        });
        
        const currentBranchHeader = document.querySelector(`.branch-header.${this.versionHistoryManager.currentBranch}`);
        if (currentBranchHeader) {
            currentBranchHeader.classList.add('current-branch');
        }
    }
    
    exitPreviewMode() {
        if (!this.versionHistoryManager.isPreviewMode) return;
        
        this.versionHistoryManager.isPreviewMode = false;
        
        // Restore original content
        this.titleField.value = this.versionHistoryManager.originalTitle;
        this.editor.innerHTML = this.versionHistoryManager.originalContent;
        this.editor.classList.remove('preview-mode');
        
        // Remove preview highlighting
        document.querySelectorAll('.version-item').forEach(item => {
            item.classList.remove('preview-mode');
        });
    }
    
    async selectVersionForEditing(version) {
        // If we're not on the same branch, create a new branch
        const needsNewBranch = version.branchId !== this.versionHistoryManager.currentBranch;
        
        if (needsNewBranch) {
            this.versionHistoryManager.currentBranch = this.versionHistoryManager.generateBranchId();
        }
        
        // Set content
        this.titleField.value = version.title;
        this.editor.innerHTML = version.content;
        this.editor.classList.remove('preview-mode');
        
        // Exit preview mode
        this.versionHistoryManager.isPreviewMode = false;
        
        // Close panel
        this.closeVersionHistoryPanel();
        
        // Take a snapshot for undo/redo
        this.takeSnapshot();
        
        // Save this as a new version if on a new branch
        if (needsNewBranch) {
            await this.saveCurrentVersion();
        }
        
        this.showStatus(`Switched to ${needsNewBranch ? 'new branch from' : ''} version from ${this.versionHistoryManager.getRelativeTime(version.timestamp)}`, 3000);
    }
    
    async deleteBranch(branchId) {
        if (confirm(`Delete branch "${branchId.replace('branch-', 'Branch ')}" and all its versions?`)) {
            try {
                await this.versionHistoryManager.deleteBranch(branchId);
                this.renderVersionTimeline();
                this.showStatus('Branch deleted', 2000);
            } catch (error) {
                console.error('Error deleting branch:', error);
                this.showStatus('Error deleting branch', 2000);
            }
        }
    }
    
    async deleteSelectedVersions() {
        const checkboxes = document.querySelectorAll('.version-checkbox:checked');
        const versionIds = Array.from(checkboxes).map(cb => 
            cb.closest('.version-item').dataset.versionId
        );
        
        if (versionIds.length === 0) return;
        
        if (confirm(`Delete ${versionIds.length} selected version${versionIds.length > 1 ? 's' : ''}?`)) {
            try {
                // Delete each version
                for (const versionId of versionIds) {
                    await this.versionHistoryManager.deleteVersion(parseInt(versionId));
                }
                
                // Refresh timeline
                await this.loadVersionHistoryForCurrentDocument();
                this.renderVersionTimeline();
                
                this.showStatus(`Deleted ${versionIds.length} version${versionIds.length > 1 ? 's' : ''}`, 2000);
            } catch (error) {
                console.error('Error deleting versions:', error);
                this.showStatus('Error deleting versions', 2000);
            }
        }
    }
    
    setupCommandSystem() {
        const chatbox = document.getElementById('command-chatbox');
        const chatboxInput = document.getElementById('chatbox-input');
        const sendBtn = document.getElementById('send-command');
        const closeChatboxBtn = document.getElementById('close-chatbox');
        const acceptAllBtn = document.getElementById('accept-all-changes');
        const contextToggle = document.getElementById('context-toggle');
        const customCmdBtn = document.getElementById('custom-cmd-btn');
        
        // Event listeners
        sendBtn.addEventListener('click', () => this.sendCommand());
        closeChatboxBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.closeCommandChatbox();
        });
        acceptAllBtn.addEventListener('click', () => this.acceptAllChanges());
        
        // Close on click outside
        document.addEventListener('click', (e) => {
            if (chatbox.classList.contains('visible') && 
                !chatbox.contains(e.target) && 
                !e.target.closest('#command-btn') &&
                !e.target.closest('.menu-item[data-action="ai-command"]')) {
                this.closeCommandChatbox();
            }
        });
        
        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && chatbox.classList.contains('visible')) {
                this.closeCommandChatbox();
            }
        });
        
        chatboxInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (this.pendingChanges.length > 0) {
                    if (e.detail === 2) { // Double click/press
                        this.acceptAllChanges();
                    } else {
                        this.acceptNextChange();
                    }
                } else {
                    this.sendCommand();
                }
            }
        });
        
        // Highlight Context and Target keywords as user types
        chatboxInput.addEventListener('input', () => {
            this.highlightCommandKeywords();
        });
        
        // Context toggle button
        contextToggle.addEventListener('click', () => {
            const input = chatboxInput;
            const cursorPos = input.selectionStart;
            const textBefore = input.value.substring(0, cursorPos);
            const textAfter = input.value.substring(cursorPos);
            
            // Check if we should add or remove Context
            const lastWord = textBefore.split(' ').pop();
            if (lastWord === 'Context') {
                // Remove the word Context
                input.value = textBefore.substring(0, textBefore.length - 7) + textAfter;
                input.setSelectionRange(cursorPos - 7, cursorPos - 7);
            } else {
                // Add Context at cursor position
                const prefix = textBefore.length > 0 && !textBefore.endsWith(' ') ? ' ' : '';
                const suffix = textAfter.length > 0 && !textAfter.startsWith(' ') ? ' ' : '';
                input.value = textBefore + prefix + 'Context' + suffix + textAfter;
                const newPos = cursorPos + prefix.length + 7;
                input.setSelectionRange(newPos, newPos);
            }
            
            // Toggle button state
            contextToggle.classList.toggle('active');
            
            // Update highlighting
            this.highlightCommandKeywords();
            
            // Focus back on input
            input.focus();
        });
        
        // Custom commands button (placeholder)
        customCmdBtn.addEventListener('click', () => {
            // TODO: Implement custom command creation/selection
            this.showStatus('Custom commands feature coming soon!', 2000);
            customCmdBtn.classList.toggle('active');
        });
        
        // Global keydown for Enter handling
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && this.pendingChanges.length > 0 && 
                !chatboxInput.contains(document.activeElement)) {
                e.preventDefault();
                if (e.detail === 2) {
                    this.acceptAllChanges();
                } else {
                    this.acceptNextChange();
                }
            }
        });
    }
    
    toggleCommandChatbox() {
        const chatbox = document.getElementById('command-chatbox');
        
        if (chatbox.classList.contains('visible')) {
            this.closeCommandChatbox();
        } else {
            this.openCommandChatbox();
        }
    }
    
    openCommandChatbox() {
        const chatbox = document.getElementById('command-chatbox');
        const input = document.getElementById('chatbox-input');
        
        // Prevent multiple opens
        if (chatbox.classList.contains('visible')) return;
        
        chatbox.classList.add('visible');
        // Small delay to ensure transition completes before focusing
        setTimeout(() => {
            input.focus();
        }, 100);
    }
    
    closeCommandChatbox() {
        const chatbox = document.getElementById('command-chatbox');
        
        // Prevent multiple closes
        if (!chatbox.classList.contains('visible')) return;
        
        chatbox.classList.remove('visible');
        
        // Clear input
        const input = document.getElementById('chatbox-input');
        input.value = '';
        
        // Clear any pending changes
        this.clearPendingChanges();
        
        // Clear messages after close animation
        setTimeout(() => {
            const messagesContainer = document.getElementById('chatbox-messages');
            if (messagesContainer) {
                messagesContainer.innerHTML = '';
            }
        }, 300);
    }
    
    async sendCommand() {
        const input = document.getElementById('chatbox-input');
        const command = input.value.trim();
        
        if (!command || this.isProcessingCommand) return;
        
        input.value = '';
        this.isProcessingCommand = true;
        
        // Add user message to chat
        this.addChatMessage('user', command);
        
        // Get context based on mode
        let context;
        
        if (this.entityProfileMode && this.currentEntitySnippets) {
            // Entity mode - send snippets as context
            context = {
                mode: 'entity',
                entityName: this.currentEntityProfile.text,
                entityType: this.currentEntityProfile.type,
                snippets: this.currentEntitySnippets.map((s, i) => ({
                    index: i,
                    text: s.modifiedText || s.text,
                    position: s.position,
                    lineNumber: s.lineNumber
                })),
                title: this.titleField.value
            };
        } else {
            // Normal mode - send page context
            const selection = window.getSelection();
            let selectedText = '';
            
            if (selection.rangeCount > 0 && !selection.isCollapsed) {
                selectedText = selection.toString();
            }
            
            // Get page-based context
            const currentPageContent = this.getPageContext(this.currentPage);
            
            // Also get surrounding pages for context
            const prevPageContent = this.currentPage > 1 ? this.getPageContext(this.currentPage - 1) : '';
            const nextPageContent = this.currentPage < this.pages.size ? this.getPageContext(this.currentPage + 1) : '';
            
            context = {
                mode: 'document',
                title: this.titleField.value,
                content: this.editor.textContent,
                html: this.editor.innerHTML,
                selection: selectedText,
                currentPage: this.currentPage,
                totalPages: this.pages.size,
                pageContent: {
                    previous: prevPageContent,
                    current: currentPageContent,
                    next: nextPageContent
                }
            };
        }
        
        try {
            // Send to AI for processing
            await this.processCommandWithAI(command, context);
        } catch (error) {
            console.error('Command processing error:', error);
            console.error('Error details:', error.message, error.stack);
            this.addChatMessage('error', `Sorry, I encountered an error processing your command: ${error.message}`);
        } finally {
            this.isProcessingCommand = false;
        }
    }
    
    addChatMessage(type, message) {
        const messagesContainer = document.getElementById('chatbox-messages');
        const messageEl = document.createElement('div');
        messageEl.className = `chat-message ${type}`;
        
        if (type === 'user') {
            // Highlight Context and Target keywords in user messages
            const highlightedMessage = message
                .replace(/\bContext\b/g, '<span class="keyword-context">Context</span>')
                .replace(/\bTarget\b/g, '<span class="keyword-target">Target</span>');
            messageEl.innerHTML = `<div class="message-content">${highlightedMessage}</div>`;
        } else if (type === 'assistant') {
            messageEl.innerHTML = `<div class="message-content">${message}</div>`;
        } else if (type === 'error') {
            messageEl.innerHTML = `<div class="message-content error">${message}</div>`;
        } else if (type === 'system') {
            messageEl.innerHTML = `<div class="message-content system">${message}</div>`;
        }
        
        messagesContainer.appendChild(messageEl);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
    
    highlightCommandKeywords() {
        const input = document.getElementById('chatbox-input');
        const value = input.value;
        
        // Visual feedback when Context or Target is typed
        if (value.includes('Context') || value.includes('Target')) {
            input.classList.add('has-keywords');
        } else {
            input.classList.remove('has-keywords');
        }
    }
    
    async processCommandWithAI(command, context) {
        try {
            // Use SmartCommandProcessor if available and not in entity mode
            if (this.smartCommandProcessor && context.mode !== 'entity') {
                return await this.smartCommandProcessor.processCommand(command, context);
            }
            // Parse document into units for potential section-based processing
            const documentContent = this.editor.textContent;
            this.documentUnitManager.parseDocument(documentContent);
            const units = this.documentUnitManager.units;
            const totalTokens = this.documentUnitManager.getTotalTokens();
            
            // Check if command references "Context" or "Target" (capital letters)
            const hasContext = command.includes('Context');
            const hasTarget = command.includes('Target');
            
            if (hasContext || hasTarget) {
                // Prepare enhanced context
                const enhancedContext = { ...context };
                
                if (hasContext) {
                    // Add context panel content
                    const contextPanelContent = this.getContextPanelContent();
                    if (contextPanelContent) {
                        enhancedContext.contextPanelContent = contextPanelContent;
                        enhancedContext.hasContextReference = true;
                    }
                }
                
                if (hasTarget) {
                    // Explicitly mark that Target refers to the main document
                    enhancedContext.hasTargetReference = true;
                    enhancedContext.targetDocument = {
                        title: this.titleField.value,
                        content: this.editor.textContent,
                        html: this.editor.innerHTML
                    };
                }
                
                // Update the command to make references clear to the AI
                let processedCommand = command;
                if (hasContext) {
                    processedCommand = processedCommand.replace(/\bContext\b/g, '[CONTEXT PANEL FILES]');
                }
                if (hasTarget) {
                    processedCommand = processedCommand.replace(/\bTarget\b/g, '[MAIN DOCUMENT]');
                }
                
                context = {
                    ...enhancedContext,
                    originalCommand: command,
                    processedCommand: processedCommand
                };
            }
            
            // Determine routing based on selection and token count
            const selection = window.getSelection();
            const hasSelection = selection && !selection.isCollapsed && selection.toString().trim();
            
            // Define token thresholds
            const GPT_TOKEN_LIMIT = 4000;
            const LARGE_DOCUMENT_THRESHOLD = 8000;
            
            // Routing logic
            let useGeminiPipeline = false;
            let routingReason = '';
            
            if (hasSelection) {
                // Selected text - use GPT-4.1
                routingReason = 'Selection-based edit';
                useGeminiPipeline = false;
            } else if (units.length === 1 && totalTokens < GPT_TOKEN_LIMIT) {
                // Single unit, small enough for GPT
                routingReason = 'Single section document';
                useGeminiPipeline = false;
            } else if (totalTokens > LARGE_DOCUMENT_THRESHOLD && hasTarget) {
                // Large document with Target reference - use Gemini pipeline
                routingReason = `Large document (${units.length} sections, ~${totalTokens} tokens)`;
                useGeminiPipeline = true;
            } else if (command.toLowerCase().includes('all sections') || 
                      command.toLowerCase().includes('entire document') ||
                      command.toLowerCase().includes('whole document')) {
                // Explicit full document command
                routingReason = 'Full document command';
                useGeminiPipeline = true;
            }
            
            // Add routing info to context
            context = {
                ...context,
                documentUnits: units,
                totalTokens: totalTokens,
                routing: {
                    useGeminiPipeline,
                    reason: routingReason
                }
            };
            
            this.addChatMessage('system', `🤖 ${routingReason} → ${useGeminiPipeline ? 'Gemini orchestration' : 'GPT-4.1'}`);
            
            if (useGeminiPipeline) {
                // Use Gemini pipeline for large documents
                await this.processWithGeminiPipeline(command, context);
                return;
            }
            
            // Check if this is an entity-related command
            const entityKeywords = ['entity', 'entities', 'person', 'people', 'organization', 
                                   'place', 'extract', 'find all', 'show all', 'list all',
                                   'rename', 'merge', 'highlight', 'facts about'];
            
            const lowerCommand = command.toLowerCase();
            const isEntityCommand = entityKeywords.some(keyword => lowerCommand.includes(keyword));
            
            // If entity system is available and command seems entity-related
            if (isEntityCommand && this.entityIndexer) {
                // Route to entity-specific processing
                await this.processEntityCommand(command);
                return;
            }
            
            // Check if this operation should use Claude
            const files = this.detectFilesInCommand(command);
            const shouldUseClaudeResponse = await fetch('/api/should-use-claude', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    command,
                    files,
                    isComplexEdit: files.length > 1
                })
            });
            
            const { useClaude } = await shouldUseClaudeResponse.json();
            
            // Show AI indicator
            this.showAIIndicator(useClaude ? 'Claude' : 'GPT-4.1');
            
            let endpoint = '/api/command';
            let requestBody = {
                command,
                context,
                stream: true
            };
            
            if (useClaude) {
                endpoint = '/api/claude-complex';
                requestBody = {
                    command,
                    files,
                    currentFile: this.titleField.value + '.md',
                    context: {
                        ...context,
                        notes: this.getGeminiContext() // Include context panel notes
                    },
                    sessionId: this.claudeSessionId // Keep track of Claude sessions
                };
            }
            
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('API Response Error:', response.status, errorText);
                throw new Error(`Command API error: ${response.status} - ${errorText}`);
            }
            
            // Handle streaming response
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer
                
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const dataStr = line.slice(6);
                            if (dataStr === '[DONE]') {
                                // Claude completion signal
                                continue;
                            }
                            const data = JSON.parse(dataStr);
                            
                            if (useClaude) {
                                this.handleClaudeResponse(data);
                            } else {
                                this.handleCommandResponse(data);
                            }
                        } catch (e) {
                            console.error('Failed to parse response:', line);
                        }
                    }
                }
            }
        } catch (error) {
            console.error('Error processing command:', error);
            this.addChatMessage('error', `Sorry, I encountered an error processing your command: ${error.message}`);
            throw error;
        }
    }
    
    async processWithGeminiPipeline(command, context) {
        try {
            this.addChatMessage('system', '🤖 Initializing Gemini orchestration pipeline...');
            
            const { documentUnits, totalTokens } = context;
            
            // Step 1: Send full document to Gemini for analysis and planning
            this.addChatMessage('system', '📋 Analyzing document structure and creating execution plan...');
            
            const planningResponse = await fetch('/api/gemini-plan', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    command,
                    documentStructure: {
                        units: documentUnits.map(unit => ({
                            id: unit.id,
                            title: unit.title,
                            tokens: unit.tokens,
                            preview: unit.content.substring(0, 200) + '...'
                        })),
                        totalTokens,
                        totalUnits: documentUnits.length
                    },
                    context: {
                        hasContextReference: context.hasContextReference,
                        hasTargetReference: context.hasTargetReference,
                        contextPanelContent: context.contextPanelContent
                    }
                })
            });
            
            if (!planningResponse.ok) {
                throw new Error('Failed to create execution plan');
            }
            
            const executionPlan = await planningResponse.json();
            
            // Display the plan to the user
            this.addChatMessage('assistant', `📋 **Execution Plan:**\n${executionPlan.summary}`);
            
            // Step 2: Process sections in parallel batches
            const PARALLEL_BATCH_SIZE = 3; // Process 3 sections at a time to avoid rate limits
            const unitResults = new Map();
            
            for (let i = 0; i < documentUnits.length; i += PARALLEL_BATCH_SIZE) {
                const batch = documentUnits.slice(i, i + PARALLEL_BATCH_SIZE);
                this.addChatMessage('system', `⚡ Processing sections ${i + 1} to ${Math.min(i + PARALLEL_BATCH_SIZE, documentUnits.length)}...`);
                
                // Process batch in parallel
                const batchPromises = batch.map(unit => 
                    this.processSingleUnit(unit, executionPlan.unitInstructions[unit.id], command, context)
                );
                
                const batchResults = await Promise.all(batchPromises);
                
                // Store results
                batch.forEach((unit, index) => {
                    unitResults.set(unit.id, batchResults[index]);
                });
                
                // Small delay between batches to avoid rate limiting
                if (i + PARALLEL_BATCH_SIZE < documentUnits.length) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }
            
            // Step 3: Send results to Gemini for review
            this.addChatMessage('system', '🔍 Reviewing changes for consistency and quality...');
            
            const reviewResponse = await fetch('/api/gemini-review', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    command,
                    originalUnits: documentUnits,
                    processedUnits: Array.from(unitResults.entries()).map(([id, result]) => ({
                        id,
                        originalContent: documentUnits.find(u => u.id === id).content,
                        processedContent: result.content,
                        changes: result.changes
                    })),
                    executionPlan
                })
            });
            
            if (!reviewResponse.ok) {
                throw new Error('Failed to review changes');
            }
            
            const reviewResult = await reviewResponse.json();
            
            // Step 4: Apply corrections if needed
            if (reviewResult.needsCorrection && reviewResult.corrections.length > 0) {
                this.addChatMessage('system', '🔧 Applying corrections based on review...');
                
                for (const correction of reviewResult.corrections) {
                    const unit = documentUnits.find(u => u.id === correction.unitId);
                    if (unit) {
                        const correctedResult = await this.processSingleUnit(
                            unit,
                            correction.instruction,
                            command,
                            context,
                            true // isCorrection flag
                        );
                        unitResults.set(unit.id, correctedResult);
                    }
                }
            }
            
            // Step 5: Apply all changes to the document
            this.addChatMessage('system', '✅ Applying changes to document...');
            
            // Reconstruct the document with processed units
            let newContent = '';
            for (const unit of documentUnits) {
                const result = unitResults.get(unit.id);
                if (result && result.content) {
                    newContent += result.content;
                    if (!result.content.endsWith('\n')) {
                        newContent += '\n';
                    }
                }
            }
            
            // Apply the new content
            this.editor.textContent = newContent;
            this.debounceObsidianFormatting();
            this.scheduleAutoSave();
            
            // Show summary
            const summary = reviewResult.summary || 'Changes applied successfully';
            this.addChatMessage('assistant', `✅ **Complete**: ${summary}`);
            
        } catch (error) {
            console.error('Error in Gemini pipeline:', error);
            this.addChatMessage('error', `Failed to process with Gemini pipeline: ${error.message}`);
            throw error;
        }
    }
    
    async processSingleUnit(unit, instruction, command, context, isCorrection = false) {
        try {
            const response = await fetch('/api/gpt-process-unit', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    unit: {
                        id: unit.id,
                        title: unit.title,
                        content: unit.content
                    },
                    instruction,
                    originalCommand: command,
                    context: {
                        hasContextReference: context.hasContextReference,
                        hasTargetReference: context.hasTargetReference,
                        contextPanelContent: context.contextPanelContent
                    },
                    isCorrection
                })
            });
            
            if (!response.ok) {
                throw new Error(`Failed to process unit ${unit.id}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error(`Error processing unit ${unit.id}:`, error);
            // Return original content on error
            return {
                content: unit.content,
                changes: [],
                error: error.message
            };
        }
    }
    
    handleCommandResponse(data) {
        switch (data.type) {
            case 'message':
                this.addChatMessage('assistant', data.content);
                break;
                
            case 'change':
                this.addPendingChange(data);
                break;
                
            case 'edit':
                if (this.entityProfileMode) {
                    this.applyEntitySnippetEdit(data);
                } else {
                    this.applyDirectEdit(data);
                }
                break;
                
            case 'function_call':
                // Log function calls for debugging
                console.log('AI Function Call:', data.function, data.arguments);
                break;
                
            case 'clarification':
                this.addChatMessage('assistant', data.question);
                break;
                
            case 'entities':
                // Handle entity extraction results (already handled in extractEntitiesFromText)
                break;
                
            case 'complete':
                // Don't show any completion messages - user doesn't want to see them
                this.directEditsApplied = 0;
                break;
                
            case 'error':
                this.addChatMessage('error', data.message);
                break;
        }
    }
    
    applyDirectEdit(data) {
        // Apply edits directly to the document based on the operation type
        switch (data.operation) {
            case 'replace_paragraph':
                this.replaceParagraph(data.paragraph_id, data.new_text);
                break;
                
            case 'replace_text':
                this.replaceTextGlobally(data.old_text, data.new_text);
                break;
                
            case 'append_text':
                this.appendText(data.text, data.after_paragraph_id);
                break;
                
            case 'write_document':
                this.writeDocument(data.content);
                break;
                
            default:
                console.warn('Unknown edit operation:', data.operation);
        }
        
        this.directEditsApplied++;
    }
    
    replaceParagraph(paragraphId, newText) {
        // Get all paragraphs (split by double newlines)
        const content = this.editor.innerHTML;
        const paragraphs = content.split(/(<p[^>]*>.*?<\/p>|\n\n)/);
        
        // Clean up and index paragraphs
        let actualParagraphs = [];
        let currentText = '';
        
        for (let i = 0; i < paragraphs.length; i++) {
            const part = paragraphs[i];
            if (part.match(/<p[^>]*>.*?<\/p>/) || (part.trim() && !part.match(/^\s*$/))) {
                if (currentText) {
                    actualParagraphs.push(currentText);
                    currentText = '';
                }
                actualParagraphs.push(part);
            } else {
                currentText += part;
            }
        }
        if (currentText) {
            actualParagraphs.push(currentText);
        }
        
        // Replace the specified paragraph
        const index = parseInt(paragraphId);
        if (index >= 0 && index < actualParagraphs.length) {
            // Preserve HTML structure if it's a <p> tag
            if (actualParagraphs[index].match(/^<p[^>]*>/)) {
                actualParagraphs[index] = actualParagraphs[index].replace(/>.*?<\/p>/, `>${newText}</p>`);
            } else {
                actualParagraphs[index] = newText;
            }
            
            // Reconstruct the content
            this.editor.innerHTML = actualParagraphs.join('');
            
            // Apply formatting
            this.applyFormattingToDocument();
            
            // Show a brief highlight on the edited paragraph
            this.highlightEditedParagraph(index);
        }
    }
    
    replaceTextGlobally(oldText, newText) {
        const content = this.editor.innerHTML;
        const escapedOldText = oldText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(escapedOldText, 'g');
        
        this.editor.innerHTML = content.replace(regex, newText);
        
        // Apply formatting
        this.applyFormattingToDocument();
    }
    
    highlightEditedParagraph(index) {
        // Find and highlight the edited paragraph briefly
        const paragraphs = this.editor.querySelectorAll('p, div');
        if (paragraphs[index]) {
            paragraphs[index].style.backgroundColor = 'rgba(76, 175, 80, 0.2)';
            paragraphs[index].style.transition = 'background-color 0.3s ease';
            
            setTimeout(() => {
                paragraphs[index].style.backgroundColor = '';
            }, 1500);
        }
    }
    
    appendText(text, afterParagraphId) {
        if (afterParagraphId) {
            // Insert after specific paragraph
            const paragraphs = this.editor.querySelectorAll('p, div');
            const index = parseInt(afterParagraphId.replace('P', ''));
            if (paragraphs[index]) {
                const newPara = document.createElement('p');
                newPara.textContent = text;
                paragraphs[index].insertAdjacentElement('afterend', newPara);
            } else {
                // Fallback to end
                this.editor.innerHTML += `<p>${text}</p>`;
            }
        } else {
            // Append to end
            this.editor.innerHTML += `<p>${text}</p>`;
        }
        
        // Apply formatting
        this.applyFormattingToDocument();
        this.scheduleAutoSave();
    }
    
    writeDocument(content) {
        // Replace entire document content
        this.editor.innerHTML = content;
        
        // Apply formatting
        this.applyFormattingToDocument();
        this.scheduleAutoSave();
    }
    
    applyFormattingToDocument() {
        // Save cursor position
        const selection = window.getSelection();
        const range = selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
        
        // Apply formatting
        const html = this.applyFormatting(this.editor.textContent);
        this.editor.innerHTML = html;
        
        // Process wiki links
        this.processWikiLinks();
        
        // Restore cursor if possible
        if (range) {
            try {
                selection.removeAllRanges();
                selection.addRange(range);
            } catch (e) {
                // Cursor restoration failed, that's okay
            }
        }
    }
    
    addPendingChange(changeData) {
        const change = {
            id: Date.now() + Math.random(),
            type: changeData.operation, // 'replace', 'insert', 'delete'
            startOffset: changeData.startOffset,
            endOffset: changeData.endOffset,
            oldText: changeData.oldText,
            newText: changeData.newText,
            applied: false
        };
        
        this.pendingChanges.push(change);
        this.applyChangePreview(change);
    }
    
    applyChangePreview(change) {
        // Find the text node and apply green highlighting
        const walker = document.createTreeWalker(
            this.editor,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let currentOffset = 0;
        let targetNode = null;
        
        while (walker.nextNode()) {
            const node = walker.currentNode;
            const nodeLength = node.textContent.length;
            
            if (currentOffset <= change.startOffset && 
                currentOffset + nodeLength > change.startOffset) {
                targetNode = node;
                break;
            }
            currentOffset += nodeLength;
        }
        
        if (targetNode) {
            const relativeStart = change.startOffset - currentOffset;
            const relativeEnd = Math.min(relativeStart + change.oldText.length, targetNode.textContent.length);
            
            // Split text node and wrap the change
            const beforeText = targetNode.textContent.substring(0, relativeStart);
            const changeText = targetNode.textContent.substring(relativeStart, relativeEnd);
            const afterText = targetNode.textContent.substring(relativeEnd);
            
            // Create new elements
            const container = document.createElement('span');
            container.className = 'ai-change-preview';
            container.dataset.changeId = change.id;
            container.innerHTML = `
                <span class="change-old">${changeText}</span>
                <span class="change-new">${change.newText}</span>
                <span class="change-controls">
                    <button class="accept-change" data-change-id="${change.id}">✓</button>
                    <button class="reject-change" data-change-id="${change.id}">✗</button>
                </span>
            `;
            
            // Replace the text node
            const parent = targetNode.parentNode;
            if (beforeText) {
                parent.insertBefore(document.createTextNode(beforeText), targetNode);
            }
            parent.insertBefore(container, targetNode);
            if (afterText) {
                parent.insertBefore(document.createTextNode(afterText), targetNode);
            }
            parent.removeChild(targetNode);
            
            // Add event listeners
            container.querySelector('.accept-change').addEventListener('click', () => {
                this.acceptChange(change.id);
            });
            
            container.querySelector('.reject-change').addEventListener('click', () => {
                this.rejectChange(change.id);
            });
        }
    }
    
    acceptChange(changeId) {
        const change = this.pendingChanges.find(c => c.id === changeId);
        if (!change) return;
        
        const element = document.querySelector(`[data-change-id="${changeId}"]`);
        if (element) {
            // Replace with the new text
            const textNode = document.createTextNode(change.newText);
            element.parentNode.replaceChild(textNode, element);
            change.applied = true;
        }
        
        this.updateAcceptAllButton();
    }
    
    rejectChange(changeId) {
        const change = this.pendingChanges.find(c => c.id === changeId);
        if (!change) return;
        
        const element = document.querySelector(`[data-change-id="${changeId}"]`);
        if (element) {
            // Replace with the old text
            const textNode = document.createTextNode(change.oldText);
            element.parentNode.replaceChild(textNode, element);
        }
        
        // Remove from pending changes
        this.pendingChanges = this.pendingChanges.filter(c => c.id !== changeId);
        this.updateAcceptAllButton();
    }
    
    acceptNextChange() {
        const nextChange = this.pendingChanges.find(c => !c.applied);
        if (nextChange) {
            this.acceptChange(nextChange.id);
        }
    }
    
    acceptAllChanges() {
        this.pendingChanges.forEach(change => {
            if (!change.applied) {
                this.acceptChange(change.id);
            }
        });
        this.clearPendingChanges();
    }
    
    clearPendingChanges() {
        // Remove all preview elements
        document.querySelectorAll('.ai-change-preview').forEach(el => {
            const textNode = document.createTextNode(el.querySelector('.change-old').textContent);
            el.parentNode.replaceChild(textNode, el);
        });
        
        this.pendingChanges = [];
        this.currentChangeIndex = 0;
        this.updateAcceptAllButton();
    }
    
    updateAcceptAllButton() {
        const acceptAllBtn = document.getElementById('accept-all-changes');
        const pendingCount = this.pendingChanges.filter(c => !c.applied).length;
        
        acceptAllBtn.disabled = pendingCount === 0;
        acceptAllBtn.textContent = pendingCount > 0 ? `Accept All (${pendingCount})` : 'Accept All';
    }
    
    createNewFile() {
        // Clear the title
        this.titleField.value = '';
        
        // Clear ALL pages
        this.removeAllPages();
        
        // Clear the main editor completely
        this.editor.innerHTML = '';
        
        // Add an empty paragraph to start with
        const p = document.createElement('p');
        p.innerHTML = '<br>'; // Empty paragraph with line break
        this.editor.appendChild(p);
        
        // Clear any footnote references
        const referencesDiv = document.getElementById('footnote-references');
        if (referencesDiv) {
            referencesDiv.remove();
        }
        
        // Reset tracking
        this.lastTitle = '';
        this.lastContent = '';
        this.currentPage = 1;
        
        // Clear version history
        this.history = [];
        this.historyIndex = -1;
        
        // Clear cutting room floor
        if (this.cuttingRoomEditor) {
            this.cuttingRoomEditor.innerHTML = '';
        }
        this.cuttingRoomContent = '';
        
        // Focus on title
        this.titleField.focus();
        
        this.showStatus('New document created', 2000);
    }
    
    async deleteCurrentFile() {
        const title = this.titleField.value;
        
        if (!title || title === 'untitled') {
            this.showStatus('No file to delete', 2000);
            return;
        }
        
        // Confirm deletion
        const confirmDiv = document.createElement('div');
        confirmDiv.className = 'delete-confirm';
        confirmDiv.innerHTML = `
            <div class="confirm-message">Delete "${title}"?</div>
            <div class="confirm-buttons">
                <button class="confirm-yes">Delete</button>
                <button class="confirm-no">Cancel</button>
            </div>
        `;
        confirmDiv.style.cssText = `
            position: fixed;
            bottom: 70px;
            left: 20px;
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
        `;
        
        document.body.appendChild(confirmDiv);
        
        confirmDiv.querySelector('.confirm-yes').addEventListener('click', async () => {
            try {
                // Delete from server
                const filename = `${title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.md`;
                const response = await fetch(`/api/delete/${filename}`, {
                    method: 'DELETE'
                });
                
                if (response.ok) {
                    this.createNewFile();
                    this.showStatus(`Deleted: ${title}`, 3000);
                } else {
                    this.showStatus('Error deleting file', 3000);
                }
            } catch (error) {
                console.error('Delete error:', error);
                this.showStatus('Error deleting file', 3000);
            }
            
            confirmDiv.remove();
        });
        
        confirmDiv.querySelector('.confirm-no').addEventListener('click', () => {
            confirmDiv.remove();
        });
        
        // Close on outside click
        setTimeout(() => {
            document.addEventListener('click', function closeConfirm(e) {
                if (!confirmDiv.contains(e.target)) {
                    confirmDiv.remove();
                    document.removeEventListener('click', closeConfirm);
                }
            });
        }, 100);
    }
    
    async showFootnoteBrowser() {
        const browser = document.getElementById('footnote-browser');
        const list = browser.querySelector('.footnote-list');
        const searchInput = browser.querySelector('.footnote-search');
        
        // Load footnotes
        await this.footnoteManager.loadFootnotes();
        
        // Display footnotes
        this.displayFootnotes(this.footnoteManager.footnotes);
        
        // Setup search
        searchInput.addEventListener('input', (e) => {
            const results = this.footnoteManager.searchFootnotes(e.target.value);
            this.displayFootnotes(results);
        });
        
        browser.classList.add('visible');
    }
    
    displayFootnotes(footnotes) {
        const list = document.querySelector('.footnote-list');
        
        if (footnotes.length === 0) {
            list.innerHTML = '<div style="text-align: center; color: #999;">No footnotes yet</div>';
            return;
        }
        
        list.innerHTML = footnotes.map(footnote => `
            <div class="footnote-item" data-id="${footnote.id}">
                <div class="footnote-url">${footnote.url}</div>
                <div class="footnote-text">${footnote.text}</div>
            </div>
        `).join('');
    }
    
    async showDocumentLoader() {
        const loader = document.getElementById('document-loader');
        const searchInput = document.getElementById('document-search');
        const documentList = document.getElementById('document-list');
        
        // Reset search
        searchInput.value = '';
        
        // Load documents
        try {
            // Show loading state
            documentList.innerHTML = '<div style="text-align: center; padding: 20px;">Loading documents...</div>';
            
            const response = await fetch('/api/documents');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            // Handle both old and new API response formats
            this.allDocuments = data.documents || data;
            this.displayDocuments(this.allDocuments);
            
            // Setup search with arrow key navigation
            let selectedIndex = -1;
            
            // Add search with debouncing
            let searchTimeout;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    const filtered = this.filterDocuments(e.target.value);
                    this.displayDocuments(filtered);
                    selectedIndex = -1;
                }, 300); // 300ms debounce
            });
            
            searchInput.addEventListener('keydown', (e) => {
                const items = documentList.querySelectorAll('.document-item');
                
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                    this.updateSelection(items, selectedIndex);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    selectedIndex = Math.max(selectedIndex - 1, 0);
                    this.updateSelection(items, selectedIndex);
                } else if (e.key === 'Enter') {
                    e.preventDefault();
                    if (selectedIndex >= 0 && items[selectedIndex]) {
                        const filename = items[selectedIndex].dataset.filename;
                        this.loadDocument(filename);
                        loader.classList.remove('visible');
                    } else if (items.length === 1) {
                        // Auto-select if only one result
                        const filename = items[0].dataset.filename;
                        this.loadDocument(filename);
                        loader.classList.remove('visible');
                    }
                } else if (e.key === 'Escape') {
                    loader.classList.remove('visible');
                }
            });
            
            // Click to load
            documentList.addEventListener('click', (e) => {
                const item = e.target.closest('.document-item');
                if (item) {
                    const filename = item.dataset.filename;
                    this.loadDocument(filename);
                    loader.classList.remove('visible');
                }
            });
            
            // Show loader
            loader.classList.add('visible');
            searchInput.focus();
            
            // Close on outside click
            setTimeout(() => {
                document.addEventListener('click', function closeLoader(e) {
                    if (!loader.contains(e.target) && e.target !== loader) {
                        loader.classList.remove('visible');
                        document.removeEventListener('click', closeLoader);
                    }
                });
            }, 100);
            
        } catch (error) {
            console.error('Error loading documents:', error);
            let errorMessage = 'Error loading documents';
            
            if (error.message && error.message.includes('404')) {
                errorMessage = 'Documents folder not found';
            } else if (error.message && error.message.includes('500')) {
                errorMessage = 'Server error - please try again';
            } else if (error.message && error.message.includes('Failed to fetch')) {
                errorMessage = 'Network error - please check your connection';
            }
            
            this.showStatus(errorMessage, 5000);
            documentList.innerHTML = `<div style="color: red; padding: 20px; text-align: center;">${errorMessage}</div>`;
        }
    }
    
    filterDocuments(query) {
        if (!query) return this.allDocuments;
        
        const lowercaseQuery = query.toLowerCase();
        return this.allDocuments.filter(doc => 
            doc.name.toLowerCase().includes(lowercaseQuery)
        );
    }
    
    displayDocuments(documents) {
        const list = document.getElementById('document-list');
        
        if (documents.length === 0) {
            list.innerHTML = '<div style="text-align: center; color: #999; padding: 20px;">No documents found</div>';
            return;
        }
        
        list.innerHTML = documents.map(doc => {
            const date = new Date(doc.modified).toLocaleDateString();
            const displayName = doc.name.replace('.md', '').replace(/_/g, ' ');
            
            return `
                <div class="document-item" data-filename="${doc.name}">
                    ${displayName}
                    <span class="doc-date">${date}</span>
                </div>
            `;
        }).join('');
    }
    
    updateSelection(items, index) {
        items.forEach((item, i) => {
            if (i === index) {
                item.classList.add('selected');
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('selected');
            }
        });
    }
    
    async loadDocument(filename) {
        // Prevent concurrent loads
        if (this.isLoadingDocument) {
            console.log('Document load already in progress');
            return;
        }
        
        this.isLoadingDocument = true;
        
        try {
            this.showStatus('Loading document...', 1000);
            
            const response = await fetch(`/api/load/${filename}`);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.error || `Failed to load document (${response.status})`);
            }
            
            const data = await response.json();
            
            // Update editor content
            this.titleField.value = data.title;
            
            // Clear ALL pages before loading new document
            this.removeAllPages();
            
            // Clear editor and set content
            this.editor.innerHTML = '';
            
            // Split content into paragraphs
            const lines = data.content.split('\n');
            let currentParagraph = '';
            
            for (const line of lines) {
                const trimmedLine = line.trim();
                
                if (trimmedLine === '') {
                    // Empty line - end current paragraph
                    if (currentParagraph) {
                        const p = document.createElement('p');
                        p.textContent = currentParagraph;
                        this.editor.appendChild(p);
                        currentParagraph = '';
                    }
                } else if (trimmedLine.startsWith('#')) {
                    // Heading
                    if (currentParagraph) {
                        const p = document.createElement('p');
                        p.textContent = currentParagraph;
                        this.editor.appendChild(p);
                        currentParagraph = '';
                    }
                    
                    const level = trimmedLine.match(/^#+/)[0].length;
                    const text = trimmedLine.replace(/^#+\s*/, '');
                    const heading = document.createElement(`h${Math.min(level, 6)}`);
                    heading.textContent = text;
                    this.editor.appendChild(heading);
                } else if (trimmedLine.startsWith('- ') || trimmedLine.startsWith('* ')) {
                    // List item
                    if (currentParagraph) {
                        const p = document.createElement('p');
                        p.textContent = currentParagraph;
                        this.editor.appendChild(p);
                        currentParagraph = '';
                    }
                    
                    // Check if we need to create a new list
                    let ul = this.editor.lastElementChild;
                    if (!ul || ul.tagName !== 'UL') {
                        ul = document.createElement('ul');
                        this.editor.appendChild(ul);
                    }
                    
                    const li = document.createElement('li');
                    li.textContent = trimmedLine.substring(2);
                    ul.appendChild(li);
                } else {
                    // Regular text - add to current paragraph
                    if (currentParagraph) {
                        currentParagraph += ' ' + trimmedLine;
                    } else {
                        currentParagraph = trimmedLine;
                    }
                }
            }
            
            // Add any remaining paragraph
            if (currentParagraph) {
                const p = document.createElement('p');
                p.textContent = currentParagraph;
                this.editor.appendChild(p);
            }
            
            // If no content was added, add a single paragraph
            if (this.editor.children.length === 0) {
                const p = document.createElement('p');
                p.textContent = data.content || '';
                this.editor.appendChild(p);
            }
            
            // Process wiki links in the loaded content
            this.processWikiLinks();
            
            // Apply formatting to the loaded content
            this.applyFormattingToDocument();
            
            // Reset tracking
            this.lastTitle = data.title;
            this.lastContent = data.content;
            
            // DISABLED - PAGINATION IS BROKEN
            // requestAnimationFrame(() => {
            //     setTimeout(() => {
            //         this.simplePaginate();
            //     }, 100);
            // });
            
            // Load version history for this document
            await this.loadVersionHistoryForCurrentDocument();
            
            // Load cutting room content for this document
            await this.loadCuttingRoomContent();
            
            // Load entity data for this document
            await this.loadEntityData(filename);
            
            // Show indexing status
            this.showStatus('Indexing document...', 1000);
            
            // Trigger entity indexing
            if (this.entityIndexer) {
                this.entityIndexer.scheduleHeavyPass();
            }
            
            this.showStatus(`Loaded: ${data.title}`, 3000);
        } catch (error) {
            console.error('Error loading document:', error);
            
            let errorMessage = 'Error loading document';
            if (error.message.includes('404')) {
                errorMessage = 'Document not found';
            } else if (error.message.includes('Invalid filename')) {
                errorMessage = 'Invalid document name';
            } else if (error.message.includes('network')) {
                errorMessage = 'Network error - please check connection';
            } else if (error.message) {
                errorMessage = error.message;
            }
            
            this.showStatus(errorMessage, 5000);
        } finally {
            this.isLoadingDocument = false;
        }
    }
    
    setupEventListeners() {
        // Title field events
        this.titleField.addEventListener('input', () => this.scheduleAutoSave());
        
        // Editor events
        this.editor.addEventListener('input', (e) => {
            // Mark as actively typing
            this.isActivelyTyping = true;
            clearTimeout(this.typingTimer);
            this.typingTimer = setTimeout(() => {
                this.isActivelyTyping = false;
            }, 200);
            
            const text = this.editor.textContent;
            const lastTwo = text.slice(-2);
            
            // Check for '//' URL syntax
            if (lastTwo === '//') {
                this.handleUrlFootnote();
            }
            
            // Check for '[[' wiki link syntax
            if (lastTwo === '[[') {
                // Auto-insert closing ]]
                const selection = window.getSelection();
                const range = selection.getRangeAt(0);
                const textNode = range.startContainer;
                const offset = range.startOffset;
                
                // Insert ]] after cursor
                const before = textNode.textContent.substring(0, offset);
                const after = textNode.textContent.substring(offset);
                textNode.textContent = before + ']]' + after;
                
                // Position cursor between [[ and ]]
                range.setStart(textNode, offset);
                range.setEnd(textNode, offset);
                selection.removeAllRanges();
                selection.addRange(range);
                
                this.showWikiAutocomplete();
            }
            
            // Update wiki link autocomplete if active
            if (this.wikiAutocompleteActive) {
                this.updateWikiAutocomplete();
            }
            
            // Apply Obsidian-style formatting after input (debounced)
            this.debounceObsidianFormatting();
            
            // Highlight "Context" word when typed
            this.highlightContextWord();
            
            // Check if we just typed punctuation
            const lastChar = text[text.length - 1];
            if (['.', '!', '?'].includes(lastChar)) {
                // Set a 2-second timer to process gaps
                if (this.punctuationTimeout) {
                    clearTimeout(this.punctuationTimeout);
                }
                this.punctuationTimeout = setTimeout(() => {
                    console.log('2 seconds after punctuation - processing gaps');
                    this.processSentenceCompletion();
                }, 2000);
            }
            
            // Also check for space after punctuation (immediate processing)
            if (lastTwo.length === 2 && lastTwo[1] === ' ' && ['.', '!', '?'].includes(lastTwo[0])) {
                console.log('Space after punctuation - processing gaps immediately');
                if (this.punctuationTimeout) {
                    clearTimeout(this.punctuationTimeout);
                }
                this.processSentenceCompletion();
            }
            
            // Check for deleted footnotes
            this.checkFootnoteDeletion();
            
            this.scheduleAutoSave();
        });
        
        // Handle footnote double-clicks and word highlighting
        this.editor.addEventListener('dblclick', (e) => {
            if (e.target.classList.contains('footnote-number')) {
                this.showFootnotePopup(e.target, e);
            } else {
                // Handle word highlighting
                this.handleWordHighlight(e);
            }
        });
        
        // Clear word highlighting when clicking outside editor
        document.addEventListener('click', (e) => {
            if (!this.editor.contains(e.target)) {
                this.clearWordHighlighting();
            }
        });
        
        // Open chat window with Cmd/Ctrl + Shift + Space
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.code === 'Space') {
                e.preventDefault();
                this.toggleCommandChatbox();
            }
        });
        
        // Handle keyboard events
        this.editor.addEventListener('keydown', (e) => {
            // Handle bullet point behavior
            if (e.key === 'Enter' && !e.shiftKey) {
                const selection = window.getSelection();
                if (selection.rangeCount > 0) {
                    const range = selection.getRangeAt(0);
                    
                    // Check if we're inside a list item
                    let listItem = range.startContainer.nodeType === Node.TEXT_NODE 
                        ? range.startContainer.parentElement 
                        : range.startContainer;
                    
                    // Find the closest LI element
                    while (listItem && listItem.tagName !== 'LI' && listItem !== this.editor) {
                        listItem = listItem.parentElement;
                    }
                    
                    if (listItem && listItem.tagName === 'LI') {
                        e.preventDefault();
                        
                        const content = listItem.textContent.trim();
                        
                        if (content === '') {
                            // Empty list item - exit list mode
                            const ul = listItem.parentElement;
                            const newP = document.createElement('p');
                            newP.innerHTML = '<br>';
                            
                            // Insert paragraph after the list
                            ul.parentElement.insertBefore(newP, ul.nextSibling);
                            
                            // Remove empty list item
                            listItem.remove();
                            
                            // If list is now empty, remove it
                            if (ul.children.length === 0) {
                                ul.remove();
                            }
                            
                            // Focus on new paragraph
                            const newRange = document.createRange();
                            newRange.selectNodeContents(newP);
                            newRange.collapse(true);
                            selection.removeAllRanges();
                            selection.addRange(newRange);
                        } else {
                            // Create new list item
                            const newLi = document.createElement('li');
                            newLi.innerHTML = '<br>';
                            
                            // Insert after current list item
                            listItem.parentElement.insertBefore(newLi, listItem.nextSibling);
                            
                            // Focus on new list item
                            const newRange = document.createRange();
                            newRange.selectNodeContents(newLi);
                            newRange.collapse(true);
                            selection.removeAllRanges();
                            selection.addRange(newRange);
                        }
                        
                        // Apply formatting after DOM change
                        this.debounceObsidianFormatting();
                        return;
                    }
                    
                    // Check if we're in plain text that starts with * or •
                    const node = range.startContainer;
                    const text = node.textContent || '';
                    const beforeCursor = text.substring(0, range.startOffset);
                    const afterCursor = text.substring(range.startOffset);
                    
                    // Check if current line starts with bullet
                    const lastNewline = beforeCursor.lastIndexOf('\n');
                    const currentLine = beforeCursor.substring(lastNewline + 1);
                    
                    if (currentLine.trim().startsWith('*')) {
                        e.preventDefault();
                        
                        // Just add a new line with asterisk
                        const textBefore = beforeCursor;
                        const newText = textBefore + '\n* ' + afterCursor;
                        node.textContent = newText;
                        
                        // Position cursor after new asterisk
                        const newRange = document.createRange();
                        newRange.setStart(node, textBefore.length + 3); // +3 for '\n* '
                        newRange.collapse(true);
                        selection.removeAllRanges();
                        selection.addRange(newRange);
                        
                        // Apply formatting to convert to list
                        this.debounceObsidianFormatting();
                    }
                }
            }
            
            // Handle Tab for bullet indentation
            if (e.key === 'Tab' && !e.shiftKey) {
                const selection = window.getSelection();
                if (selection.rangeCount > 0) {
                    const range = selection.getRangeAt(0);
                    
                    // Check if we're inside a list item
                    let listItem = range.startContainer.nodeType === Node.TEXT_NODE 
                        ? range.startContainer.parentElement 
                        : range.startContainer;
                    
                    // Find the closest LI element
                    while (listItem && listItem.tagName !== 'LI' && listItem !== this.editor) {
                        listItem = listItem.parentElement;
                    }
                    
                    if (listItem && listItem.tagName === 'LI') {
                        e.preventDefault();
                        
                        // Create a nested list
                        let nestedUl = listItem.querySelector('ul');
                        if (!nestedUl) {
                            nestedUl = document.createElement('ul');
                            listItem.appendChild(nestedUl);
                        }
                        
                        // Move content to nested list
                        const newLi = document.createElement('li');
                        newLi.innerHTML = listItem.childNodes[0].textContent || '<br>';
                        nestedUl.appendChild(newLi);
                        
                        // Remove original text
                        if (listItem.childNodes[0].nodeType === Node.TEXT_NODE) {
                            listItem.childNodes[0].remove();
                        }
                        
                        // Focus on nested item
                        const newRange = document.createRange();
                        newRange.selectNodeContents(newLi);
                        newRange.collapse(false);
                        selection.removeAllRanges();
                        selection.addRange(newRange);
                        
                        return;
                    }
                    
                    // Handle plain text with asterisk
                    const node = range.startContainer;
                    const text = node.textContent || '';
                    const beforeCursor = text.substring(0, range.startOffset);
                    
                    // Check if current line starts with *
                    const lastNewline = beforeCursor.lastIndexOf('\n');
                    const lineStart = lastNewline + 1;
                    const currentLine = text.substring(lineStart);
                    
                    if (currentLine.trim().startsWith('*')) {
                        e.preventDefault();
                        
                        // Add indent before asterisk
                        const beforeLine = text.substring(0, lineStart);
                        const afterAsterisk = currentLine.substring(currentLine.indexOf('*'));
                        const newText = beforeLine + '    ' + afterAsterisk;
                        node.textContent = newText;
                        
                        // Restore cursor position
                        const newRange = document.createRange();
                        newRange.setStart(node, range.startOffset + 4);
                        newRange.collapse(true);
                        selection.removeAllRanges();
                        selection.addRange(newRange);
                        
                        // Apply formatting
                        this.debounceObsidianFormatting();
                    }
                }
            }
            
            // Handle Shift+Tab for bullet outdent
            if (e.key === 'Tab' && e.shiftKey) {
                const selection = window.getSelection();
                if (selection.rangeCount > 0) {
                    const range = selection.getRangeAt(0);
                    const node = range.startContainer;
                    const text = node.textContent || '';
                    const beforeCursor = text.substring(0, range.startOffset);
                    
                    // Check if we're on an indented bullet line
                    const lastNewline = beforeCursor.lastIndexOf('\n');
                    const lineStart = lastNewline + 1;
                    const currentLine = text.substring(lineStart, range.startOffset);
                    
                    const bulletMatch = currentLine.match(/^(\s+)(•|◦|○|\*)/);
                    if (bulletMatch && bulletMatch[1].length >= 4) {
                        e.preventDefault();
                        
                        const currentIndent = bulletMatch[1];
                        const currentBullet = bulletMatch[2];
                        
                        // Remove 4 spaces of indent
                        const newIndent = currentIndent.substring(4);
                        
                        // Determine new bullet style based on indent level
                        let newBullet = '•'; // Default back to solid bullet
                        if (newIndent.length >= 4) {
                            newBullet = '◦'; // Still nested, use hollow
                        }
                        
                        const restOfLine = text.substring(lineStart + bulletMatch[0].length);
                        const beforeLine = text.substring(0, lineStart);
                        
                        // Replace the line with outdented version
                        const newText = beforeLine + newIndent + newBullet + restOfLine;
                        node.textContent = newText;
                        
                        // Restore cursor position
                        const newCursorPos = Math.max(lineStart, range.startOffset - 4); // Removed 4 spaces
                        const newRange = document.createRange();
                        newRange.setStart(node, newCursorPos);
                        newRange.collapse(true);
                        selection.removeAllRanges();
                        selection.addRange(newRange);
                    }
                }
            }
            
            // Handle wiki autocomplete
            if (this.wikiAutocompleteActive) {
                if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    const items = this.wikiDropdown.querySelectorAll('.wiki-suggestion');
                    this.wikiSelectedIndex = Math.min(this.wikiSelectedIndex + 1, items.length - 1);
                    this.updateWikiSelection(items);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    const items = this.wikiDropdown.querySelectorAll('.wiki-suggestion');
                    this.wikiSelectedIndex = Math.max(this.wikiSelectedIndex - 1, 0);
                    this.updateWikiSelection(items);
                } else if (e.key === 'Enter' || e.key === 'Tab') {
                    e.preventDefault();
                    const items = this.wikiDropdown.querySelectorAll('.wiki-suggestion');
                    const selectedItem = items[this.wikiSelectedIndex];
                    
                    if (selectedItem) {
                        if (selectedItem.classList.contains('url-option')) {
                            const url = selectedItem.dataset.url;
                            this.insertWikiLink(url);
                        } else if (selectedItem.dataset.filename) {
                            // Extract just the display name without the icon
                            const displayName = selectedItem.textContent.replace(/^[📄🔗]\s*/, '').trim();
                            this.insertWikiLink(displayName);
                        } else if (selectedItem.classList.contains('no-results')) {
                            // Create new note with current query
                            const text = this.editor.textContent;
                            const startIndex = text.lastIndexOf('[[');
                            const query = text.substring(startIndex + 2);
                            this.insertWikiLink(query);
                        }
                    }
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    this.closeWikiAutocomplete();
                }
            }
        });
        
        // Handle AI suggestion clicks
        this.editor.addEventListener('click', (e) => {
            if (e.target.classList.contains('ai-suggestion')) {
                e.preventDefault();
                e.stopPropagation();
                
                // Check for double-click
                const now = Date.now();
                const lastClick = e.target.lastClick || 0;
                
                if (now - lastClick < 300) {
                    // Double click - accept immediately
                    this.acceptSuggestion(e.target);
                } else {
                    // Single click - show menu
                    e.target.lastClick = now;
                    this.showSuggestionMenu(e.target, e);
                }
            }
        });
    }
    
    
    async processSentenceCompletion() {
        // Prevent multiple simultaneous processing
        if (this.isProcessing) {
            console.log('Already processing gaps, skipping...');
            return;
        }
        
        this.isProcessing = true;
        const content = this.editor.textContent;
        console.log('Full content:', content);
        const gaps = this.findGaps(content);
        
        console.log('Processing sentence completion. Found gaps:', gaps);
        
        if (gaps.length > 0) {
            this.showStatus('Processing gaps...');
            
            // Process only the first gap to avoid conflicts
            const gap = gaps[0];
            console.log('Processing gap:', gap);
            await this.processGap(gap);
            
            this.hideStatus();
        } else {
            console.log('No gaps found in content');
        }
        
        this.isProcessing = false;
    }
    
    findGaps(text) {
        const gaps = [];
        
        // Find [?] patterns
        const questionGaps = [...text.matchAll(/\[\?\]/g)];
        questionGaps.forEach(match => {
            gaps.push({
                type: 'question',
                index: match.index,
                length: match[0].length,
                content: match[0]
            });
        });
        
        // Find [description] patterns
        const descriptionGaps = [...text.matchAll(/\[([^\]]+)\]/g)];
        descriptionGaps.forEach(match => {
            if (match[1] !== '?') {
                gaps.push({
                    type: 'description',
                    index: match.index,
                    length: match[0].length,
                    content: match[0],
                    description: match[1]
                });
            }
        });
        
        return gaps.sort((a, b) => a.index - b.index);
    }
    
    async processGap(gap) {
        const context = this.getContextForGap(gap);
        
        try {
            const result = await this.getGeminiSuggestion(context, gap);
            console.log('Got result:', result);
            
            if (result && result.suggestion) {
                // Check if we have citations
                if (result.citations && result.citations.length > 0) {
                    // Add footnote markers to the suggestion
                    const footnotedSuggestion = this.addFootnotesToSuggestion(result.suggestion, result.citations);
                    this.replaceGapWithSuggestion(gap, footnotedSuggestion.text);
                    
                    // Add citations to the end of the document
                    this.appendCitations(footnotedSuggestion.citations);
                } else {
                    // No citations, just replace the gap
                    this.replaceGapWithSuggestion(gap, result.suggestion);
                }
            }
        } catch (error) {
            console.error('Error processing gap:', error);
            this.showStatus('Error processing gap', 3000);
        }
    }
    
    getContextForGap(gap) {
        const content = this.editor.textContent;
        const startIndex = Math.max(0, gap.index - 200);
        const endIndex = Math.min(content.length, gap.index + gap.length + 200);
        
        return {
            before: content.substring(startIndex, gap.index),
            gap: gap.content,
            after: content.substring(gap.index + gap.length, endIndex),
            description: gap.description || null
        };
    }
    
    async getGeminiSuggestion(context, gap) {
        try {
            // Get additional context from the context panel
            const additionalContext = this.getGeminiContext();
            
            const response = await fetch('/api/fill-gap', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    context, 
                    gap,
                    additionalContext 
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to get suggestion');
            }
            
            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Error getting suggestion:', error);
            
            // Fallback to simple suggestions if API fails
            if (gap.type === 'description') {
                const desc = gap.description.toLowerCase();
                if (desc.includes('capital')) return 'London';
                if (desc.includes('date')) return '1492';
                if (desc.includes('synonym')) return 'alternative';
            }
            
            return null;
        }
    }
    
    replaceGapWithSuggestion(gap, suggestion) {
        // Work with text content first to find the exact position
        const text = this.editor.textContent;
        const gapIndex = text.indexOf(gap.content);
        
        if (gapIndex === -1) {
            console.log('Gap not found in text');
            return;
        }
        
        // Create a range for the gap
        const walker = document.createTreeWalker(
            this.editor,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let currentIndex = 0;
        let targetNode = null;
        let targetOffset = 0;
        
        while (walker.nextNode()) {
            const node = walker.currentNode;
            const nodeLength = node.textContent.length;
            
            if (currentIndex + nodeLength >= gapIndex) {
                targetNode = node;
                targetOffset = gapIndex - currentIndex;
                break;
            }
            currentIndex += nodeLength;
        }
        
        if (!targetNode) {
            console.log('Could not find text node for gap');
            return;
        }
        
        // Create and insert the suggestion span
        const suggestionSpan = document.createElement('span');
        suggestionSpan.className = 'ai-suggestion';
        suggestionSpan.setAttribute('data-original', gap.content);
        suggestionSpan.textContent = suggestion;
        
        // Split the text node and insert the suggestion
        const afterGap = targetNode.splitText(targetOffset + gap.content.length);
        targetNode.deleteData(targetOffset, gap.content.length);
        targetNode.parentNode.insertBefore(suggestionSpan, afterGap);
        
        console.log('Successfully replaced gap with suggestion');
        this.restoreCursorPosition();
    }
    
    
    restoreCursorPosition() {
        // Place cursor at end of editor
        const range = document.createRange();
        const selection = window.getSelection();
        
        range.selectNodeContents(this.editor);
        range.collapse(false);
        
        selection.removeAllRanges();
        selection.addRange(range);
    }
    
    showSuggestionMenu(element, event) {
        // Remove any existing menu
        const existingMenu = document.querySelector('.suggestion-menu');
        if (existingMenu) {
            existingMenu.remove();
        }
        
        // Create menu
        const menu = document.createElement('div');
        menu.className = 'suggestion-menu';
        menu.innerHTML = `
            <button class="menu-accept">✓ Accept</button>
            <button class="menu-reject">✗ Reject</button>
        `;
        
        // Position menu at the click location
        menu.style.position = 'absolute';
        menu.style.left = (event.pageX - 50) + 'px'; // Center it on click
        menu.style.top = (event.pageY + 5) + 'px';
        
        document.body.appendChild(menu);
        
        // Handle menu clicks
        menu.querySelector('.menu-accept').addEventListener('click', () => {
            this.acceptSuggestion(element);
            menu.remove();
        });
        
        menu.querySelector('.menu-reject').addEventListener('click', () => {
            this.rejectSuggestion(element);
            menu.remove();
        });
        
        // Remove menu when clicking elsewhere
        setTimeout(() => {
            document.addEventListener('click', function removeMenu(e) {
                if (!menu.contains(e.target)) {
                    menu.remove();
                    document.removeEventListener('click', removeMenu);
                }
            });
        }, 100);
    }
    
    acceptSuggestion(element) {
        console.log('Accepting suggestion:', element.textContent);
        const text = element.textContent;
        const textNode = document.createTextNode(text);
        element.parentNode.replaceChild(textNode, element);
        
        this.scheduleAutoSave();
    }
    
    rejectSuggestion(element) {
        const original = element.getAttribute('data-original');
        const textNode = document.createTextNode(original);
        element.parentNode.replaceChild(textNode, element);
        
        this.scheduleAutoSave();
    }
    
    addFootnotesToSuggestion(text, citations) {
        // Find existing footnote numbers to get the next number
        const existingNumbers = this.editor.querySelectorAll('.footnote-number').length;
        let nextNum = existingNumbers + 1;
        
        // We'll add superscript numbers after inserting the text
        const citationMap = [];
        
        citations.forEach((citation, index) => {
            const footnoteNum = nextNum + index;
            citationMap.push({
                number: footnoteNum,
                url: citation
            });
        });
        
        return {
            text: text,
            citations: citationMap
        };
    }
    
    appendCitations(citations) {
        if (!citations || citations.length === 0) return;
        
        // Add references using the same Word-style format
        citations.forEach(citation => {
            this.appendFootnoteReference(citation.number, citation.url);
        });
        
        // Add superscript numbers after the suggestion
        const selection = window.getSelection();
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            const container = range.startContainer;
            
            citations.forEach(citation => {
                const sup = document.createElement('sup');
                sup.className = 'footnote-number';
                sup.setAttribute('data-footnote', citation.number);
                sup.textContent = citation.number;
                sup.title = citation.url;
                
                if (container.parentNode) {
                    container.parentNode.insertBefore(sup, container.nextSibling);
                }
            });
        }
        
        this.scheduleAutoSave();
    }
    
    scheduleAutoSave() {
        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }
        
        this.saveTimeout = setTimeout(() => {
            this.autoSave();
        }, 500); // Save after 500ms of no typing
    }
    
    async autoSave() {
        const title = this.titleField.value || 'untitled';
        
        // Convert wiki links back to [[]] format for saving
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = this.editor.innerHTML;
        
        // Convert wiki links back to [[]] syntax
        const wikiLinks = tempDiv.querySelectorAll('.wiki-link');
        wikiLinks.forEach(link => {
            const linkText = link.textContent;
            const wikiSyntax = document.createTextNode(`[[${linkText}]]`);
            link.parentNode.replaceChild(wikiSyntax, link);
        });
        
        const content = tempDiv.textContent;
        
        if (content === this.lastContent && title === this.lastTitle) {
            return;
        }
        
        try {
            const response = await fetch('/api/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ title, content })
            });
            
            if (!response.ok) {
                throw new Error('Failed to save');
            }
            
            const data = await response.json();
            
            this.lastContent = content;
            this.lastTitle = title;
            
            // Save entity data as metadata
            if (this.entityIndexer) {
                await this.saveEntityData(data.filename);
            }
            
            this.showStatus(`Saved to Obsidian: ${data.filename}`, 3000);
        } catch (error) {
            console.error('Error saving:', error);
            this.showStatus('Error saving document', 3000);
        }
    }
    
    loadLastDocument() {
        // TODO: Implement loading last document
        // For now, just set placeholder content
        
        // Process any existing wiki links
        this.processWikiLinks();
    }
    
    applyFormatting(text) {
        // Convert plain text to formatted HTML
        if (!text) return '';
        
        // Split into lines and process
        const lines = text.split('\n');
        const formattedLines = [];
        
        for (const line of lines) {
            const trimmed = line.trim();
            
            // Headings
            if (trimmed.startsWith('#')) {
                const level = trimmed.match(/^#+/)[0].length;
                const content = trimmed.replace(/^#+\s*/, '');
                formattedLines.push(`<h${Math.min(level, 6)}>${content}</h${Math.min(level, 6)}>`);
            }
            // Lists
            else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
                formattedLines.push(`<li>${trimmed.substring(2)}</li>`);
            }
            // Empty line = paragraph break
            else if (trimmed === '') {
                formattedLines.push('<br>');
            }
            // Regular text
            else {
                formattedLines.push(`<p>${trimmed}</p>`);
            }
        }
        
        // Wrap consecutive list items in <ul>
        let html = formattedLines.join('\n');
        html = html.replace(/(<li>.*<\/li>\n?)+/g, match => `<ul>${match}</ul>`);
        
        return html;
    }
    
    highlightContextWord() {
        // Highlight the word "Context" when typed
        const content = this.editor.textContent;
        const contextRegex = /\bContext\b/gi;
        
        if (contextRegex.test(content)) {
            // Save cursor position
            const selection = window.getSelection();
            const range = selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
            const offset = range ? range.startOffset : 0;
            
            // Apply highlighting
            let html = this.editor.innerHTML;
            html = html.replace(contextRegex, '<span class="context-highlight">Context</span>');
            this.editor.innerHTML = html;
            
            // Try to restore cursor position
            if (range) {
                try {
                    const newRange = document.createRange();
                    const textNode = this.editor.firstChild;
                    if (textNode) {
                        newRange.setStart(textNode, Math.min(offset, textNode.length));
                        newRange.collapse(true);
                        selection.removeAllRanges();
                        selection.addRange(newRange);
                    }
                } catch (e) {
                    // Cursor restoration failed
                }
            }
        }
    }
    
    processWikiLinks() {
        // Find all [[wiki links]] in the content
        const content = this.editor.innerHTML;
        const wikiLinkPattern = /\[\[([^\]]+)\]\]/g;
        
        let newContent = content;
        let match;
        
        while ((match = wikiLinkPattern.exec(content)) !== null) {
            const linkText = match[1];
            
            // Check if it's a URL
            const isURL = linkText.match(/^https?:\/\//);
            
            if (isURL) {
                const linkHtml = `<a class="wiki-link external-link" href="${linkText}" target="_blank">${linkText}</a>`;
                newContent = newContent.replace(match[0], linkHtml);
            } else {
                // Handle as note reference
                const linkHtml = `<a class="wiki-link note-link" data-note="${linkText}" href="#">${linkText}</a>`;
                newContent = newContent.replace(match[0], linkHtml);
            }
        }
        
        if (newContent !== content) {
            this.editor.innerHTML = newContent;
            this.setupWikiLinkHandlers();
        }
    }
    
    setupWikiLinkHandlers() {
        const wikiLinks = this.editor.querySelectorAll('.wiki-link');
        wikiLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                if (link.classList.contains('external-link')) {
                    // External links open in new tab (default behavior)
                    return;
                } else {
                    // Note links load the note
                    e.preventDefault();
                    const noteName = e.target.dataset.note;
                    this.loadWikiLink(noteName);
                }
            });
        });
    }
    
    async loadWikiLink(noteName) {
        try {
            // First try exact match with .md extension
            let filename = noteName.endsWith('.md') ? noteName : `${noteName}.md`;
            
            // Try to load the document
            const response = await fetch(`/api/documents/${filename}`);
            
            if (!response.ok) {
                // Try with sanitized filename
                filename = `${noteName.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.md`;
                await this.loadDocument(filename);
            } else {
                await this.loadDocument(filename);
            }
            
            // Update recently used documents
            const recentlyUsed = JSON.parse(localStorage.getItem('recentlyUsedDocs') || '[]');
            const updatedRecent = [filename, ...recentlyUsed.filter(f => f !== filename)].slice(0, 20);
            localStorage.setItem('recentlyUsedDocs', JSON.stringify(updatedRecent));
            
        } catch (error) {
            this.showStatus(`Note not found: ${noteName}`, 3000);
        }
    }
    
    async showWikiAutocomplete() {
        // Get cursor position
        const selection = window.getSelection();
        const range = selection.getRangeAt(0);
        const rect = range.getBoundingClientRect();
        
        // Create autocomplete dropdown
        const dropdown = document.createElement('div');
        dropdown.className = 'wiki-autocomplete';
        dropdown.style.left = rect.left + 'px';
        dropdown.style.top = (rect.bottom + 5) + 'px';
        
        // Load all documents
        try {
            const response = await fetch('/api/documents');
            const documents = await response.json();
            this.wikiDocuments = documents;
            this.wikiAutocompleteActive = true;
            this.wikiSelectedIndex = 0;
            
            this.displayWikiSuggestions(dropdown, documents);
            document.body.appendChild(dropdown);
            
            // Store references
            this.wikiDropdown = dropdown;
            this.wikiStartOffset = this.getTextOffset(range.startContainer) + range.startOffset - 2;
            
        } catch (error) {
            console.error('Error loading documents:', error);
        }
    }
    
    updateWikiAutocomplete() {
        if (!this.wikiDropdown) return;
        
        // Get the current text after [[
        const text = this.editor.textContent;
        const startIndex = text.lastIndexOf('[[');
        if (startIndex === -1) {
            this.closeWikiAutocomplete();
            return;
        }
        
        const query = text.substring(startIndex + 2);
        
        // Check if we've closed the link
        if (query.includes(']]')) {
            this.closeWikiAutocomplete();
            return;
        }
        
        // Filter documents
        const filtered = this.wikiDocuments.filter(doc => {
            const displayName = doc.name.replace('.md', '').replace(/_/g, ' ');
            return displayName.toLowerCase().includes(query.toLowerCase());
        });
        
        this.displayWikiSuggestions(this.wikiDropdown, filtered);
    }
    
    displayWikiSuggestions(dropdown, documents) {
        // Get current query
        const text = this.editor.textContent;
        const startIndex = text.lastIndexOf('[[');
        const query = startIndex >= 0 ? text.substring(startIndex + 2).replace(']]', '') : '';
        
        // Get recently used documents from localStorage
        const recentlyUsed = JSON.parse(localStorage.getItem('recentlyUsedDocs') || '[]');
        
        let html = '';
        let suggestionIndex = 0;
        
        // Add URL option if query looks like a URL
        if (query.match(/^https?:\/\//) || (query.includes('.') && query.includes('/'))) {
            html += `<div class="wiki-suggestion url-option ${this.wikiSelectedIndex === suggestionIndex ? 'selected' : ''}" data-url="${query}">
                        <span class="suggestion-icon">🔗</span> Use as URL: ${query}
                     </div>`;
            suggestionIndex++;
        }
        
        // Sort documents - recently used first, then alphabetically
        const sortedDocs = [...documents].sort((a, b) => {
            const aIndex = recentlyUsed.indexOf(a.name);
            const bIndex = recentlyUsed.indexOf(b.name);
            
            if (aIndex !== -1 && bIndex !== -1) {
                return aIndex - bIndex; // Both in recent, sort by recency
            } else if (aIndex !== -1) {
                return -1; // a is recent, b is not
            } else if (bIndex !== -1) {
                return 1; // b is recent, a is not
            } else {
                // Neither is recent, sort alphabetically
                const aTitle = a.name.replace('.md', '');
                const bTitle = b.name.replace('.md', '');
                return aTitle.localeCompare(bTitle);
            }
        });
        
        // Add existing note options
        if (sortedDocs.length > 0) {
            html += sortedDocs.slice(0, 10).map((doc, index) => {
                const displayName = doc.name.replace('.md', '').replace(/_/g, ' ');
                const isRecent = recentlyUsed.includes(doc.name);
                const selected = suggestionIndex === this.wikiSelectedIndex ? 'selected' : '';
                suggestionIndex++;
                return `<div class="wiki-suggestion ${selected}" data-filename="${doc.name}">
                            <span class="suggestion-icon">${isRecent ? '🕐' : '📄'}</span> ${displayName}
                        </div>`;
            }).join('');
        }
        
        // Add create new option if query has content
        if (query && query.trim()) {
            html += `<div class="wiki-suggestion create-new ${suggestionIndex === this.wikiSelectedIndex ? 'selected' : ''}" data-query="${query}">
                        <span class="suggestion-icon">➕</span> Create new note: "${query}"
                     </div>`;
        } else if (!html) {
            html = '<div class="wiki-suggestion no-results">Type to search or create a new note</div>';
        }
        
        dropdown.innerHTML = html;
        
        // Add click handlers
        dropdown.querySelectorAll('.wiki-suggestion').forEach((item, index) => {
            item.addEventListener('click', () => {
                if (item.classList.contains('url-option')) {
                    const url = item.dataset.url;
                    this.insertWikiLink(url);
                } else if (item.dataset.filename) {
                    const filename = item.dataset.filename;
                    const displayName = item.textContent.replace(/^[🕐📄]\s*/, '').trim();
                    this.insertWikiLink(displayName);
                    
                    // Update recently used
                    const recentlyUsed = JSON.parse(localStorage.getItem('recentlyUsedDocs') || '[]');
                    const updatedRecent = [filename, ...recentlyUsed.filter(f => f !== filename)].slice(0, 20);
                    localStorage.setItem('recentlyUsedDocs', JSON.stringify(updatedRecent));
                } else if (item.dataset.query || item.classList.contains('create-new')) {
                    // Create new note with query as name
                    const newNoteName = item.dataset.query || query;
                    this.insertWikiLink(newNoteName);
                    
                    // Optionally create the file
                    this.createNewNote(newNoteName);
                }
            });
        });
    }
    
    updateWikiSelection(items) {
        items.forEach((item, i) => {
            if (i === this.wikiSelectedIndex) {
                item.classList.add('selected');
                item.scrollIntoView({ block: 'nearest' });
            } else {
                item.classList.remove('selected');
            }
        });
    }
    
    insertWikiLink(noteName) {
        const text = this.editor.textContent;
        const startIndex = text.lastIndexOf('[[');
        
        if (startIndex !== -1) {
            const selection = window.getSelection();
            const range = selection.getRangeAt(0);
            
            // Find the ]] that was auto-inserted
            const endIndex = text.indexOf(']]', startIndex);
            
            if (endIndex !== -1) {
                // Replace from [[ to ]] with the wiki link
                const before = text.substring(0, startIndex);
                const after = text.substring(endIndex + 2);
                
                // Clear the editor and rebuild content
                this.editor.textContent = before + after;
                
                // Create the wiki link element
                const link = document.createElement('a');
                link.className = 'wiki-link';
                link.dataset.note = noteName;
                link.textContent = noteName;
                link.href = '#';
                link.addEventListener('click', (e) => {
                    e.preventDefault();
                    this.loadWikiLink(noteName);
                });
                
                // Find insertion point
                const insertNode = this.findTextNodeAtOffset(startIndex);
                if (insertNode) {
                    const textNode = insertNode.node;
                    const offset = insertNode.offset;
                    
                    textNode.splitText(offset);
                    textNode.parentNode.insertBefore(link, textNode.nextSibling);
                    
                    // Move cursor after the link
                    const newRange = document.createRange();
                    newRange.setStartAfter(link);
                    newRange.collapse(true);
                    selection.removeAllRanges();
                    selection.addRange(newRange);
                }
            }
        }
        
        this.closeWikiAutocomplete();
    }
    
    closeWikiAutocomplete() {
        if (this.wikiDropdown) {
            this.wikiDropdown.remove();
            this.wikiDropdown = null;
        }
        this.wikiAutocompleteActive = false;
    }
    
    async createNewNote(noteName) {
        // Sanitize the note name for filename
        const filename = noteName.replace(/[^a-z0-9]/gi, '_').toLowerCase() + '.md';
        
        // Create basic content for the new note
        const content = `# ${noteName}\n\nCreated on ${new Date().toLocaleDateString()}\n\n`;
        
        try {
            // Save the new note
            await fetch('/api/documents', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    filename: filename,
                    content: content,
                    title: noteName
                })
            });
            
            this.showStatus(`Created new note: ${noteName}`, 2000);
        } catch (error) {
            console.error('Error creating new note:', error);
        }
    }
    
    debounceObsidianFormatting() {
        // Clear existing timer
        if (this.formattingTimer) {
            clearTimeout(this.formattingTimer);
        }
        
        // Set new timer to apply formatting after user stops typing
        this.formattingTimer = setTimeout(() => {
            this.applyObsidianFormatting();
        }, 300); // Wait 300ms after user stops typing
    }
    
    applyObsidianFormatting() {
        // Don't format if actively typing or if cursor is in the middle of a word
        if (this.isActivelyTyping) return;
        
        const selection = window.getSelection();
        if (selection.rangeCount === 0) return;
        
        const range = selection.getRangeAt(0);
        
        // Save exact cursor position
        const cursorNode = range.startContainer;
        const cursorOffset = range.startOffset;
        
        // Get plain text and cursor position in plain text
        const plainText = this.editor.textContent;
        const textBeforeCursor = this.getTextBeforeCursor(cursorNode, cursorOffset);
        const plainTextCursorPos = textBeforeCursor.length;
        
        // Apply formatting to HTML
        let html = this.editor.innerHTML;
        const originalHtml = html;
        
        // Convert checkboxes
        html = html.replace(/- \[ \]/g, '<input type="checkbox" class="task-checkbox">');
        html = html.replace(/- \[x\]/gi, '<input type="checkbox" class="task-checkbox" checked>');
        
        // Convert * at start of line to proper bullet points
        // Split content into lines for processing
        const lines = html.split('\n');
        const processedLines = [];
        let inList = false;
        let currentIndent = 0;
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            
            // Check if line starts with * or • (after any HTML tags)
            const bulletMatch = line.match(/^(.*?>)?(\s*)(\*|•)\s+(.*)$/);
            
            if (bulletMatch) {
                const [, prefix = '', indent, bullet, content] = bulletMatch;
                const indentLevel = indent.length;
                
                if (!inList) {
                    processedLines.push(prefix + '<ul>');
                    inList = true;
                    currentIndent = indentLevel;
                }
                
                // Handle nested lists
                if (indentLevel > currentIndent) {
                    processedLines.push('<ul>');
                } else if (indentLevel < currentIndent) {
                    processedLines.push('</ul>');
                }
                currentIndent = indentLevel;
                
                processedLines.push(`<li>${content}</li>`);
            } else {
                // Not a bullet line
                if (inList && line.trim() !== '') {
                    processedLines.push('</ul>');
                    inList = false;
                }
                processedLines.push(line);
            }
        }
        
        // Close any open lists
        if (inList) {
            processedLines.push('</ul>');
        }
        
        html = processedLines.join('\n');
        
        // Style hashtags (but preserve existing ones)
        html = html.replace(/<span class="hashtag">#(\w+)<\/span>/g, '#$1'); // Remove old
        html = html.replace(/#(\w+)/g, '<span class="hashtag">#$1</span>'); // Add new
        
        // Apply markdown formatting
        html = this.applyMarkdownFormatting(html);
        
        // Only update if changed
        if (html === originalHtml) return;
        
        // Update content
        this.editor.innerHTML = html;
        
        // Restore cursor position using plain text position
        this.restoreCursorAtPlainTextPosition(plainTextCursorPos);
    }
    
    getTextBeforeCursor(node, offset) {
        const walker = document.createTreeWalker(
            this.editor,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let text = '';
        let currentNode;
        
        while (currentNode = walker.nextNode()) {
            if (currentNode === node) {
                text += currentNode.textContent.substring(0, offset);
                break;
            } else {
                text += currentNode.textContent;
            }
        }
        
        return text;
    }
    
    restoreCursorAtPlainTextPosition(targetPos) {
        const walker = document.createTreeWalker(
            this.editor,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let currentPos = 0;
        let node;
        
        while (node = walker.nextNode()) {
            const nodeLength = node.textContent.length;
            if (currentPos + nodeLength >= targetPos) {
                const offset = targetPos - currentPos;
                const selection = window.getSelection();
                const range = document.createRange();
                
                try {
                    range.setStart(node, offset);
                    range.collapse(true);
                    selection.removeAllRanges();
                    selection.addRange(range);
                } catch (e) {
                    // Fallback to end of node
                    range.setStart(node, Math.min(offset, node.textContent.length));
                    range.collapse(true);
                    selection.removeAllRanges();
                    selection.addRange(range);
                }
                break;
            }
            currentPos += nodeLength;
        }
    }
    
    applyFormattingToDocument() {
        // Apply formatting to the entire document after loading
        this.applyObsidianFormatting();
    }
    
    applyMarkdownFormatting(html) {
        // Process headings from H6 to H1 (longest to shortest) to avoid conflicts
        // H6: ###### text -> 11pt, italicized, underlined
        html = html.replace(/^(\s*)######\s+(.+)$/gm, '$1<span class="heading-6">$2</span>');
        
        // H5: ##### text -> 11pt, italicized, underlined
        html = html.replace(/^(\s*)#####\s+(.+)$/gm, '$1<span class="heading-5">$2</span>');
        
        // H4: #### text -> 11pt, underlined (not bold)
        html = html.replace(/^(\s*)####\s+(.+)$/gm, '$1<span class="heading-4">$2</span>');
        
        // H3: ### text -> 12.4pt, bold, underlined
        html = html.replace(/^(\s*)###\s+(.+)$/gm, '$1<span class="heading-3">$2</span>');
        
        // H2: ## text -> 14pt, bold, underlined  
        html = html.replace(/^(\s*)##\s+(.+)$/gm, '$1<span class="heading-2">$2</span>');
        
        // H1: # text -> 16pt, bold, underlined
        html = html.replace(/^(\s*)#\s+(.+)$/gm, '$1<span class="heading-1">$2</span>');
        
        // Bold: **text** or __text__
        html = html.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/__([^_]+)__/g, '<strong>$1</strong>');
        
        // Italic: *text* or _text_ (simplified approach)
        // Handle single asterisks for italics (not already in strong tags)
        html = html.replace(/\*([^\*\n<>]+)\*/g, '<em>$1</em>');
        // Handle single underscores for italics (not already in strong tags)
        html = html.replace(/_([^_\n<>]+)_/g, '<em>$1</em>');
        
        // Strikethrough: ~~text~~
        html = html.replace(/~~([^~]+)~~/g, '<del>$1</del>');
        
        // Code: `text`
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        // Block quotes: > text
        html = html.replace(/^(\s*)>\s+(.+)$/gm, '$1<blockquote>$2</blockquote>');
        
        // Checkboxes: - [ ] and - [x]
        html = html.replace(/^(\s*)-\s+\[\s\]\s+(.*)$/gm, '$1<label class="checkbox-item"><input type="checkbox" disabled> <span>$2</span></label>');
        html = html.replace(/^(\s*)-\s+\[x\]\s+(.*)$/gm, '$1<label class="checkbox-item"><input type="checkbox" checked disabled> <span>$2</span></label>');
        
        return html;
    }
    
    showStatus(message, duration = 0) {
        this.statusBar.textContent = message;
        this.statusBar.classList.add('visible');
        
        if (duration > 0) {
            setTimeout(() => this.hideStatus(), duration);
        }
    }
    
    hideStatus() {
        this.statusBar.classList.remove('visible');
    }
    
    handleWordHighlight(e) {
        // Clear any existing highlighting
        this.clearWordHighlighting();
        
        // Get the word under the cursor
        const selection = window.getSelection();
        const range = document.createRange();
        
        // Find the word boundaries
        let textNode = e.target;
        let offset = 0;
        
        // If clicked on an element, find the nearest text node
        if (textNode.nodeType !== Node.TEXT_NODE) {
            const walker = document.createTreeWalker(
                textNode,
                NodeFilter.SHOW_TEXT,
                null,
                false
            );
            textNode = walker.nextNode();
            if (!textNode) return;
        }
        
        const text = textNode.textContent;
        const clickOffset = this.getClickOffset(e, textNode);
        
        // Find word boundaries
        const wordRegex = /\b\w+\b/g;
        let match;
        let wordStart = -1;
        let wordEnd = -1;
        let selectedWord = '';
        
        while ((match = wordRegex.exec(text)) !== null) {
            if (clickOffset >= match.index && clickOffset <= match.index + match[0].length) {
                wordStart = match.index;
                wordEnd = match.index + match[0].length;
                selectedWord = match[0];
                break;
            }
        }
        
        if (selectedWord && selectedWord.length > 1) {
            this.highlightAllInstances(selectedWord);
            this.currentHighlightedWord = selectedWord;
        }
    }
    
    getClickOffset(e, textNode) {
        // Approximate click position in text node
        const range = document.caretRangeFromPoint(e.clientX, e.clientY);
        if (range && range.startContainer === textNode) {
            return range.startOffset;
        }
        return 0;
    }
    
    highlightAllInstances(word) {
        const content = this.editor.innerHTML;
        const regex = new RegExp(`\\b${this.escapeRegex(word)}\\b`, 'gi');
        
        // Replace all instances with highlighted version
        const highlightedContent = content.replace(regex, (match) => {
            return `<span class="word-highlight">${match}</span>`;
        });
        
        // Save cursor position
        const selection = window.getSelection();
        const bookmark = this.createBookmark(selection);
        
        this.editor.innerHTML = highlightedContent;
        
        // Restore cursor position
        this.restoreBookmark(bookmark);
    }
    
    escapeRegex(string) {
        return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
    
    createBookmark(selection) {
        if (selection.rangeCount === 0) return null;
        
        const range = selection.getRangeAt(0);
        return {
            startContainer: range.startContainer,
            startOffset: range.startOffset,
            endContainer: range.endContainer,
            endOffset: range.endOffset
        };
    }
    
    restoreBookmark(bookmark) {
        if (!bookmark) return;
        
        try {
            const selection = window.getSelection();
            const range = document.createRange();
            range.setStart(bookmark.startContainer, bookmark.startOffset);
            range.setEnd(bookmark.endContainer, bookmark.endOffset);
            selection.removeAllRanges();
            selection.addRange(range);
        } catch (e) {
            // Ignore errors if nodes no longer exist
        }
    }
    
    clearWordHighlighting() {
        const highlightedElements = this.editor.querySelectorAll('.word-highlight');
        highlightedElements.forEach(element => {
            const parent = element.parentNode;
            parent.replaceChild(document.createTextNode(element.textContent), element);
            parent.normalize();
        });
        this.currentHighlightedWord = null;
    }
    
    async initializeEntitySystem() {
        // Wait for modules to load
        let attempts = 0;
        while ((!window.EntityIndexer || !window.EntityDetailPanel || !window.FactExtractor) && attempts < 50) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        
        if (window.EntityIndexer && window.EntityDetailPanel && window.FactExtractor) {
            try {
                // Initialize entity indexer if not already initialized
                if (!this.entityIndexer) {
                    this.entityIndexer = new window.EntityIndexer(this);
                    
                    // Trigger initial indexing of current content
                    if (this.editor.textContent) {
                        await this.entityIndexer.performHeavyPass(this.editor.textContent);
                    }
                }
                
                // Initialize entity detail panel with integration if not already initialized
                if (!this.entityDetailPanel && window.integrateEntityDetailPanel) {
                    this.entityDetailPanel = window.integrateEntityDetailPanel(this, this.entityIndexer);
                }
                
                // Initialize fact extractor if not already initialized
                if (!this.factExtractor) {
                    this.factExtractor = new window.FactExtractor();
                }
                
                // Override the word highlight to use entity detection instead
                this.setupEntityDoubleClick();
                
                // Set up periodic indexing
                this.setupEntityIndexingListeners();
                
                console.log('Entity system initialized successfully');
            } catch (error) {
                console.error('Error initializing entity system:', error);
            }
        } else {
            console.warn('Entity system modules failed to load');
        }
    }
    
    async initializeLeftRail() {
        // Wait for LeftRail module to load
        let attempts = 0;
        while (!window.LeftRail && attempts < 50) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        
        if (window.LeftRail) {
            try {
                this.leftRail = new window.LeftRail(this);
                
                // Connect entity indexer to left rail
                if (this.entityIndexer && this.leftRail) {
                    // Update left rail when entity index changes
                    document.addEventListener('entityIndexUpdated', (e) => {
                        if (this.leftRail) {
                            this.leftRail.updateEntityTree();
                        }
                    });
                    
                    // Connect left rail entity selection to detail panel
                    document.addEventListener('entitySelected', (e) => {
                        if (this.entityDetailPanel) {
                            this.entityDetailPanel.showEntity(e.detail.entityId);
                        }
                    });
                }
                
                console.log('LeftRail initialized successfully');
            } catch (error) {
                console.error('Error initializing LeftRail:', error);
            }
        } else {
            console.warn('LeftRail module failed to load');
        }
    }
    
    // BulkOperations removed - not requested
    
    async initializeSmartProcessor() {
        // Wait for SmartCommandProcessor to load
        let attempts = 0;
        while (!window.SmartCommandProcessor && attempts < 50) {
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        
        if (window.SmartCommandProcessor) {
            try {
                this.smartCommandProcessor = new window.SmartCommandProcessor(this);
                console.log('SmartCommandProcessor initialized successfully');
            } catch (error) {
                console.error('Error initializing SmartCommandProcessor:', error);
            }
        } else {
            console.warn('SmartCommandProcessor module failed to load');
        }
    }
    
    setupEntityDoubleClick() {
        // Replace the existing double-click handler to prioritize entity detection
        this.editor.removeEventListener('dblclick', this.handleWordHighlight.bind(this));
        
        this.editor.addEventListener('dblclick', (e) => {
            if (e.target.classList.contains('footnote-number')) {
                this.showFootnotePopup(e.target, e);
                return;
            }
            
            // Try entity detection first
            if (this.entityDetailPanel && this.tryShowEntityPanel(e)) {
                return;
            }
            
            // Fallback to word highlighting
            this.handleWordHighlight(e);
        });
    }
    
    setupEntityIndexingListeners() {
        if (!this.entityIndexer) return;
        
        // Listen for entity index updates
        document.addEventListener('entityIndexUpdated', (e) => {
            console.log(`Entity index updated: ${e.detail.entityCount} entities found`);
            
            // Update entity highlights if visible
            if (this.entityHighlightsVisible) {
                this.updateEntityHighlights();
            }
            
            // Update entity index panel
            this.updateEntityIndexPanel();
        });
        
        // Listen for document changes to trigger re-indexing
        let indexTimeout;
        this.editor.addEventListener('input', () => {
            // Clear existing timeout
            clearTimeout(indexTimeout);
            
            // Schedule light pass after 2 seconds of no typing
            indexTimeout = setTimeout(() => {
                if (this.entityIndexer && this.editor.value) {
                    this.entityIndexer.scheduleLightPass();
                }
            }, 2000);
        });
        
        // Heavy pass on save
        document.addEventListener('documentSaved', () => {
            if (this.entityIndexer && this.editor.value) {
                this.entityIndexer.scheduleHeavyPass();
            }
        });
    }
    
    setupEntityIndexPanel() {
        const panel = document.getElementById('entity-index-panel');
        const closeBtn = document.getElementById('close-entity-index');
        const searchInput = document.getElementById('entity-index-search');
        const refreshBtn = document.getElementById('refresh-entities');
        
        // Close button
        closeBtn.addEventListener('click', () => {
            this.hideEntityIndex();
        });
        
        // Search functionality
        searchInput.addEventListener('input', (e) => {
            this.filterEntityIndex(e.target.value);
        });
        
        // Refresh button
        refreshBtn.addEventListener('click', () => {
            if (this.entityIndexer && this.editor.value) {
                this.entityIndexer.performHeavyPass(this.editor.value);
            }
        });
        
        // Show panel when entities menu item is clicked
        // (Already handled in setupMenuHandlers)
    }
    
    showEntityIndex() {
        // Use LeftRail instead of basic panel if available
        if (this.leftRail) {
            this.leftRail.show();
            this.leftRail.switchTab('entities');
            return;
        }
        
        // Fallback to basic panel
        const panel = document.getElementById('entity-index-panel');
        const container = document.getElementById('editor-container');
        
        panel.classList.add('visible');
        container.classList.add('with-entity-index');
        
        // Update the entity list
        this.updateEntityIndexPanel();
    }
    
    hideEntityIndex() {
        const panel = document.getElementById('entity-index-panel');
        const container = document.getElementById('editor-container');
        
        panel.classList.remove('visible');
        container.classList.remove('with-entity-index');
    }
    
    updateEntityIndexPanel() {
        if (!this.entityIndexer || !this.entityIndexer.entityGraph) return;
        
        const listContainer = document.getElementById('entity-index-list');
        listContainer.innerHTML = '';
        
        // Group entities by type
        const entityTree = this.entityIndexer.getEntityTree();
        
        // Define type order and icons
        const typeConfig = {
            'person': { icon: '👤', label: 'People' },
            'organization': { icon: '🏢', label: 'Organizations' },
            'place': { icon: '📍', label: 'Places' },
            'date': { icon: '📅', label: 'Dates' },
            'url': { icon: '🔗', label: 'Links' },
            'email': { icon: '✉️', label: 'Emails' },
            'phone': { icon: '📞', label: 'Phone Numbers' }
        };
        
        // Create groups
        for (const [type, config] of Object.entries(typeConfig)) {
            if (!entityTree[type] || entityTree[type].count === 0) continue;
            
            const group = document.createElement('div');
            group.className = 'entity-type-group';
            
            const header = document.createElement('div');
            header.className = 'entity-type-header';
            header.textContent = `${config.label} (${entityTree[type].count})`;
            group.appendChild(header);
            
            // Add entities in this group
            entityTree[type].entities.forEach(entity => {
                const item = this.createEntityIndexItem(entity, config.icon);
                group.appendChild(item);
            });
            
            listContainer.appendChild(group);
        }
    }
    
    createEntityIndexItem(entity, icon) {
        const item = document.createElement('div');
        item.className = 'entity-index-item';
        item.dataset.entityId = entity.id;
        
        const iconSpan = document.createElement('span');
        iconSpan.className = 'entity-icon';
        iconSpan.textContent = icon;
        
        const nameSpan = document.createElement('span');
        nameSpan.className = 'entity-index-name';
        nameSpan.textContent = entity.text;
        
        const mentionBadge = document.createElement('span');
        mentionBadge.className = 'entity-mention-badge';
        mentionBadge.textContent = entity.mentions || '1';
        
        const profileBtn = document.createElement('button');
        profileBtn.className = 'entity-profile-btn';
        profileBtn.innerHTML = '👁';
        profileBtn.title = 'View entity profile';
        
        item.appendChild(iconSpan);
        item.appendChild(nameSpan);
        item.appendChild(mentionBadge);
        item.appendChild(profileBtn);
        
        // Click on item to navigate through mentions
        item.addEventListener('click', (e) => {
            if (e.target === profileBtn) return;
            this.navigateToEntityMention(entity);
        });
        
        // Double-click or profile button to open profile
        item.addEventListener('dblclick', () => {
            this.openEntityProfile(entity);
        });
        
        profileBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.openEntityProfile(entity);
        });
        
        return item;
    }
    
    navigateToEntityMention(entity) {
        const mentions = this.entityIndexer.getMentions(entity.id);
        if (!mentions || mentions.length === 0) return;
        
        // Get current index for this entity
        let currentIndex = this.entityMentionIndex.get(entity.id) || 0;
        
        // Get the mention to navigate to
        const mention = mentions[currentIndex];
        
        // Find the position in the editor
        const content = this.editor.textContent;
        const regex = new RegExp(`\\b${this.escapeRegex(entity.text)}\\b`, 'gi');
        
        let match;
        let matchIndex = 0;
        while ((match = regex.exec(content)) !== null) {
            if (matchIndex === currentIndex) {
                // Scroll to this position
                this.scrollToTextPosition(match.index);
                
                // Highlight the mention temporarily
                this.highlightTextAtPosition(match.index, entity.text.length);
                
                // Update active state in index
                document.querySelectorAll('.entity-index-item').forEach(item => {
                    item.classList.remove('active', 'current-mention');
                });
                const currentItem = document.querySelector(`[data-entity-id="${entity.id}"]`);
                if (currentItem) {
                    currentItem.classList.add('active', 'current-mention');
                }
                
                break;
            }
            matchIndex++;
        }
        
        // Update index for next click (cycle through mentions)
        currentIndex = (currentIndex + 1) % mentions.length;
        this.entityMentionIndex.set(entity.id, currentIndex);
    }
    
    scrollToTextPosition(position) {
        // Create a temporary marker to scroll to
        const range = document.createRange();
        const textNodes = this.getTextNodes(this.editor);
        
        let currentPos = 0;
        for (const node of textNodes) {
            const nodeLength = node.textContent.length;
            if (currentPos + nodeLength >= position) {
                range.setStart(node, position - currentPos);
                range.setEnd(node, position - currentPos);
                
                const marker = document.createElement('span');
                marker.id = 'scroll-marker';
                range.insertNode(marker);
                
                marker.scrollIntoView({ behavior: 'smooth', block: 'center' });
                
                // Remove marker after scrolling
                setTimeout(() => marker.remove(), 100);
                break;
            }
            currentPos += nodeLength;
        }
    }
    
    highlightTextAtPosition(position, length) {
        // Temporarily highlight the text
        const range = document.createRange();
        const textNodes = this.getTextNodes(this.editor);
        
        let currentPos = 0;
        for (const node of textNodes) {
            const nodeLength = node.textContent.length;
            if (currentPos + nodeLength >= position) {
                range.setStart(node, position - currentPos);
                
                // Find end position
                let endPos = position + length;
                let endNode = node;
                let endOffset = position - currentPos + length;
                
                if (endOffset > nodeLength) {
                    // Span multiple nodes
                    for (const nextNode of textNodes) {
                        if (currentPos + nextNode.textContent.length >= endPos) {
                            endNode = nextNode;
                            endOffset = endPos - currentPos;
                            break;
                        }
                    }
                }
                
                range.setEnd(endNode, endOffset);
                
                // Apply temporary highlight
                const selection = window.getSelection();
                selection.removeAllRanges();
                selection.addRange(range);
                
                // Remove selection after a moment
                setTimeout(() => {
                    selection.removeAllRanges();
                }, 2000);
                
                break;
            }
            currentPos += nodeLength;
        }
    }
    
    getTextNodes(element) {
        const textNodes = [];
        const walk = document.createTreeWalker(
            element,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let node;
        while (node = walk.nextNode()) {
            textNodes.push(node);
        }
        
        return textNodes;
    }
    
    filterEntityIndex(searchTerm) {
        const items = document.querySelectorAll('.entity-index-item');
        const groups = document.querySelectorAll('.entity-type-group');
        const lowercaseSearch = searchTerm.toLowerCase();
        
        groups.forEach(group => {
            let visibleCount = 0;
            const groupItems = group.querySelectorAll('.entity-index-item');
            
            groupItems.forEach(item => {
                const name = item.querySelector('.entity-index-name').textContent.toLowerCase();
                if (name.includes(lowercaseSearch)) {
                    item.style.display = 'flex';
                    visibleCount++;
                } else {
                    item.style.display = 'none';
                }
            });
            
            // Hide group if no visible items
            group.style.display = visibleCount > 0 ? 'block' : 'none';
        });
    }
    
    async processEntityCommand(command) {
        const lowerCommand = command.toLowerCase().trim();
        
        // Show processing indicator
        this.addChatMessage('assistant', '🔍 Processing entity command...');
        
        try {
            // Extract entities command
            if (lowerCommand.includes('extract') || lowerCommand.includes('find all')) {
                await this.extractEntitiesWithAI();
                this.addChatMessage('assistant', '✅ Entity extraction complete. Opening entity browser...');
                setTimeout(() => this.showEntityBrowser(), 500);
            }
            // Show specific entity type
            else if (lowerCommand.includes('show all') || lowerCommand.includes('list all')) {
                const types = ['person', 'people', 'organization', 'place', 'date'];
                const matchedType = types.find(t => lowerCommand.includes(t));
                
                if (matchedType) {
                    const entities = this.entityIndexer.getEntitiesByType(matchedType === 'people' ? 'person' : matchedType);
                    if (entities.length > 0) {
                        this.highlightEntitiesByType(matchedType);
                        this.addChatMessage('assistant', `✅ Found ${entities.length} ${matchedType} entities. They are now highlighted.`);
                    } else {
                        this.addChatMessage('assistant', `No ${matchedType} entities found. Try running "extract entities" first.`);
                    }
                } else {
                    await this.showEntityBrowser();
                    this.addChatMessage('assistant', '✅ Opened entity browser with all entities.');
                }
            }
            // Highlight specific entity
            else if (lowerCommand.includes('highlight')) {
                const entityMatch = command.match(/highlight\s+["']?([^"']+)["']?/i);
                if (entityMatch) {
                    const entityName = entityMatch[1].trim();
                    this.highlightSpecificEntity(entityName);
                    this.addChatMessage('assistant', `✅ Highlighted all mentions of "${entityName}"`);
                } else {
                    this.addChatMessage('assistant', 'Please specify which entity to highlight. Example: "highlight John Smith"');
                }
            }
            // Facts about entity
            else if (lowerCommand.includes('facts about')) {
                const entityMatch = command.match(/facts about\s+["']?([^"']+)["']?/i);
                if (entityMatch) {
                    const entityName = entityMatch[1].trim();
                    await this.showEntityFacts(entityName);
                } else {
                    this.addChatMessage('assistant', 'Please specify which entity. Example: "facts about John Smith"');
                }
            }
            // Rename entity
            else if (lowerCommand.includes('rename')) {
                const renameMatch = command.match(/rename\s+["']?([^"']+)["']?\s+to\s+["']?([^"']+)["']?/i);
                if (renameMatch) {
                    const oldName = renameMatch[1].trim();
                    const newName = renameMatch[2].trim();
                    this.renameEntity(oldName, newName);
                    this.addChatMessage('assistant', `✅ Renamed "${oldName}" to "${newName}"`);
                } else {
                    this.addChatMessage('assistant', 'Please use format: "rename [old name] to [new name]"');
                }
            }
            // General entity help
            else {
                this.addChatMessage('assistant', `
Entity commands available:
• "extract entities" - Find all entities in document
• "show all people/organizations/places" - Show specific entity types
• "highlight [entity name]" - Highlight specific entity
• "facts about [entity name]" - Show all facts about an entity
• "rename [old] to [new]" - Rename all mentions
                `.trim());
            }
        } catch (error) {
            console.error('Entity command error:', error);
            this.addChatMessage('error', `Error processing entity command: ${error.message}`);
        }
    }
    
    async extractEntitiesWithAI() {
        if (!this.entityIndexer) {
            throw new Error('Entity system not initialized');
        }
        
        const content = this.editor.value || this.editor.textContent;
        if (!content) {
            throw new Error('No content to analyze');
        }
        
        // Trigger heavy pass extraction
        await this.entityIndexer.performHeavyPass(content);
    }
    
    highlightEntitiesByType(type) {
        // Clear existing highlights
        this.clearWordHighlights();
        
        const entities = this.entityIndexer.getEntitiesByType(type === 'people' ? 'person' : type);
        entities.forEach(entity => {
            this.highlightEntityInEditor(entity.text);
        });
        
        this.entityHighlightsVisible = true;
    }
    
    highlightSpecificEntity(entityName) {
        // Clear existing highlights
        this.clearWordHighlights();
        
        // Search for the entity
        const results = this.entityIndexer.searchEntities(entityName);
        if (results.length > 0) {
            this.highlightEntityInEditor(results[0].text);
            this.entityHighlightsVisible = true;
        }
    }
    
    highlightEntityInEditor(entityText) {
        const content = this.editor.innerHTML;
        const regex = new RegExp(`\\b${this.escapeRegex(entityText)}\\b`, 'gi');
        
        // Create highlighted version
        const highlighted = content.replace(regex, (match) => {
            return `<span class="entity-highlight">${match}</span>`;
        });
        
        // Update editor
        this.editor.innerHTML = highlighted;
    }
    
    async showEntityFacts(entityName) {
        const results = this.entityIndexer.searchEntities(entityName);
        
        if (results.length === 0) {
            this.addChatMessage('assistant', `No entity found matching "${entityName}"`);
            return;
        }
        
        const entity = results[0];
        const mentions = this.entityIndexer.getMentions(entity.id);
        
        // Use fact extractor if available
        let facts = [];
        if (this.factExtractor) {
            const content = this.editor.value || this.editor.textContent;
            facts = await this.factExtractor.extractFactsAboutEntity(entityName, content);
        }
        
        let message = `📋 Facts about "${entity.text}" (${entity.type}):\n\n`;
        message += `• Mentions: ${mentions.length}\n`;
        message += `• First seen: ${new Date(entity.firstSeen).toLocaleDateString()}\n`;
        
        if (facts.length > 0) {
            message += `\nExtracted facts:\n`;
            facts.forEach((fact, i) => {
                message += `${i + 1}. ${fact.text}\n`;
            });
        }
        
        this.addChatMessage('assistant', message);
    }
    
    openEntityProfile(entity) {
        // Enter entity profile mode
        this.entityProfileMode = true;
        this.currentEntityProfile = entity;
        
        // Show profile view
        const profileView = document.getElementById('entity-profile-view');
        profileView.classList.add('visible');
        
        // Update header
        document.querySelector('.profile-entity-name').textContent = entity.text;
        document.querySelector('.profile-entity-type').textContent = entity.type;
        
        // Get mentions count
        const mentions = this.entityIndexer.getMentions(entity.id) || [];
        document.querySelector('.mention-count').textContent = mentions.length;
        
        // Extract and display snippets
        this.displayEntitySnippets(entity);
        
        // Add back button handler
        const backBtn = document.getElementById('back-to-editor');
        backBtn.onclick = () => this.closeEntityProfile();
        
        // Set chat to entity mode
        const chatbox = document.getElementById('command-chatbox');
        chatbox.classList.add('entity-mode');
        
        // Store original editor content for reference
        this.originalEditorContent = this.editor.innerHTML;
    }
    
    closeEntityProfile() {
        // Exit entity profile mode
        this.entityProfileMode = false;
        this.currentEntityProfile = null;
        
        // Hide profile view
        const profileView = document.getElementById('entity-profile-view');
        profileView.classList.remove('visible');
        
        // Remove entity mode from chat
        const chatbox = document.getElementById('command-chatbox');
        chatbox.classList.remove('entity-mode');
        
        // Sync any changes back to main editor
        this.syncSnippetsToEditor();
    }
    
    async displayEntitySnippets(entity) {
        const container = document.getElementById('entity-snippets-container');
        container.innerHTML = '';
        
        // Get all mentions
        const mentions = this.entityIndexer.getMentions(entity.id) || [];
        const content = this.editor.textContent;
        
        // Find each mention and extract context
        const regex = new RegExp(`\\b${this.escapeRegex(entity.text)}\\b`, 'gi');
        let match;
        let snippets = [];
        
        while ((match = regex.exec(content)) !== null) {
            const snippet = this.extractSnippetContext(content, match.index, entity.text.length);
            snippet.entityText = entity.text;
            snippet.position = match.index;
            snippets.push(snippet);
        }
        
        // Create snippet elements
        snippets.forEach((snippet, index) => {
            const snippetEl = this.createSnippetElement(snippet, index);
            container.appendChild(snippetEl);
        });
        
        // Store snippets for AI context
        this.currentEntitySnippets = snippets;
    }
    
    extractSnippetContext(fullText, position, entityLength) {
        // Extract 1-2 paragraphs around the entity mention
        const lines = fullText.split('\n');
        let currentPos = 0;
        let targetLineIndex = -1;
        let lineStartPos = 0;
        
        // Find which line contains the entity
        for (let i = 0; i < lines.length; i++) {
            const lineLength = lines[i].length + 1; // +1 for newline
            if (currentPos + lineLength > position) {
                targetLineIndex = i;
                lineStartPos = currentPos;
                break;
            }
            currentPos += lineLength;
        }
        
        if (targetLineIndex === -1) return { text: '', start: 0, end: 0 };
        
        // Get surrounding context (current paragraph + neighboring ones)
        let startLine = targetLineIndex;
        let endLine = targetLineIndex;
        
        // Find paragraph boundaries
        // Go back to find paragraph start
        while (startLine > 0 && lines[startLine - 1].trim() !== '') {
            startLine--;
        }
        
        // Go forward to find paragraph end
        while (endLine < lines.length - 1 && lines[endLine + 1].trim() !== '') {
            endLine++;
        }
        
        // Include one paragraph before and after if they exist
        if (startLine > 0 && lines[startLine - 1].trim() === '') {
            startLine = Math.max(0, startLine - 2);
            while (startLine > 0 && lines[startLine - 1].trim() !== '') {
                startLine--;
            }
        }
        
        if (endLine < lines.length - 1 && lines[endLine + 1].trim() === '') {
            endLine = Math.min(lines.length - 1, endLine + 2);
            while (endLine < lines.length - 1 && lines[endLine + 1].trim() !== '') {
                endLine++;
            }
        }
        
        // Calculate positions
        let snippetStart = 0;
        for (let i = 0; i < startLine; i++) {
            snippetStart += lines[i].length + 1;
        }
        
        let snippetEnd = snippetStart;
        for (let i = startLine; i <= endLine; i++) {
            snippetEnd += lines[i].length + 1;
        }
        
        const snippetText = lines.slice(startLine, endLine + 1).join('\n');
        
        return {
            text: snippetText,
            start: snippetStart,
            end: snippetEnd,
            entityOffset: position - snippetStart,
            lineNumber: targetLineIndex + 1
        };
    }
    
    createSnippetElement(snippet, index) {
        const div = document.createElement('div');
        div.className = 'entity-snippet';
        div.dataset.snippetIndex = index;
        div.dataset.position = snippet.position;
        
        // Header
        const header = document.createElement('div');
        header.className = 'snippet-header';
        
        const location = document.createElement('span');
        location.className = 'snippet-location';
        location.textContent = `Line ${snippet.lineNumber}`;
        
        const controls = document.createElement('div');
        controls.className = 'snippet-controls';
        
        const expandUpBtn = document.createElement('button');
        expandUpBtn.className = 'snippet-control-btn';
        expandUpBtn.textContent = '↑';
        expandUpBtn.title = 'Expand context up';
        expandUpBtn.onclick = () => this.expandSnippetContext(index, 'up');
        
        const expandDownBtn = document.createElement('button');
        expandDownBtn.className = 'snippet-control-btn';
        expandDownBtn.textContent = '↓';
        expandDownBtn.title = 'Expand context down';
        expandDownBtn.onclick = () => this.expandSnippetContext(index, 'down');
        
        controls.appendChild(expandUpBtn);
        controls.appendChild(expandDownBtn);
        
        header.appendChild(location);
        header.appendChild(controls);
        
        // Editor
        const editor = document.createElement('div');
        editor.className = 'snippet-editor';
        editor.contentEditable = true;
        editor.dataset.snippetIndex = index;
        
        // Highlight entity mentions
        const highlightedText = snippet.text.replace(
            new RegExp(`\\b${this.escapeRegex(snippet.entityText)}\\b`, 'gi'),
            (match) => `<span class="entity-mention">${match}</span>`
        );
        editor.innerHTML = highlightedText;
        
        // Track changes
        editor.addEventListener('input', () => {
            this.trackSnippetChange(index, editor.textContent);
        });
        
        // Navigation
        const nav = document.createElement('div');
        nav.className = 'snippet-navigation';
        
        const expandBtn = document.createElement('button');
        expandBtn.className = 'expand-context-btn';
        expandBtn.textContent = 'Expand context';
        expandBtn.onclick = () => this.expandFullContext(index);
        
        const goToBtn = document.createElement('button');
        goToBtn.className = 'go-to-text-btn';
        goToBtn.innerHTML = 'Go to text →';
        goToBtn.onclick = () => this.goToTextFromSnippet(snippet.position);
        
        nav.appendChild(expandBtn);
        nav.appendChild(goToBtn);
        
        div.appendChild(header);
        div.appendChild(editor);
        div.appendChild(nav);
        
        return div;
    }
    
    trackSnippetChange(index, newText) {
        if (!this.currentEntitySnippets[index]) return;
        
        this.currentEntitySnippets[index].modifiedText = newText;
        this.currentEntitySnippets[index].isModified = true;
    }
    
    expandSnippetContext(index, direction) {
        // Expand the snippet context by one paragraph
        const snippet = this.currentEntitySnippets[index];
        if (!snippet) return;
        
        const content = this.editor.textContent;
        const lines = content.split('\n');
        
        // Re-calculate with expanded bounds
        // (Implementation would expand the context calculation)
        this.displayEntitySnippets(this.currentEntityProfile);
    }
    
    goToTextFromSnippet(position) {
        // Close profile and navigate to position
        this.closeEntityProfile();
        
        // Scroll to position
        setTimeout(() => {
            this.scrollToTextPosition(position);
            this.highlightTextAtPosition(position, this.currentEntityProfile.text.length);
        }, 300);
    }
    
    syncSnippetsToEditor() {
        if (!this.currentEntitySnippets) return;
        
        // Apply modified snippets back to the main editor
        let content = this.editor.textContent;
        
        // Sort snippets by position (reverse order to maintain positions)
        const modifiedSnippets = this.currentEntitySnippets
            .filter(s => s.isModified)
            .sort((a, b) => b.start - a.start);
        
        // Apply changes
        modifiedSnippets.forEach(snippet => {
            const before = content.substring(0, snippet.start);
            const after = content.substring(snippet.end);
            content = before + snippet.modifiedText + after;
        });
        
        // Update editor
        this.editor.textContent = content;
        
        // Clear snippets
        this.currentEntitySnippets = null;
    }
    
    applyEntitySnippetEdit(data) {
        // Apply edit to specific snippet or all snippets
        if (!this.currentEntitySnippets) return;
        
        if (data.snippetIndex !== undefined) {
            // Edit specific snippet
            const snippet = this.currentEntitySnippets[data.snippetIndex];
            if (snippet) {
                const editor = document.querySelector(`[data-snippet-index="${data.snippetIndex}"]`);
                if (editor) {
                    // Apply the edit
                    let newText = snippet.modifiedText || snippet.text;
                    
                    if (data.operation === 'replace') {
                        newText = newText.replace(data.oldText, data.newText);
                    } else if (data.operation === 'insert') {
                        newText = data.text;
                    }
                    
                    // Update editor display
                    const highlightedText = newText.replace(
                        new RegExp(`\\b${this.escapeRegex(this.currentEntityProfile.text)}\\b`, 'gi'),
                        (match) => `<span class="entity-mention">${match}</span>`
                    );
                    editor.innerHTML = highlightedText;
                    
                    // Track change
                    this.trackSnippetChange(data.snippetIndex, newText);
                }
            }
        } else if (data.allSnippets) {
            // Apply to all snippets
            this.currentEntitySnippets.forEach((snippet, index) => {
                const editor = document.querySelector(`[data-snippet-index="${index}"]`);
                if (editor) {
                    let newText = snippet.modifiedText || snippet.text;
                    
                    if (data.operation === 'replace') {
                        newText = newText.replace(new RegExp(data.oldText, 'g'), data.newText);
                    }
                    
                    // Update editor display
                    const highlightedText = newText.replace(
                        new RegExp(`\\b${this.escapeRegex(this.currentEntityProfile.text)}\\b`, 'gi'),
                        (match) => `<span class="entity-mention">${match}</span>`
                    );
                    editor.innerHTML = highlightedText;
                    
                    // Track change
                    this.trackSnippetChange(index, newText);
                }
            });
        }
        
        // Show status
        this.directEditsApplied++;
        this.showStatus(`Applied edit to ${data.allSnippets ? 'all' : 'snippet'} (${this.directEditsApplied} total)`, 2000);
    }
    
    tryShowEntityPanel(e) {
        // Get the word under cursor
        const word = this.getWordAtPosition(e);
        if (!word || word.length < 2) return false;
        
        // Check if this word is a known entity
        if (this.entityIndexer && this.entityIndexer.entityGraph) {
            // Search through all entities
            const results = this.entityIndexer.searchEntities(word);
            
            if (results && results.length > 0) {
                // Get the most relevant entity (first result)
                const entity = results[0];
                
                // Show entity detail panel
                if (this.entityDetailPanel && typeof this.entityDetailPanel.show === 'function') {
                    this.entityDetailPanel.show(entity.id, e);
                    return true;
                }
            }
        }
        
        return false;
    }
    
    getWordAtPosition(e) {
        const selection = window.getSelection();
        const range = document.caretRangeFromPoint(e.clientX, e.clientY);
        
        if (!range) return '';
        
        // Expand range to word boundaries
        const textNode = range.startContainer;
        if (textNode.nodeType !== Node.TEXT_NODE) return '';
        
        const text = textNode.textContent;
        const offset = range.startOffset;
        
        // Find word boundaries
        let start = offset;
        let end = offset;
        
        // Move start backward to word boundary
        while (start > 0 && /\w/.test(text[start - 1])) {
            start--;
        }
        
        // Move end forward to word boundary
        while (end < text.length && /\w/.test(text[end])) {
            end++;
        }
        
        return text.substring(start, end);
    }
    
    async showEntityBrowser() {
        const browser = document.getElementById('entity-browser');
        if (!browser) {
            console.error('Entity browser element not found!');
            return;
        }
        
        // Initialize advanced entity systems if available
        if (!this.entityIndexer && window.EntityIndexer) {
            this.entityIndexer = new window.EntityIndexer(this);
            this.entityDetailPanel = new window.EntityDetailPanel(this.entityIndexer, this);
        }
        
        const closeButton = browser.querySelector('.close-button');
        const entityList = browser.querySelector('.entity-list');
        const entitySearch = browser.querySelector('.entity-search');
        const executeButton = browser.querySelector('.execute-entity-command');
        const commandInput = browser.querySelector('.entity-command-input');
        
        // Remove old listeners to prevent duplicates
        const newCloseButton = closeButton.cloneNode(true);
        closeButton.parentNode.replaceChild(newCloseButton, closeButton);
        
        const newExecuteButton = executeButton.cloneNode(true);
        executeButton.parentNode.replaceChild(newExecuteButton, executeButton);
        
        // Setup close handler
        newCloseButton.addEventListener('click', () => {
            browser.classList.remove('visible');
        });
        
        browser.addEventListener('click', (e) => {
            if (e.target === browser) {
                browser.classList.remove('visible');
            }
        });
        
        // Clear search
        entitySearch.value = '';
        
        // Extract and display entities
        await this.extractAndDisplayEntities();
        
        // Setup search
        entitySearch.addEventListener('input', (e) => {
            this.filterEntityList(e.target.value);
        });
        
        // Setup entity command execution
        newExecuteButton.addEventListener('click', () => {
            this.executeEntityCommand(commandInput.value);
        });
        
        // Show the browser
        browser.classList.add('visible');
        
        // Focus on search
        setTimeout(() => entitySearch.focus(), 100);
    }
    
    async extractAndDisplayEntities() {
        const content = this.editor.textContent;
        const entities = await this.extractEntitiesFromText(content);
        
        const entityList = document.querySelector('.entity-list');
        entityList.innerHTML = '';
        
        if (!entities || entities.length === 0) {
            entityList.innerHTML = '<div style="padding: 20px; text-align: center; color: #999;">No entities found</div>';
            return;
        }
        
        entities.forEach(entity => {
            const entityItem = document.createElement('div');
            entityItem.className = 'entity-item';
            entityItem.dataset.entityName = entity.name;
            entityItem.dataset.entityType = entity.type;
            
            entityItem.innerHTML = `
                <div class="entity-name">${entity.name}</div>
                <div class="entity-type">${entity.type}</div>
                <span class="entity-mentions-count">${entity.mentions.length}</span>
            `;
            
            entityItem.addEventListener('click', () => {
                this.selectEntity(entity);
            });
            
            entityList.appendChild(entityItem);
        });
    }
    
    async extractEntitiesFromText(text) {
        try {
            const response = await fetch('/api/command', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    command: 'EXTRACT_ENTITIES',
                    context: {
                        content: text,
                        extractionMode: true
                    }
                })
            });

            if (!response.ok) {
                throw new Error('Entity extraction API error');
            }

            // Handle streaming response for entity extraction
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let entityData = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.type === 'entities') {
                                entityData = data.data;
                            } else if (data.type === 'message') {
                                // Fallback for old format
                                entityData += data.content;
                            }
                        } catch (e) {
                            console.error('Failed to parse entity response:', line);
                        }
                    }
                }
            }

            // Parse the extracted entities JSON
            try {
                const entities = JSON.parse(entityData.trim());
                return this.processAIExtractedEntities(entities, text);
            } catch (e) {
                console.error('Failed to parse entity JSON from GPT-4.1-nano:', entityData);
                return [];
            }

        } catch (error) {
            console.error('Entity extraction error with GPT-4.1-nano:', error);
            return [];
        }
    }
    
    processAIExtractedEntities(aiEntities, text) {
        const processedEntities = [];
        
        aiEntities.forEach(entity => {
            const mentions = this.findEntityMentions(entity.name, text);
            if (mentions.length > 0) {
                processedEntities.push({
                    name: entity.name,
                    type: entity.type || 'Unknown',
                    mentions: mentions
                });
            }
        });
        
        return processedEntities.sort((a, b) => b.mentions.length - a.mentions.length);
    }
    
    findEntityMentions(entityName, text) {
        const mentions = [];
        const regex = new RegExp(`\\b${this.escapeRegex(entityName)}\\b`, 'gi');
        let match;
        
        while ((match = regex.exec(text)) !== null) {
            const start = Math.max(0, match.index - 50);
            const end = Math.min(text.length, match.index + entityName.length + 50);
            const context = text.substring(start, end);
            
            mentions.push({
                index: match.index,
                context: context,
                snippet: this.highlightEntityInContext(context, entityName)
            });
        }
        
        return mentions;
    }
    
    // NO REGEX FALLBACK - ONLY GPT-4.1-nano for entity extraction as requested
    
    highlightEntityInContext(context, entityName) {
        return context.replace(new RegExp(`\\b${this.escapeRegex(entityName)}\\b`, 'gi'), 
            `<span class="snippet-entity">${entityName}</span>`);
    }
    
    selectEntity(entity) {
        // Update UI selection
        document.querySelectorAll('.entity-item').forEach(item => {
            item.classList.remove('selected');
        });
        
        const selectedItem = document.querySelector(`[data-entity-name="${entity.name}"]`);
        if (selectedItem) {
            selectedItem.classList.add('selected');
        }
        
        // Update detail panel
        const entityNameEl = document.querySelector('.selected-entity-name');
        const entityTypeEl = document.querySelector('.entity-type-badge');
        const snippetsList = document.querySelector('.snippets-list');
        
        entityNameEl.textContent = entity.name;
        entityTypeEl.textContent = entity.type;
        
        // Display all mentions/snippets
        snippetsList.innerHTML = '';
        entity.mentions.forEach((mention, index) => {
            const snippetItem = document.createElement('div');
            snippetItem.className = 'snippet-item';
            snippetItem.innerHTML = `
                <div class="snippet-context">${mention.snippet}</div>
            `;
            snippetsList.appendChild(snippetItem);
        });
        
        // Store selected entity for commands
        this.selectedEntity = entity;
    }
    
    filterEntityList(searchTerm) {
        const entityItems = document.querySelectorAll('.entity-item');
        const lowercaseSearch = searchTerm.toLowerCase();
        
        entityItems.forEach(item => {
            const entityName = item.dataset.entityName.toLowerCase();
            const entityType = item.dataset.entityType.toLowerCase();
            
            if (entityName.includes(lowercaseSearch) || entityType.includes(lowercaseSearch)) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    }
    
    executeEntityCommand(command) {
        if (!this.selectedEntity || !command.trim()) {
            alert('Please select an entity and enter a command');
            return;
        }
        
        const entityName = this.selectedEntity.name;
        const lowerCommand = command.toLowerCase().trim();
        
        // Handle rename commands
        if (lowerCommand.startsWith('rename to ')) {
            const newName = command.substring(10).trim();
            this.renameEntity(entityName, newName);
        }
        // Handle attribute changes (like "make his hair grey")
        else if (lowerCommand.includes('make') || lowerCommand.includes('change')) {
            this.applyEntityAttributeChange(entityName, command);
        }
        else {
            alert('Command not recognized. Try "rename to [name]" or "make his [attribute] [value]"');
        }
    }
    
    renameEntity(oldName, newName) {
        let content = this.editor.innerHTML;
        const regex = new RegExp(`\\b${this.escapeRegex(oldName)}\\b`, 'g');
        content = content.replace(regex, newName);
        this.editor.innerHTML = content;
        
        this.showStatus(`Renamed "${oldName}" to "${newName}"`, 3000);
        this.scheduleAutoSave();
        
        // Refresh entity list
        this.extractAndDisplayEntities();
    }
    
    async applyEntityAttributeChange(entityName, command) {
        // Use AI to understand and apply the command intelligently
        const content = this.getPlainTextContent();
        
        try {
            // First, find all mentions of the entity with context
            const mentions = this.findEntityMentions(entityName, content);
            
            if (mentions.length === 0) {
                this.showStatus(`No mentions of "${entityName}" found`, 3000);
                return;
            }
            
            // Use AI to understand the command and apply it
            const prompt = `You are editing a document. Apply this command to all mentions of "${entityName}": "${command}"
            
Here are all the mentions with context:
${mentions.map((m, i) => `${i + 1}. "...${m.context}..."`).join('\n')}

For each mention, rewrite the sentence/paragraph to reflect the requested change. Maintain the original tone and style.
Return a JSON object with this structure:
{
    "changes": [
        {
            "original": "original text",
            "modified": "modified text",
            "explanation": "what was changed"
        }
    ],
    "summary": "brief summary of all changes made"
}`;

            const response = await fetch('/api/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    command: prompt,
                    context: { 
                        isEntityEdit: true,
                        entityName: entityName,
                        userCommand: command
                    }
                })
            });
            
            if (response.ok) {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.substring(6);
                            if (data && data !== '[DONE]') {
                                try {
                                    const parsed = JSON.parse(data);
                                    if (parsed.choices && parsed.choices[0] && parsed.choices[0].delta && parsed.choices[0].delta.content) {
                                        fullResponse += parsed.choices[0].delta.content;
                                    }
                                } catch (e) {
                                    fullResponse += data;
                                }
                            }
                        }
                    }
                }
                
                // Parse the response
                let result;
                try {
                    const jsonMatch = fullResponse.match(/\{[\s\S]*\}/);
                    if (jsonMatch) {
                        result = JSON.parse(jsonMatch[0]);
                    }
                } catch (e) {
                    console.error('Failed to parse AI response:', e);
                    this.showStatus('Failed to process command', 3000);
                    return;
                }
                
                // Apply the changes
                if (result && result.changes && result.changes.length > 0) {
                    let updatedContent = content;
                    
                    // Apply changes in reverse order to maintain positions
                    result.changes.reverse().forEach(change => {
                        updatedContent = updatedContent.replace(change.original, change.modified);
                    });
                    
                    // Update the editor
                    this.editor.innerHTML = this.convertToHtml(updatedContent);
                    
                    this.showStatus(result.summary || `Applied changes to ${entityName}`, 4000);
                    this.scheduleAutoSave();
                    
                    // Refresh entity list
                    this.extractAndDisplayEntities();
                } else {
                    this.showStatus('No changes needed', 3000);
                }
            }
        } catch (error) {
            console.error('Entity command error:', error);
            this.showStatus('Failed to apply command', 3000);
        }
    }
    
    findEntityMentions(entityName, content) {
        const mentions = [];
        const lines = content.split('\n');
        const regex = new RegExp(`\\b${this.escapeRegex(entityName)}\\b`, 'gi');
        
        lines.forEach((line, lineIndex) => {
            if (regex.test(line)) {
                // Get surrounding context (previous and next line)
                const contextStart = Math.max(0, lineIndex - 1);
                const contextEnd = Math.min(lines.length - 1, lineIndex + 1);
                const context = lines.slice(contextStart, contextEnd + 1).join('\n');
                
                mentions.push({
                    line: lineIndex,
                    text: line,
                    context: context
                });
            }
        });
        
        return mentions;
    }
    
    setupCuttingRoomFloor() {
        const selectionActions = document.getElementById('selection-actions');
        const cutButton = document.getElementById('cut-to-floor-btn');
        const openButton = document.getElementById('open-cutting-room-btn');
        const closeButton = document.getElementById('close-cutting-room');
        const moveBackButton = document.getElementById('move-back-to-editor');
        const panel = document.getElementById('cutting-room-panel');
        const content = document.getElementById('cutting-room-content');
        
        // Monitor selection changes
        document.addEventListener('selectionchange', () => {
            const selection = window.getSelection();
            const hasSelection = selection.toString().trim().length > 0;
            const isInEditor = selection.anchorNode && this.editor.contains(selection.anchorNode);
            
            if (hasSelection && isInEditor) {
                // Position the buttons relative to selection
                const range = selection.getRangeAt(0);
                const rect = range.getBoundingClientRect();
                
                selectionActions.style.top = `${rect.top - 80}px`;
                selectionActions.classList.add('visible');
            } else {
                selectionActions.classList.remove('visible');
            }
        });
        
        // Cut to floor button
        cutButton.addEventListener('click', () => {
            this.cutToFloor();
        });
        
        // Open cutting room button
        openButton.addEventListener('click', () => {
            this.openCuttingRoomFloor();
        });
        
        // Move back to editor button
        moveBackButton.addEventListener('click', () => {
            this.moveSelectedTextToMainEditor();
        });
        
        // Close cutting room
        closeButton.addEventListener('click', () => {
            panel.classList.remove('visible');
            this.saveCuttingRoomContent();
        });
        
        // Make cutting room editor properly editable
        content.setAttribute('spellcheck', 'true');
        this.cuttingRoomEditor = content;
        
        // Auto-save cutting room content on changes
        content.addEventListener('input', () => {
            if (this.cuttingRoomSaveTimeout) {
                clearTimeout(this.cuttingRoomSaveTimeout);
            }
            this.cuttingRoomSaveTimeout = setTimeout(() => {
                this.saveCuttingRoomContent();
            }, 1000);
        });
        
        // Handle keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'x') {
                const selection = window.getSelection();
                if (selection.toString().trim() && this.editor.contains(selection.anchorNode)) {
                    e.preventDefault();
                    this.cutToFloor();
                }
            }
            
            // Ctrl/Cmd + Enter to insert page break
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                this.insertPageBreak();
            }
        });
        
        // Add arrow key handling for cutting room
        content.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                this.moveSelectedTextToMainEditor();
            }
        });
        
        // Load cutting room content on startup
        this.loadCuttingRoomContent();
    }
    
    moveSelectedTextToMainEditor() {
        const selection = window.getSelection();
        if (!selection.rangeCount || !selection.toString().trim()) return;
        
        const selectedText = selection.toString();
        const range = selection.getRangeAt(0);
        
        // Check if selection is in cutting room editor
        if (!this.cuttingRoomEditor.contains(selection.anchorNode)) return;
        
        // Get cursor position in main editor
        const mainSelection = window.getSelection();
        const mainRange = document.createRange();
        
        // If there's a cursor position in main editor, use it
        if (this.editor.contains(mainSelection.anchorNode)) {
            mainRange.setStart(mainSelection.anchorNode, mainSelection.anchorOffset);
            mainRange.setEnd(mainSelection.anchorNode, mainSelection.anchorOffset);
        } else {
            // Otherwise append to end of main editor
            const lastChild = this.editor.lastChild || this.editor;
            const offset = lastChild.textContent ? lastChild.textContent.length : 0;
            mainRange.setStart(lastChild, offset);
            mainRange.setEnd(lastChild, offset);
        }
        
        // Insert text at cursor position in main editor
        const textNode = document.createTextNode(selectedText);
        mainRange.insertNode(textNode);
        
        // Delete from cutting room
        range.deleteContents();
        
        // Save both documents
        this.saveCuttingRoomContent();
        this.scheduleAutoSave();
        
        // Show status
        this.showStatus('Moved text to main editor', 2000);
    }
    
    setupContextPanel() {
        const panel = document.getElementById('context-panel');
        const tab = document.getElementById('context-panel-tab');
        const closeBtn = document.getElementById('close-context-panel');
        const pinBtn = document.getElementById('pin-context-panel');
        const searchInput = document.getElementById('context-search-input');
        const searchResults = document.getElementById('context-search-results');
        const selectedList = document.getElementById('selected-context-list');
        const manualInput = document.getElementById('manual-context-input');
        const clearBtn = document.getElementById('clear-context-btn');
        
        // Initialize context storage
        this.contextFiles = [];
        this.contextMetadata = new Map();
        this.manualContext = '';
        this.contextPanelVisible = false;
        this.contextPanelPinned = localStorage.getItem('contextPanelPinned') === 'true';
        this.totalTokenCount = 0;
        
        // Set initial pin state
        if (this.contextPanelPinned) {
            panel.classList.add('pinned');
            pinBtn.classList.add('active');
            pinBtn.innerHTML = '📍';
        }
        
        // Pulse tab on first load to draw attention
        if (!localStorage.getItem('contextPanelUsed')) {
            tab.classList.add('pulse');
            setTimeout(() => {
                tab.classList.remove('pulse');
                localStorage.setItem('contextPanelUsed', 'true');
            }, 5000);
        }
        
        // Tab click handler
        tab.addEventListener('click', () => {
            this.showContextPanel();
        });
        
        // Keyboard shortcut (Ctrl/Cmd + K)
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                if (this.contextPanelVisible) {
                    this.hideContextPanel();
                } else {
                    this.showContextPanel();
                }
            }
        });
        
        // Touch/swipe gesture support for mobile
        let touchStartX = null;
        let touchStartY = null;
        
        document.addEventListener('touchstart', (e) => {
            touchStartX = e.touches[0].clientX;
            touchStartY = e.touches[0].clientY;
        });
        
        document.addEventListener('touchmove', (e) => {
            if (!touchStartX || !touchStartY) return;
            
            const touchEndX = e.touches[0].clientX;
            const touchEndY = e.touches[0].clientY;
            
            const deltaX = touchEndX - touchStartX;
            const deltaY = Math.abs(touchEndY - touchStartY);
            
            // Swipe from right edge
            if (touchStartX > window.innerWidth - 50 && deltaX < -50 && deltaY < 50) {
                this.showContextPanel();
                touchStartX = null;
                touchStartY = null;
            }
        });
        
        document.addEventListener('touchend', () => {
            touchStartX = null;
            touchStartY = null;
        });
        
        // Track mouse position for right edge detection (keep for backward compatibility)
        document.addEventListener('mousemove', (e) => {
            const screenWidth = window.innerWidth;
            const mouseX = e.clientX;
            const panel = document.getElementById('context-panel');
            
            // Show panel when mouse is at right edge
            if (mouseX >= screenWidth - 10 && !this.contextPanelVisible) {
                this.showContextPanel();
            } 
            // Hide panel when mouse moves away from the right side (unless pinned)
            else if (this.contextPanelVisible && !this.contextPanelPinned && mouseX < screenWidth - 400) {
                // Only hide if mouse is not over the panel itself
                const panelRect = panel.getBoundingClientRect();
                if (mouseX < panelRect.left) {
                    this.hideContextPanel();
                }
            }
        });
        
        // Close button
        closeBtn.addEventListener('click', () => {
            this.hideContextPanel();
        });
        
        // Pin button handler
        pinBtn.addEventListener('click', () => {
            this.contextPanelPinned = !this.contextPanelPinned;
            localStorage.setItem('contextPanelPinned', this.contextPanelPinned);
            
            if (this.contextPanelPinned) {
                panel.classList.add('pinned');
                pinBtn.classList.add('active');
                pinBtn.innerHTML = '📍';
                pinBtn.title = 'Unpin panel';
            } else {
                panel.classList.remove('pinned');
                pinBtn.classList.remove('active');
                pinBtn.innerHTML = '📌';
                pinBtn.title = 'Pin panel open';
            }
        });
        
        // Search functionality
        let searchTimeout;
        searchInput.addEventListener('input', () => {
            const query = searchInput.value.trim();
            
            clearTimeout(searchTimeout);
            if (!query) {
                searchResults.classList.remove('active');
                searchResults.innerHTML = '';
                return;
            }
            
            searchTimeout = setTimeout(() => {
                this.searchCloudVould(query);
            }, 300);
        });
        
        // Handle search result clicks
        searchResults.addEventListener('click', (e) => {
            const item = e.target.closest('.search-result-item');
            if (item) {
                this.addContextNote(item.dataset);
                searchInput.value = '';
                searchResults.classList.remove('active');
                searchResults.innerHTML = '';
            }
        });
        
        // Handle remove buttons
        selectedList.addEventListener('click', (e) => {
            if (e.target.classList.contains('remove-btn')) {
                const item = e.target.closest('.selected-context-item');
                const index = Array.from(selectedList.children).indexOf(item);
                this.removeContextNote(index);
            }
        });
        
        // Save manual context
        manualInput.addEventListener('input', () => {
            this.manualContext = manualInput.value;
        });
        
        // Clear all context
        clearBtn.addEventListener('click', () => {
            this.clearAllContext();
        });
        
        // Setup drag and drop
        this.setupDragAndDrop();
    }
    
    setupDragAndDrop() {
        const dropZone = document.getElementById('drop-zone');
        const selectedList = document.getElementById('selected-context-list');
        
        // Prevent default drag behaviors
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            document.addEventListener(eventName, (e) => {
                if (e.target.closest('.context-panel')) {
                    e.preventDefault();
                    e.stopPropagation();
                }
            });
        });
        
        // Highlight drop zone when dragging over
        ['dragenter', 'dragover'].forEach(eventName => {
            selectedList.addEventListener(eventName, (e) => {
                dropZone.classList.add('drag-over');
            });
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            selectedList.addEventListener(eventName, (e) => {
                // Only remove if leaving the selected list entirely
                if (eventName === 'dragleave' && e.relatedTarget && e.relatedTarget.closest('#selected-context-list')) {
                    return;
                }
                dropZone.classList.remove('drag-over');
            });
        });
        
        // Handle dropped files
        selectedList.addEventListener('drop', async (e) => {
            const files = e.dataTransfer.files;
            
            for (const file of files) {
                if (file.type === 'text/plain' || file.type === 'text/markdown' || file.name.endsWith('.md') || file.name.endsWith('.txt')) {
                    await this.handleDroppedFile(file);
                }
            }
        });
    }
    
    async handleDroppedFile(file) {
        try {
            const content = await file.text();
            const title = file.name.replace(/\.(md|txt)$/, '').replace(/_/g, ' ');
            
            // Check if already in context
            const existingIndex = this.contextFiles.findIndex(f => f.filename === file.name);
            if (existingIndex !== -1) {
                this.showStatus(`${file.name} already in context`, 2000);
                return;
            }
            
            // Add to context
            const fileData = {
                filename: file.name,
                title: title,
                content: content,
                tokens: this.estimateTokens(content)
            };
            
            this.contextFiles.push(fileData);
            
            // Generate metadata in background
            this.generateFileMetadata(fileData);
            
            // Update UI
            this.updateSelectedContextList();
            this.updateTokenCount();
            this.updateAISelector();
            
            this.showStatus(`Added ${file.name} to context`, 2000);
        } catch (error) {
            console.error('Error reading dropped file:', error);
            this.showStatus('Failed to read file', 2000);
        }
    }
    
    showContextPanel() {
        const panel = document.getElementById('context-panel');
        panel.classList.add('visible');
        this.contextPanelVisible = true;
    }
    
    hideContextPanel() {
        // Don't hide if pinned
        if (this.contextPanelPinned) return;
        
        const panel = document.getElementById('context-panel');
        panel.classList.remove('visible');
        this.contextPanelVisible = false;
    }
    
    getContextPanelContent() {
        if (this.contextFiles.length === 0 && !this.manualContext) {
            return null;
        }
        
        const content = {
            files: this.contextFiles.map(f => ({
                filename: f.filename,
                title: f.title,
                content: f.content,
                metadata: this.contextMetadata.get(f.filename)
            })),
            manualContext: this.manualContext,
            totalTokens: this.totalTokenCount
        };
        
        return content;
    }
    
    async searchCloudVould(query) {
        try {
            const response = await fetch(`/api/search-notes?q=${encodeURIComponent(query)}`);
            const results = await response.json();
            
            this.displaySearchResults(results);
        } catch (error) {
            console.error('Search error:', error);
        }
    }
    
    displaySearchResults(results) {
        const container = document.getElementById('context-search-results');
        
        if (results.length === 0) {
            container.innerHTML = '<div style="padding: 10px; text-align: center; color: #999;">No results found</div>';
        } else {
            container.innerHTML = results.map(result => `
                <div class="search-result-item" 
                     data-filename="${result.filename}"
                     data-title="${result.title}"
                     data-content="${result.content}">
                    <div class="search-result-title">${result.title}</div>
                    ${result.tags ? `<div class="search-result-tags">${result.tags.join(' ')}</div>` : ''}
                </div>
            `).join('');
        }
        
        container.classList.add('active');
    }
    
    addContextNote(noteData) {
        // Add to context files array
        const fileData = {
            filename: noteData.filename,
            title: noteData.title,
            content: noteData.content,
            tokens: this.estimateTokens(noteData.content)
        };
        
        this.contextFiles.push(fileData);
        
        // Generate metadata in background
        this.generateFileMetadata(fileData);
        
        // Update UI
        this.updateSelectedContextList();
        this.updateTokenCount();
        this.updateAISelector();
    }
    
    removeContextNote(index) {
        this.contextFiles.splice(index, 1);
        this.updateSelectedContextList();
        this.updateTokenCount();
        this.updateAISelector();
    }
    
    updateSelectedContextList() {
        const container = document.getElementById('selected-context-list');
        const dropZone = document.getElementById('drop-zone');
        
        // Hide drop zone if we have files
        if (this.contextFiles.length > 0) {
            dropZone.classList.add('has-files');
        } else {
            dropZone.classList.remove('has-files');
        }
        
        if (this.contextFiles.length === 0) {
            // Clear any existing content except drop zone
            Array.from(container.children).forEach(child => {
                if (child.id !== 'drop-zone') {
                    child.remove();
                }
            });
        } else {
            // Clear existing content except drop zone
            Array.from(container.children).forEach(child => {
                if (child.id !== 'drop-zone') {
                    child.remove();
                }
            });
            
            // Add file items
            const filesHTML = this.contextFiles.map((file, index) => {
                const hasMetadata = this.contextMetadata.has(file.filename);
                const snippet = file.content.split('\n').slice(0, 10).join('\n');
                
                return `
                    <div class="context-file-item" data-index="${index}">
                        <div class="context-file-header" data-filename="${file.filename}">
                            <span class="context-file-title">${file.title}</span>
                            <div class="context-file-meta">
                                <span class="file-tokens">${file.tokens} tokens</span>
                                ${hasMetadata ? '<div class="file-metadata-badge" title="Metadata available"></div>' : ''}
                                <button class="remove-btn" title="Remove">×</button>
                            </div>
                        </div>
                        <div class="context-file-snippet">${this.escapeHtml(snippet)}${file.content.split('\n').length > 10 ? '\n...' : ''}</div>
                    </div>
                `;
            }).join('');
            
            // Create a temporary div to hold the new content
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = filesHTML;
            
            // Append all new elements before the drop zone
            while (tempDiv.firstChild) {
                container.insertBefore(tempDiv.firstChild, dropZone);
            }
            
            // Add event listeners for file interactions
            container.querySelectorAll('.context-file-header').forEach(header => {
                header.addEventListener('dblclick', (e) => {
                    const filename = header.dataset.filename;
                    const file = this.contextFiles.find(f => f.filename === filename);
                    if (file) {
                        this.openFilePopup(file);
                    }
                });
            });
            
            // Remove button listeners
            container.querySelectorAll('.remove-btn').forEach((btn, index) => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const fileItem = e.target.closest('.context-file-item');
                    const fileIndex = parseInt(fileItem.dataset.index);
                    this.removeContextNote(fileIndex);
                });
            });
        }
    }
    
    clearAllContext() {
        this.contextFiles = [];
        this.contextMetadata.clear();
        this.manualContext = '';
        document.getElementById('manual-context-input').value = '';
        this.updateSelectedContextList();
        this.updateTokenCount();
        this.updateAISelector();
    }
    
    getGeminiContext() {
        // Combine all context sources for Gemini/Claude
        const contextParts = [];
        
        // Add context files
        if (this.contextFiles.length > 0) {
            contextParts.push('=== Context Files ===');
            this.contextFiles.forEach(file => {
                contextParts.push(`\n--- ${file.title} (${file.filename}) ---\n${file.content}`);
            });
        }
        
        // Add manual context
        if (this.manualContext.trim()) {
            contextParts.push('\n=== Additional Context ===');
            contextParts.push(this.manualContext);
        }
        
        return contextParts.length > 0 ? contextParts.join('\n') : null;
    }
    
    addCurrentDocToContext() {
        // Get current document content and title
        const title = this.titleField.value || 'Untitled';
        const content = this.getPlainTextContent();
        const filename = this.currentFilename || `${title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.md`;
        
        // Check if already in context
        const existingIndex = this.contextFiles.findIndex(f => f.filename === filename);
        if (existingIndex !== -1) {
            this.showStatus('Document already in context', 2000);
            return;
        }
        
        // Add to context
        const fileData = {
            filename: filename,
            title: title,
            content: content,
            tokens: this.estimateTokens(content)
        };
        
        this.contextFiles.push(fileData);
        
        // Generate metadata in background
        this.generateFileMetadata(fileData);
        
        // Update UI
        this.updateSelectedContextList();
        this.updateTokenCount();
        this.updateAISelector();
        
        // Show context panel
        this.showContextPanel();
        
        // Show status
        this.showStatus('Added current document to context', 2000);
    }
    
    setupPagination() {
        // DISABLED - PAGINATION IS DELETING CONTENT
        // this.editor.addEventListener('input', () => {
        //     clearTimeout(this.paginationTimeout);
        //     this.paginationTimeout = setTimeout(() => {
        //         this.simplePaginate();
        //     }, 300);
        // });
        
        // // Monitor for paste events
        // this.editor.addEventListener('paste', () => {
        //     setTimeout(() => this.simplePaginate(), 300);
        // });
    }
    
    checkPagination() {
        // Use new pagination system
        this.checkForPageBreak();
    }
    
    clearExtraPages() {
        // Remove all pages except the first one
        const container = document.getElementById('editor-container');
        const extraPages = container.querySelectorAll('.page-wrapper[data-page]:not([data-page="1"])');
        
        extraPages.forEach(page => {
            page.remove();
        });
        
        // Reset pages map to only contain the first page
        this.pages.clear();
        this.pages.set(1, document.querySelector('.page-wrapper[data-page="1"]'));
    }
    
    simplePaginate() {
        const container = document.getElementById('editor-container');
        
        console.log('=== PAGINATION START ===');
        
        // Remove ALL pages except first
        const allPages = container.querySelectorAll('.page-wrapper');
        console.log(`Removing ${allPages.length - 1} extra pages`);
        for (let i = 1; i < allPages.length; i++) {
            allPages[i].remove();
        }
        this.pages.clear();
        this.pages.set(1, allPages[0]);
        
        // Use CSS-based approach like Vivliostyle
        // Get the ACTUAL rendered height of content
        const pageHeightPx = 297 * 3.7795275591 - 50 * 3.7795275591; // A4 minus margins
        const titleHeight = this.titleField.offsetHeight + 30;
        const firstPageMaxHeight = pageHeightPx - titleHeight;
        
        console.log(`Page height: ${pageHeightPx}px, First page max: ${firstPageMaxHeight}px`);
        
        // Collect all block elements
        const blocks = Array.from(this.editor.children);
        if (blocks.length === 0) return;
        
        let currentPageHeight = 0;
        let currentPageNum = 1;
        let pageMaxHeight = firstPageMaxHeight;
        
        // Use the approach from ProseMirror - find natural split points
        for (let i = 0; i < blocks.length; i++) {
            const block = blocks[i];
            const blockHeight = block.offsetHeight;
            
            console.log(`Block ${i}: ${block.tagName}, height: ${blockHeight}px, total: ${currentPageHeight + blockHeight}px`);
            
            // Check if this block would overflow the page
            if (currentPageHeight + blockHeight > pageMaxHeight && i > 0) {
                console.log(`OVERFLOW! Creating page 2 at block ${i}`);
                
                // Create new page (like ProseMirror's page nodes)
                const newPage = this.createNewPage();
                const newEditor = newPage.querySelector('.editor-content');
                
                // Move remaining blocks to new page
                let movedCount = 0;
                while (i < blocks.length) {
                    newEditor.appendChild(blocks[i]);
                    movedCount++;
                    i++;
                }
                console.log(`Moved ${movedCount} blocks to page 2`);
                
                // For subsequent pages if needed
                if (newEditor.children.length > 0) {
                    setTimeout(() => {
                        this.paginateFromEditor(newEditor, pageHeightPx);
                    }, 10);
                }
                
                break;
            }
            
            currentPageHeight += blockHeight;
        }
        
        console.log('=== PAGINATION END ===');
    }
    
    paginateFromEditor(editor, maxHeight) {
        const blocks = Array.from(editor.children);
        let currentHeight = 0;
        
        for (let i = 0; i < blocks.length; i++) {
            const blockHeight = blocks[i].offsetHeight;
            
            if (currentHeight + blockHeight > maxHeight && i > 0) {
                // Split to new page
                const newPage = this.createNewPage();
                const newEditor = newPage.querySelector('.editor-content');
                
                // Move remaining
                while (i < blocks.length) {
                    newEditor.appendChild(blocks[i]);
                    i++;
                }
                
                // Continue if needed
                if (newEditor.children.length > 0) {
                    setTimeout(() => {
                        this.paginateFromEditor(newEditor, maxHeight);
                    }, 10);
                }
                
                break;
            }
            
            currentHeight += blockHeight;
        }
    }
    
    
    checkForPageBreak() {
        // Prevent concurrent pagination checks
        if (this.isPaginating) {
            console.log('Already paginating, skipping...');
            return;
        }
        
        this.isPaginating = true;
        
        try {
            // Constants for A4 page measurements
            const MM_TO_PX = 3.7795275591;
            const PAGE_HEIGHT_MM = 297;
            const VERTICAL_MARGINS_MM = 50; // 25mm top + 25mm bottom
            const CONTENT_HEIGHT_MM = PAGE_HEIGHT_MM - VERTICAL_MARGINS_MM; // 247mm
            const CONTENT_HEIGHT_PX = CONTENT_HEIGHT_MM * MM_TO_PX; // ~933px
            
            // Get all content from all existing pages
            const allContent = this.collectAllContent();
            if (allContent.length === 0) {
                console.log('No content to paginate');
                return;
            }
            
            // Calculate max heights for each page type
            const titleHeight = this.titleField ? this.titleField.offsetHeight + 30 : 0;
            const firstPageMaxHeight = CONTENT_HEIGHT_PX - titleHeight - 20; // 20px buffer
            const subsequentPageMaxHeight = CONTENT_HEIGHT_PX - 20; // 20px buffer
            
            // Clear all pages except first
            this.removeExtraPages();
            
            // Redistribute all content across pages
            this.redistributeContent(allContent, firstPageMaxHeight, subsequentPageMaxHeight);
        } finally {
            this.isPaginating = false;
        }
    }
    
    collectAllContent() {
        const allContent = [];
        
        // Collect from main editor (page 1)
        allContent.push(...Array.from(this.editor.children));
        
        // Collect from any additional pages
        for (let pageNum = 2; pageNum <= this.pages.size; pageNum++) {
            const page = this.pages.get(pageNum);
            if (page) {
                const editor = page.querySelector('.editor-content');
                if (editor && editor.children.length > 0) {
                    allContent.push(...Array.from(editor.children));
                }
            }
        }
        
        return allContent;
    }
    
    removeExtraPages() {
        // This should ONLY be called during redistribution, not during initial load!
        const container = document.getElementById('editor-container');
        // Get actual page count from DOM
        const existingPages = container.querySelectorAll('.page-wrapper');
        
        // Remove all except first
        for (let i = 1; i < existingPages.length; i++) {
            existingPages[i].remove();
        }
        
        // Clear the map of all but first
        const firstPage = this.pages.get(1);
        this.pages.clear();
        if (firstPage) {
            this.pages.set(1, firstPage);
        }
    }
    
    removeAllPages() {
        const container = document.getElementById('editor-container');
        
        // SUPER NUCLEAR: Get ALL page-wrapper elements
        const allPages = container.querySelectorAll('.page-wrapper');
        console.log(`removeAllPages: Found ${allPages.length} total pages`);
        
        // Remove everything except the very first one
        let keptFirst = false;
        allPages.forEach((page, index) => {
            if (index === 0) {
                // Keep the first page but ensure it's properly set up
                page.setAttribute('data-page', '1');
                const pageNum = page.querySelector('.page-number');
                if (pageNum) pageNum.textContent = '1';
                keptFirst = true;
                console.log('Keeping first page');
            } else {
                console.log(`Removing page at index ${index}`);
                page.remove();
            }
        });
        
        // If somehow we didn't have any pages, that's a problem
        if (!keptFirst) {
            console.error('WARNING: No pages found to keep!');
        }
        
        // Clear and reset the pages map
        this.pages.clear();
        this.currentPage = 1;
        
        // Re-find the first page
        const firstPage = container.querySelector('.page-wrapper');
        if (firstPage) {
            this.pages.set(1, firstPage);
            // Make sure the editor reference is correct
            const firstEditor = firstPage.querySelector('.editor-content');
            if (firstEditor) {
                this.editor = firstEditor;
            }
        } else {
            console.error('CRITICAL: Could not find first page after cleanup!');
        }
        
        // Final verification
        const remainingPages = container.querySelectorAll('.page-wrapper');
        if (remainingPages.length !== 1) {
            console.error(`ERROR: Should have 1 page but have ${remainingPages.length}`);
        }
    }
    
    redistributeContent(allContent, firstPageMaxHeight, subsequentPageMaxHeight) {
        // Clear main editor
        this.editor.innerHTML = '';
        
        let currentPageNum = 1;
        let currentPageHeight = 0;
        let currentPageMaxHeight = firstPageMaxHeight;
        let currentEditor = this.editor;
        
        for (const element of allContent) {
            const elementHeight = this.measureElementHeight(element);
            
            // Check if element fits on current page
            if (currentPageHeight + elementHeight > currentPageMaxHeight && currentPageHeight > 0) {
                // Need new page
                currentPageNum++;
                
                // Create new page if it doesn't exist
                if (!this.pages.has(currentPageNum)) {
                    const newPage = this.createNewPage();
                    currentEditor = newPage.querySelector('.editor-content');
                } else {
                    const page = this.pages.get(currentPageNum);
                    currentEditor = page.querySelector('.editor-content');
                    currentEditor.innerHTML = '';
                }
                
                // Reset for new page
                currentPageHeight = 0;
                currentPageMaxHeight = subsequentPageMaxHeight;
            }
            
            // Add element to current page
            currentEditor.appendChild(element);
            currentPageHeight += elementHeight;
        }
    }
    
    measureElementHeight(element) {
        // If element is already in DOM, measure it
        if (element.offsetHeight) {
            const styles = window.getComputedStyle(element);
            const marginTop = parseInt(styles.marginTop || 0);
            const marginBottom = parseInt(styles.marginBottom || 0);
            return element.offsetHeight + marginTop + marginBottom;
        }
        
        // Otherwise, temporarily add to measure
        const temp = element.cloneNode(true);
        temp.style.position = 'absolute';
        temp.style.visibility = 'hidden';
        temp.style.left = '-9999px';
        document.body.appendChild(temp);
        
        const height = temp.offsetHeight + 
                      parseInt(window.getComputedStyle(temp).marginBottom || 0) +
                      parseInt(window.getComputedStyle(temp).marginTop || 0);
        
        document.body.removeChild(temp);
        return height || 30; // Default 30px if measurement fails
    }
    
    isAtPageLimit() {
        const editor = this.editor;
        if (!editor) {
            console.warn('isAtPageLimit: editor is null');
            return false;
        }
        const titleHeight = this.titleField.offsetHeight + 30;
        const maxHeight = (247 * 3.7795275591) - titleHeight - 40;
        const isAtLimit = editor.scrollHeight >= maxHeight;
        
        // Debug logging
        if (isAtLimit) {
            console.log('Page limit reached:', {
                scrollHeight: editor.scrollHeight,
                maxHeight: maxHeight,
                titleHeight: titleHeight
            });
        }
        
        return isAtLimit;
    }
    
    splitContentToNewPage(maxHeight) {
        const editor = this.editor;
        const elements = Array.from(editor.children);
        let currentHeight = 0;
        let splitIndex = -1;
        
        // Find where to split
        for (let i = 0; i < elements.length; i++) {
            const element = elements[i];
            const elementHeight = element.offsetHeight;
            
            if (currentHeight + elementHeight > maxHeight) {
                splitIndex = i;
                break;
            }
            currentHeight += elementHeight;
        }
        
        // If we found a split point, move content to next page
        if (splitIndex > 0 && splitIndex < elements.length) {
            const elementsToMove = elements.slice(splitIndex);
            this.moveToNextPage(elementsToMove);
        }
    }
    
    moveToNextPage(elements) {
        // Check if next page exists, if not create it
        let nextPage = document.querySelector('.page-wrapper[data-page="2"]');
        if (!nextPage) {
            nextPage = this.createNewPage();
        }
        
        const nextEditor = nextPage.querySelector('.editor-content');
        if (nextEditor) {
            elements.forEach(element => {
                nextEditor.appendChild(element);
            });
        }
    }
    
    createNewPageIfNeeded() {
        const currentPage = this.currentPage || 1;
        const nextPage = this.pages.get(currentPage + 1);
        
        if (!nextPage) {
            const newPage = this.createNewPage();
            const newEditor = newPage.querySelector('.editor-content');
            
            // Focus on the new page's editor
            if (newEditor) {
                newEditor.focus();
                this.currentPage = currentPage + 1;
                this.editor = newEditor;
            }
        }
    }
    
    createNewPageWithContent(pageNum, elements) {
        // Create the page if it doesn't exist
        if (!this.pages.has(pageNum)) {
            this.createNewPage();
        }
        
        const page = this.pages.get(pageNum);
        const editor = page.querySelector('.editor-content');
        
        if (editor) {
            // Clear existing content
            editor.innerHTML = '';
            
            // Add new elements
            elements.forEach(element => {
                editor.appendChild(element);
            });
        }
    }
    
    createAdditionalPages(allElements, startIndex, pageHeight) {
        let currentPageNum = 2;
        let currentIndex = startIndex;
        
        while (currentIndex < allElements.length) {
            // Create new page
            const newPage = this.createNewPage();
            const newEditor = newPage.querySelector('.editor-content');
            
            // Fill the new page with content
            let currentHeight = 0;
            let elementsOnPage = 0;
            
            while (currentIndex < allElements.length) {
                const element = allElements[currentIndex];
                const elementHeight = element.offsetHeight;
                const marginBottom = parseInt(window.getComputedStyle(element).marginBottom || 0);
                const totalHeight = elementHeight + marginBottom;
                
                if (currentHeight + totalHeight > pageHeight && elementsOnPage > 0) {
                    // This element won't fit, break to next page
                    break;
                }
                
                // Move element to new page
                newEditor.appendChild(element);
                currentHeight += totalHeight;
                elementsOnPage++;
                currentIndex++;
            }
            
            currentPageNum++;
        }
    }
    
    moveElementsToPage(elements, targetPageNum) {
        const targetPage = this.pages.get(targetPageNum);
        if (!targetPage) return;
        
        const targetEditor = targetPageNum === 1 ? this.editor : targetPage.querySelector('.editor-content');
        if (!targetEditor) return;
        
        // Move elements
        elements.forEach(element => {
            targetEditor.appendChild(element);
        });
    }
    
    shouldSplitPage() {
        // Get all paragraphs
        const paragraphs = this.editor.querySelectorAll('p, div');
        if (paragraphs.length === 0) return false;
        
        // Calculate where to split
        let accumulatedHeight = this.titleField.offsetHeight + 120;
        
        for (let i = 0; i < paragraphs.length; i++) {
            const para = paragraphs[i];
            accumulatedHeight += para.offsetHeight;
            
            if (accumulatedHeight > this.pageHeight * 0.85) {
                // Found split point
                return true;
            }
        }
        
        return false;
    }
    
    createNewPage() {
        const container = document.getElementById('editor-container');
        
        // Get actual page count from DOM, not from this.pages which might be out of sync
        const existingPages = container.querySelectorAll('.page-wrapper');
        const pageNum = existingPages.length + 1;
        
        console.log(`Creating page ${pageNum}, found ${existingPages.length} existing pages`);
        
        // Create new page wrapper
        const newPage = document.createElement('div');
        newPage.className = 'page-wrapper';
        newPage.setAttribute('data-page', pageNum);
        
        // Create new editor div for the page
        const newEditor = document.createElement('div');
        newEditor.className = 'editor-content';
        newEditor.contentEditable = 'true';
        newEditor.id = `editor-page-${pageNum}`;
        
        // KILLED - NO MORE PAGINATION
        // newEditor.addEventListener('input', () => {
        //     this.editor = newEditor;
        //     this.currentPage = pageNum;
        // });
        
        // newEditor.addEventListener('paste', () => {
        //     this.editor = newEditor;
        //     this.currentPage = pageNum;
        // });
        
        newEditor.addEventListener('focus', () => {
            this.currentPage = pageNum;
            this.editor = newEditor;
        });
        
        // Add page number
        const pageNumber = document.createElement('div');
        pageNumber.className = 'page-number';
        pageNumber.textContent = pageNum;
        
        // Assemble page
        const wrapper = document.createElement('div');
        wrapper.className = 'main-editor-wrapper';
        wrapper.appendChild(newEditor);
        
        newPage.appendChild(wrapper);
        newPage.appendChild(pageNumber);
        container.appendChild(newPage);
        
        // Store page reference
        this.pages.set(pageNum, newPage);
        
        return newPage;
    }
    
    moveOverflowContent(newPageNum) {
        // This is a simplified version - in production you'd want more sophisticated splitting
        const paragraphs = this.editor.querySelectorAll('p, div');
        let accumulatedHeight = this.titleField.offsetHeight + 120;
        let splitIndex = -1;
        
        for (let i = 0; i < paragraphs.length; i++) {
            accumulatedHeight += paragraphs[i].offsetHeight;
            
            if (accumulatedHeight > this.pageHeight * 0.85) {
                splitIndex = i;
                break;
            }
        }
        
        if (splitIndex > -1 && splitIndex < paragraphs.length) {
            const newEditor = document.getElementById(`editor-page-${newPageNum}`);
            
            // Move paragraphs after split point to new page
            for (let i = splitIndex; i < paragraphs.length; i++) {
                newEditor.appendChild(paragraphs[i].cloneNode(true));
                paragraphs[i].remove();
            }
        }
    }
    
    getPageContext(pageNumber) {
        // Get content from specific page for AI context
        const page = this.pages.get(pageNumber);
        if (!page) return '';
        
        const editor = page.querySelector('.editor-content');
        return editor ? editor.textContent : '';
    }
    
    moveToNextPage() {
        // Check if next page exists
        const nextPageNum = this.currentPage + 1;
        
        if (!this.pages.has(nextPageNum)) {
            this.createNewPage();
        }
        
        // Move cursor to beginning of next page
        const nextPage = this.pages.get(nextPageNum);
        const nextEditor = nextPage.querySelector('.editor-content');
        
        // Set focus on next page editor
        nextEditor.focus();
        
        // Place cursor at beginning
        const range = document.createRange();
        const selection = window.getSelection();
        range.setStart(nextEditor, 0);
        range.collapse(true);
        selection.removeAllRanges();
        selection.addRange(range);
        
        // Update current page
        this.currentPage = nextPageNum;
        
        // Scroll to new page
        nextPage.scrollIntoView({ behavior: 'smooth', block: 'start' });
        
        // Update main editor reference
        this.editor = nextEditor;
        
        // Scroll to new page
        nextPage.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    
    insertPageBreak() {
        // Create new page if doesn't exist
        if (!this.pages.has(this.currentPage + 1)) {
            this.createNewPage();
        }
        
        // Move to next page
        this.moveToNextPage();
    }
    
    cutToFloor() {
        const selection = window.getSelection();
        if (!selection.rangeCount) return;
        
        const range = selection.getRangeAt(0);
        const textContent = selection.toString();
        
        if (!textContent.trim()) return;
        
        // Get current cutting room content
        let currentContent = this.cuttingRoomEditor.textContent;
        
        // Add separator if there's existing content
        if (currentContent.trim()) {
            currentContent += '\n\n---\n\n';
        }
        
        // Add timestamp and the cut content
        const timestamp = new Date().toLocaleString();
        currentContent += `[Cut at ${timestamp}]\n\n${textContent}`;
        
        // Update cutting room editor
        this.cuttingRoomEditor.textContent = currentContent;
        
        // Delete the selected content from main editor
        range.deleteContents();
        
        // Auto-save cutting room content
        this.saveCuttingRoomContent();
        
        // Show status
        this.showStatus('Cut to Cutting Room Floor', 2000);
        
        // Clear selection
        selection.removeAllRanges();
        
        // Hide selection actions
        document.getElementById('selection-actions').classList.remove('visible');
    }
    
    openCuttingRoomFloor() {
        const panel = document.getElementById('cutting-room-panel');
        this.loadCuttingRoomContent();
        panel.classList.add('visible');
    }
    
    async saveCuttingRoomContent() {
        const title = this.titleField.value || 'untitled';
        const content = this.cuttingRoomEditor.textContent;
        
        // Save to cutting room file (append _cuttingroom to filename)
        const filename = `${title}_cuttingroom`;
        
        try {
            const response = await fetch('/api/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ 
                    title: filename, 
                    content: content 
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to save cutting room');
            }
            
            console.log('Cutting room content saved');
        } catch (error) {
            console.error('Error saving cutting room:', error);
        }
    }
    
    async loadCuttingRoomContent() {
        const title = this.titleField.value || 'untitled';
        const filename = `${title}_cuttingroom.md`;
        
        try {
            const response = await fetch(`/api/load/${filename}`);
            if (!response.ok) {
                // File doesn't exist yet, that's okay
                this.cuttingRoomEditor.textContent = '';
                return;
            }
            
            const data = await response.json();
            this.cuttingRoomEditor.textContent = data.content || '';
        } catch (error) {
            console.error('Error loading cutting room:', error);
            this.cuttingRoomEditor.textContent = '';
        }
    }
    
    
    showFootnotePopup(element, event) {
        const footnoteNum = element.getAttribute('data-footnote');
        const footnoteContent = element.title || '';
        
        // Remove any existing popup
        const existingPopup = document.querySelector('.footnote-popup');
        if (existingPopup) {
            existingPopup.remove();
        }
        
        // Create popup
        const popup = document.createElement('div');
        popup.className = 'footnote-popup visible';
        popup.textContent = footnoteContent;
        
        // Position near the footnote number
        const rect = element.getBoundingClientRect();
        popup.style.left = rect.left + 'px';
        popup.style.top = (rect.bottom + 5) + 'px';
        
        document.body.appendChild(popup);
        
        // Remove popup when clicking elsewhere
        setTimeout(() => {
            document.addEventListener('click', function removePopup(e) {
                if (!popup.contains(e.target)) {
                    popup.remove();
                    document.removeEventListener('click', removePopup);
                }
            });
        }, 100);
    }
    
    handleUrlFootnote() {
        // Get the current selection or find the text before //
        const selection = window.getSelection();
        let selectedText = '';
        let startOffset = 0;
        
        if (selection.rangeCount > 0 && !selection.isCollapsed) {
            // User has selected text
            selectedText = selection.toString();
            const range = selection.getRangeAt(0);
            startOffset = this.getAbsoluteOffset(range.startContainer, range.startOffset);
        } else {
            // Find text between last footnote and //
            const content = this.editor.textContent;
            const doubleSlashPos = content.lastIndexOf('//');
            
            // Find the last footnote marker before //
            const beforeSlash = content.substring(0, doubleSlashPos);
            const lastFootnoteMatch = beforeSlash.match(/\[\^(\d+)\][^[]*$/);
            
            if (lastFootnoteMatch) {
                startOffset = beforeSlash.lastIndexOf(lastFootnoteMatch[0]) + lastFootnoteMatch[0].length;
                selectedText = content.substring(startOffset, doubleSlashPos).trim();
            } else {
                // No previous footnote, take from start of line
                const lastNewline = beforeSlash.lastIndexOf('\n');
                startOffset = lastNewline + 1;
                selectedText = content.substring(startOffset, doubleSlashPos).trim();
            }
        }
        
        if (!selectedText) return;
        
        // Create input for URL
        this.showUrlInput(selectedText, startOffset);
    }
    
    showUrlInput(text, startOffset) {
        // Store cursor position before removing //
        const selection = window.getSelection();
        let rect = { left: 0, bottom: 0 };
        
        if (selection.rangeCount > 0) {
            const range = selection.getRangeAt(0);
            rect = range.getBoundingClientRect();
        }
        
        // If position is invalid, use editor position as fallback
        if (rect.left === 0 && rect.bottom === 0) {
            const editorRect = this.editor.getBoundingClientRect();
            rect = {
                left: editorRect.left + editorRect.width / 2,
                bottom: editorRect.top + 100 // Approximate line position
            };
        }
        
        // Remove the '//' from editor
        const content = this.editor.textContent;
        const doubleSlashPos = content.lastIndexOf('//');
        if (doubleSlashPos !== -1) {
            const before = content.substring(0, doubleSlashPos);
            const after = content.substring(doubleSlashPos + 2);
            this.editor.textContent = before + after;
        }
        
        // Create inline input
        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = 'Enter footnote text...';
        input.className = 'footnote-input';
        input.style.cssText = `
            position: fixed;
            left: 50%;
            transform: translateX(-50%);
            top: ${rect.bottom + 10}px;
            padding: 10px 14px;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            font-size: 15px;
            width: 400px;
            max-width: 90vw;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
            background: white;
        `;
        
        document.body.appendChild(input);
        input.focus();
        
        const handleSubmit = async () => {
            const url = input.value.trim();
            if (!url) {
                input.remove();
                return;
            }
            
            // Find existing footnote numbers to get next number
            const existingNumbers = this.editor.querySelectorAll('.footnote-number').length;
            const nextNum = existingNumbers + 1;
            
            // Save footnote to database
            await this.footnoteManager.saveFootnote({
                url: url,
                text: text,
                documentId: this.titleField.value || 'untitled',
                footnoteNumber: nextNum
            });
            
            // Add superscript number after the text
            const textNode = this.findTextNodeAtOffset(startOffset + text.length);
            if (textNode) {
                const offset = startOffset + text.length - this.getTextOffset(textNode.node);
                textNode.node.splitText(offset);
                
                // Create superscript number
                const sup = document.createElement('sup');
                sup.className = 'footnote-number';
                sup.setAttribute('data-footnote', nextNum);
                sup.textContent = nextNum;
                sup.title = url;
                
                textNode.node.parentNode.insertBefore(sup, textNode.node.nextSibling);
            }
            
            // Add footnote reference at the bottom
            this.appendFootnoteReference(nextNum, url);
            
            input.remove();
            this.scheduleAutoSave();
            this.showStatus(`Added footnote [^${nextNum}]`, 2000);
        };
        
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                handleSubmit();
            } else if (e.key === 'Escape') {
                input.remove();
            }
        });
        
        // Don't auto-submit on blur - only on Enter
        input.addEventListener('blur', () => {
            // Give a small delay to check if user clicked elsewhere
            setTimeout(() => {
                if (document.activeElement !== input) {
                    input.remove();
                }
            }, 200);
        });
    }
    
    getAbsoluteOffset(container, offset) {
        let absoluteOffset = 0;
        const walker = document.createTreeWalker(
            this.editor,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let node;
        while (node = walker.nextNode()) {
            if (node === container) {
                return absoluteOffset + offset;
            }
            absoluteOffset += node.textContent.length;
        }
        
        return absoluteOffset;
    }
    
    findTextNodeAtOffset(offset) {
        let currentOffset = 0;
        const walker = document.createTreeWalker(
            this.editor,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let node;
        while (node = walker.nextNode()) {
            const nodeLength = node.textContent.length;
            if (currentOffset + nodeLength >= offset) {
                return {
                    node: node,
                    offset: offset - currentOffset
                };
            }
            currentOffset += nodeLength;
        }
        
        return null;
    }
    
    getTextOffset(targetNode) {
        let offset = 0;
        const walker = document.createTreeWalker(
            this.editor,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let node;
        while (node = walker.nextNode()) {
            if (node === targetNode) {
                return offset;
            }
            offset += node.textContent.length;
        }
        
        return offset;
    }
    
    appendFootnoteReference(number, content) {
        // Check if we already have a references section
        let referencesDiv = document.getElementById('footnote-references');
        if (!referencesDiv) {
            // Create references section at bottom (without title)
            referencesDiv = document.createElement('div');
            referencesDiv.id = 'footnote-references';
            referencesDiv.className = 'footnote-references';
            referencesDiv.innerHTML = '<div class="references-divider"></div>';
            this.editor.parentNode.insertBefore(referencesDiv, this.editor.nextSibling);
        }
        
        // Check if footnote reference already exists
        const existingRef = referencesDiv.querySelector(`.reference-number[data-number="${number}"]`);
        if (existingRef) {
            console.log(`Footnote ${number} already exists, skipping duplicate`);
            return;
        }
        
        // Determine if content is a URL
        const isURL = this.isValidURL(content);
        
        // Add new reference
        const refItem = document.createElement('div');
        refItem.className = 'reference-item';
        
        const refNumber = document.createElement('sup');
        refNumber.className = 'reference-number';
        refNumber.textContent = number;
        refNumber.dataset.number = number; // Add data attribute for checking duplicates
        
        const refContent = document.createElement('span');
        refContent.className = 'reference-content';
        refContent.contentEditable = 'true';
        
        if (isURL) {
            // Make URL clickable
            const link = document.createElement('a');
            link.href = content;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = content;
            link.contentEditable = 'false';
            refContent.appendChild(link);
        } else {
            refContent.textContent = content;
        }
        
        refItem.appendChild(refNumber);
        refItem.appendChild(refContent);
        
        // Add edit functionality
        refContent.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                refContent.blur();
            }
        });
        
        refContent.addEventListener('blur', () => {
            this.scheduleAutoSave();
        });
        
        referencesDiv.appendChild(refItem);
        this.restoreCursorPosition();
    }
    
    checkFootnoteDeletion() {
        // Get all current footnote numbers in the text
        const footnoteElements = this.editor.querySelectorAll('sup.footnote-number');
        const existingNumbers = new Set();
        
        footnoteElements.forEach(sup => {
            existingNumbers.add(sup.getAttribute('data-footnote'));
        });
        
        // Check all footnote references at the bottom
        const referencesDiv = document.getElementById('footnote-references');
        if (!referencesDiv) return;
        
        const referenceItems = referencesDiv.querySelectorAll('.footnote-reference');
        referenceItems.forEach(item => {
            const refNum = item.querySelector('.reference-number').textContent;
            if (!existingNumbers.has(refNum)) {
                // This reference no longer has a corresponding footnote number
                item.remove();
            }
        });
        
        // Also check for orphaned footnote numbers (references that were deleted)
        const referenceNumbers = new Set();
        referencesDiv.querySelectorAll('.reference-number').forEach(ref => {
            referenceNumbers.add(ref.textContent);
        });
        
        footnoteElements.forEach(sup => {
            const num = sup.getAttribute('data-footnote');
            if (!referenceNumbers.has(num)) {
                sup.remove();
            }
        });
        
        // Remove the references section if empty
        if (referencesDiv.querySelectorAll('.footnote-reference').length === 0) {
            referencesDiv.remove();
        }
    }
    
    isValidURL(string) {
        try {
            new URL(string);
            return true;
        } catch (_) {
            // Check for common URL patterns without protocol
            const urlPattern = /^(www\.|[a-zA-Z0-9-]+\.)[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
            return urlPattern.test(string);
        }
    }
    
    detectFilesInCommand(command) {
        const files = [];
        
        // Look for file patterns in the command
        const filePatterns = [
            /\b(\w+\.md)\b/g,  // Direct .md file references
            /all\s+files/gi,     // "all files"
            /files?\s+in\s+(\w+)/gi,  // "files in folder"
            /merge\s+(\w+)\s+and\s+(\w+)/gi,  // "merge X and Y"
        ];
        
        filePatterns.forEach(pattern => {
            const matches = command.matchAll(pattern);
            for (const match of matches) {
                if (match[1] && match[1].endsWith('.md')) {
                    files.push(match[1]);
                }
                if (match[2] && match[2].endsWith('.md')) {
                    files.push(match[2]);
                }
            }
        });
        
        // If "all files" is mentioned, add a special marker
        if (/all\s+files/i.test(command)) {
            files.push('*');
        }
        
        return [...new Set(files)]; // Remove duplicates
    }
    
    showAIIndicator(aiName) {
        // Remove existing indicator
        const existing = document.querySelector('.ai-indicator');
        if (existing) existing.remove();
        
        // Create new indicator
        const indicator = document.createElement('div');
        indicator.className = 'ai-indicator';
        if (aiName.toLowerCase() === 'claude') {
            indicator.classList.add('claude');
        }
        indicator.innerHTML = `
            <span class="ai-name">${aiName}</span>
            <span class="ai-status">Processing...</span>
        `;
        
        // Add to chatbox header
        const chatboxHeader = document.querySelector('.chatbox-header');
        if (chatboxHeader) {
            chatboxHeader.appendChild(indicator);
        }
        
        // Auto-hide after processing
        setTimeout(() => {
            if (indicator.querySelector('.ai-status').textContent === 'Processing...') {
                indicator.querySelector('.ai-status').textContent = 'Ready';
            }
        }, 2000);
    }
    
    handleClaudeResponse(data) {
        // Handle Claude-specific response format
        switch (data.type) {
            case 'system':
                if (data.subtype === 'init') {
                    this.claudeSessionId = data.session_id;
                    console.log('Claude session initialized:', data);
                }
                break;
                
            case 'assistant':
                // Claude's response
                if (data.message && data.message.content) {
                    const content = data.message.content
                        .map(block => block.text || '')
                        .join('\n');
                    this.addChatMessage('assistant', content);
                }
                break;
                
            case 'user':
                // Echo of user message (skip)
                break;
                
            case 'result':
                if (data.subtype === 'success') {
                    this.addChatMessage('assistant', `✓ Operation completed successfully (${data.num_turns} turns)`);
                } else if (data.subtype === 'error_max_turns') {
                    this.addChatMessage('error', 'Reached maximum turns limit');
                } else if (data.subtype === 'error_during_execution') {
                    this.addChatMessage('error', 'Error during execution');
                }
                
                // Update AI indicator
                const indicator = document.querySelector('.ai-indicator .ai-status');
                if (indicator) {
                    indicator.textContent = 'Complete';
                }
                break;
                
            case 'error':
                this.addChatMessage('error', data.message || 'Claude error occurred');
                break;
                
            default:
                console.log('Unhandled Claude response:', data);
        }
    }
    
    // New methods for enhanced context panel
    estimateTokens(text) {
        // Rough estimate: 1 token ≈ 4 characters
        return Math.ceil(text.length / 4);
    }
    
    updateTokenCount() {
        this.totalTokenCount = this.contextFiles.reduce((sum, file) => sum + file.tokens, 0);
        const manualTokens = this.estimateTokens(this.manualContext);
        this.totalTokenCount += manualTokens;
        
        const tokenElement = document.getElementById('context-token-count');
        if (tokenElement) {
            tokenElement.textContent = `(${this.totalTokenCount} tokens)`;
        }
    }
    
    updateAISelector() {
        const aiTypeElement = document.querySelector('.ai-type');
        if (!aiTypeElement) return;
        
        // Determine which AI to use based on context
        let aiName = 'GPT-4.1';
        
        if (this.contextFiles.length > 1 || this.totalTokenCount > 4000) {
            aiName = 'Claude';
            aiTypeElement.classList.add('claude');
            aiTypeElement.classList.remove('gemini');
        } else {
            aiTypeElement.classList.remove('claude', 'gemini');
        }
        
        aiTypeElement.textContent = aiName;
    }
    
    openFilePopup(file) {
        const overlay = document.getElementById('file-popup-overlay');
        const titleElement = document.getElementById('popup-file-title');
        const editorElement = document.getElementById('popup-file-editor');
        const saveButton = document.getElementById('save-file-popup');
        const closeButton = document.getElementById('close-file-popup');
        
        // Set content
        titleElement.textContent = file.title;
        editorElement.value = file.content;
        
        // Show overlay
        overlay.classList.add('visible');
        
        // Save button handler
        const saveHandler = async () => {
            const newContent = editorElement.value;
            file.content = newContent;
            file.tokens = this.estimateTokens(newContent);
            
            // Update the actual file
            try {
                const response = await fetch('/api/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        title: file.title,
                        content: newContent
                    })
                });
                
                if (response.ok) {
                    const status = document.getElementById('popup-status');
                    status.textContent = 'Saved!';
                    status.classList.add('visible');
                    setTimeout(() => status.classList.remove('visible'), 2000);
                    
                    // Regenerate metadata
                    this.generateFileMetadata(file);
                    
                    // Update UI
                    this.updateSelectedContextList();
                    this.updateTokenCount();
                }
            } catch (error) {
                console.error('Save error:', error);
            }
        };
        
        saveButton.onclick = saveHandler;
        
        // Close button handler
        const closeHandler = () => {
            overlay.classList.remove('visible');
            saveButton.onclick = null;
            closeButton.onclick = null;
        };
        
        closeButton.onclick = closeHandler;
        
        // Close on overlay click
        overlay.onclick = (e) => {
            if (e.target === overlay) {
                closeHandler();
            }
        };
    }
    
    async generateFileMetadata(file) {
        // Skip if already generating or exists
        if (this.contextMetadata.has(file.filename)) return;
        
        try {
            // Use GPT-4.1 to generate metadata
            const prompt = `Analyze this document and provide structured metadata:

Title: ${file.title}
Content: ${file.content.substring(0, 2000)}${file.content.length > 2000 ? '...' : ''}

Please provide a JSON response with this exact structure:
{
    "structure": ["Main section 1", "Main section 2", "etc"],
    "purpose": "One sentence describing the document's purpose",
    "facts": [
        {"claim": "Fact 1", "source": "Source or context"},
        {"claim": "Fact 2", "source": "Source or context"}
    ],
    "entities": [
        {"name": "Entity Name", "type": "person/place/org/concept", "context": "Brief context"}
    ]
}`;
            
            const response = await fetch('/api/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    command: prompt,
                    context: { 
                        content: file.content,
                        isMetadataGeneration: true 
                    }
                })
            });
            
            if (response.ok) {
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                
                // Read streaming response
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.substring(6);
                            if (data && data !== '[DONE]') {
                                try {
                                    const parsed = JSON.parse(data);
                                    if (parsed.choices && parsed.choices[0] && parsed.choices[0].delta && parsed.choices[0].delta.content) {
                                        fullResponse += parsed.choices[0].delta.content;
                                    }
                                } catch (e) {
                                    // Try as plain text
                                    fullResponse += data;
                                }
                            }
                        }
                    }
                }
                
                // Parse the response as JSON
                let metadata;
                try {
                    // Extract JSON from response (in case there's extra text)
                    const jsonMatch = fullResponse.match(/\{[\s\S]*\}/);
                    if (jsonMatch) {
                        metadata = JSON.parse(jsonMatch[0]);
                    } else {
                        throw new Error('No JSON found in response');
                    }
                } catch (parseError) {
                    console.error('Failed to parse metadata JSON:', parseError);
                    // Create default metadata
                    metadata = {
                        structure: ['Document structure pending analysis'],
                        purpose: 'Document purpose pending analysis',
                        facts: [],
                        entities: []
                    };
                }
                
                // Add metadata with timestamp
                metadata.generated = new Date().toISOString();
                metadata.filename = file.filename;
                
                this.contextMetadata.set(file.filename, metadata);
                
                // Save to disk for future use
                this.saveMetadata(file.filename, metadata);
                
                // Update UI
                this.updateSelectedContextList();
            }
        } catch (error) {
            console.error('Metadata generation error:', error);
            
            // Create minimal metadata on error
            const metadata = {
                generated: new Date().toISOString(),
                structure: ['Error analyzing structure'],
                purpose: 'Error analyzing purpose',
                facts: [],
                entities: [],
                error: error.message
            };
            
            this.contextMetadata.set(file.filename, metadata);
            this.updateSelectedContextList();
        }
    }
    
    async saveMetadata(filename, metadata) {
        // Save metadata to .edith/metadata/ directory
        const metadataPath = `.edith/metadata/${filename}.json`;
        
        try {
            await fetch('/api/save-metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: metadataPath,
                    metadata: metadata
                })
            });
        } catch (error) {
            console.error('Error saving metadata:', error);
        }
    }
    
    async saveEntityData(filename) {
        if (!this.entityIndexer || !this.entityIndexer.entityGraph) return;
        
        // Prepare entity data for persistence
        const entityData = {
            entities: {},
            mentions: {},
            facts: {},
            relationships: [],
            lastIndexed: new Date().toISOString()
        };
        
        // Export entities
        for (const [entityId, entity] of this.entityIndexer.entityGraph) {
            entityData.entities[entityId] = {
                id: entity.id,
                name: entity.name,
                type: entity.type,
                confidence: entity.confidence,
                variants: entity.variants || [],
                metadata: entity.metadata || {}
            };
            
            // Export mentions
            const mentions = this.entityIndexer.mentionIndex.get(entityId) || [];
            entityData.mentions[entityId] = mentions.map(m => ({
                text: m.text,
                position: m.position,
                context: m.context,
                confidence: m.confidence
            }));
            
            // Export facts if available
            if (entity.facts) {
                entityData.facts[entityId] = entity.facts;
            }
        }
        
        // Save entity data as metadata
        const entityMetadataPath = `.edith/metadata/entities/${filename}.json`;
        
        try {
            await fetch('/api/save-metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: entityMetadataPath,
                    metadata: entityData
                })
            });
            
            console.log(`Entity data saved for ${filename}`);
        } catch (error) {
            console.error('Error saving entity data:', error);
        }
    }
    
    async loadEntityData(filename) {
        if (!this.entityIndexer) return;
        
        const entityMetadataPath = `.edith/metadata/entities/${filename}.json`;
        
        try {
            const response = await fetch('/api/metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: entityMetadataPath
                })
            });
            
            if (!response.ok) {
                console.log('No entity data found for', filename);
                return;
            }
            
            const data = await response.json();
            const entityData = data.metadata;
            
            // Check if entityData exists and has the expected structure
            if (!entityData || typeof entityData !== 'object') {
                console.log('Invalid entity data structure');
                return;
            }
            
            // Restore entity graph
            this.entityIndexer.entityGraph.clear();
            this.entityIndexer.mentionIndex.clear();
            this.entityIndexer.typeIndex.clear();
            
            // Import entities
            if (!entityData.entities || typeof entityData.entities !== 'object') {
                console.log('No entities found in entity data');
                return;
            }
            
            for (const [entityId, entity] of Object.entries(entityData.entities)) {
                this.entityIndexer.entityGraph.set(entityId, entity);
                
                // Update type index
                if (!this.entityIndexer.typeIndex.has(entity.type)) {
                    this.entityIndexer.typeIndex.set(entity.type, new Set());
                }
                this.entityIndexer.typeIndex.get(entity.type).add(entityId);
                
                // Import mentions
                if (entityData.mentions && entityData.mentions[entityId]) {
                    this.entityIndexer.mentionIndex.set(entityId, entityData.mentions[entityId]);
                }
                
                // Import facts
                if (entityData.facts && entityData.facts[entityId]) {
                    entity.facts = entityData.facts[entityId];
                }
            }
            
            // Trigger UI update
            document.dispatchEvent(new CustomEvent('entityIndexUpdated', {
                detail: {
                    entityCount: this.entityIndexer.entityGraph.size,
                    source: 'load'
                }
            }));
            
            console.log(`Entity data loaded for ${filename}: ${this.entityIndexer.entityGraph.size} entities`);
            
        } catch (error) {
            console.error('Error loading entity data:', error);
        }
    }
    
    setupMetaMode() {
        const metaButton = document.getElementById('meta-mode-btn');
        
        metaButton.addEventListener('click', () => {
            this.toggleBlueprintMode();
        });
    }
    
    toggleBlueprintMode() {
        const body = document.body;
        const metaButton = document.getElementById('meta-mode-btn');
        const hoverPanel = document.getElementById('hover-panel');
        
        body.classList.toggle('blueprint-mode');
        metaButton.classList.toggle('active');
        
        if (body.classList.contains('blueprint-mode')) {
            this.showBlueprintContent();
            metaButton.title = 'Exit Blueprint Mode';
            this.addBlueprintModeButtons();
        } else {
            this.hideBlueprintContent();
            metaButton.title = 'Blueprint Mode';
            this.removeBlueprintModeButtons();
        }
    }
    
    addBlueprintModeButtons() {
        const hoverPanel = document.getElementById('hover-panel');
        console.log('Adding blueprint buttons, hover panel:', hoverPanel);
        
        // Remove existing blueprint buttons if any
        this.removeBlueprintModeButtons();
        
        // Create blueprint-specific buttons with clear labels
        const buttons = [
            { id: 'bp-generate-btn', text: 'Analyze', title: 'Generate Blueprint from Text', action: 'generateBlueprint' },
            { id: 'bp-generate-text-btn', text: 'Generate', title: 'Generate Text from Blueprint', action: 'generateTextFromBlueprint' }
        ];
        
        // Add buttons after the blueprint mode button
        const metaButton = document.getElementById('meta-mode-btn');
        buttons.forEach(btn => {
            const button = document.createElement('button');
            button.id = btn.id;
            button.className = 'panel-btn blueprint-btn';
            button.innerHTML = btn.text;
            button.title = btn.title;
            button.setAttribute('aria-label', btn.title);
            button.addEventListener('click', () => this[btn.action]());
            
            // Insert after meta button
            metaButton.parentNode.insertBefore(button, metaButton.nextSibling);
        });
    }
    
    removeBlueprintModeButtons() {
        // Remove all blueprint-specific buttons
        const blueprintButtons = document.querySelectorAll('.blueprint-btn');
        blueprintButtons.forEach(btn => btn.remove());
    }
    
    showBlueprintContent() {
        // Create or update blueprint content
        let blueprintContent = document.querySelector('.blueprint-content');
        if (!blueprintContent) {
            blueprintContent = document.createElement('div');
            blueprintContent.className = 'blueprint-content';
            this.editor.parentElement.appendChild(blueprintContent);
        }
        
        // Initialize blueprint if needed
        if (!this.blueprintManager) {
            // If no blueprint manager, just show a simple text version
            const title = this.titleField.value || 'Untitled Document';
            const wordCount = this.editor.textContent.split(/\s+/).filter(w => w.length > 0).length;
            
            blueprintContent.innerHTML = `
                <div class="blueprint-document-text">
                    <h1>DOCUMENT BLUEPRINT</h1>
                    <h2>${title.toUpperCase()}</h2>
                    <p><em>Words: ${wordCount} | Status: Draft | Version: 1.0</em></p>
                    
                    <h3>GLOBAL INTENT</h3>
                    <p>[ Document purpose not yet defined ]</p>
                    
                    <h3>DOCUMENT STYLE</h3>
                    <p>[ Style not yet specified ]</p>
                    
                    <h3>TARGET AUDIENCE</h3>
                    <p>[ Audience not yet identified ]</p>
                    
                    <h3>SECTIONS</h3>
                    <p>[ No sections defined - use GENERATE FROM TEXT to analyze document structure ]</p>
                    
                    <hr>
                    <p><small>Use the menu buttons above to generate blueprint from text or create text from blueprint</small></p>
                </div>
            `;
            blueprintContent.style.display = 'block';
            return;
        }
        
        if (!this.blueprintManager.currentBlueprint) {
            const title = this.titleField.value || 'Untitled Document';
            this.blueprintManager.createBlueprint(title);
        }
        
        const blueprint = this.blueprintManager.currentBlueprint;
        const wordCount = this.editor.textContent.split(/\s+/).filter(w => w.length > 0).length;
        
        // Generate blueprint as readable document text
        const blueprintText = this.generateBlueprintText(blueprint, wordCount);
        
        blueprintContent.innerHTML = `
            <div class="blueprint-document-text">
                ${blueprintText}
                
            </div>
        `;
        
        // Style display
        blueprintContent.style.display = 'block';
    }
    
    getPlainTextContent() {
        return this.editor.textContent || '';
    }
    
    generateBlueprintText(blueprint, wordCount) {
        let html = `
            <h1>DOCUMENT BLUEPRINT</h1>
            <h2>${blueprint.title.toUpperCase()}</h2>
            <p><em>Words: ${wordCount} | Status: ${blueprint.metadata.status} | Version: ${blueprint.metadata.version}</em></p>
            
            <h3>GLOBAL INTENT</h3>
            <p>${blueprint.globalIntent || '[ Document purpose not yet defined ]'}</p>
            
            <h3>DOCUMENT STYLE</h3>
            <p>${blueprint.documentStyle || '[ Style not yet specified ]'}</p>
            
            <h3>TARGET AUDIENCE</h3>
            <p>${blueprint.targetAudience || '[ Audience not yet identified ]'}</p>
            
            <h3>DOCUMENT STRUCTURE</h3>
        `;
        
        if (blueprint.sections && blueprint.sections.length > 0) {
            html += this.renderBlueprintSectionsAsText(blueprint.sections, 1);
        } else {
            html += '<p>[ No sections defined ]</p>';
        }
        
        return html;
    }
    
    renderBlueprintSectionsAsText(sections, level) {
        let html = '';
        
        sections.forEach((section, index) => {
            const numbering = level === 1 ? `${index + 1}.` : `${level}.${index + 1}`;
            const indent = '&nbsp;&nbsp;&nbsp;&nbsp;'.repeat(level - 1);
            
            html += `<p><strong>${indent}${numbering} ${section.title}</strong></p>`;
            
            if (section.intent) {
                html += `<p>${indent}&nbsp;&nbsp;&nbsp;&nbsp;<em>Intent:</em> ${section.intent}</p>`;
            }
            
            if (section.style) {
                html += `<p>${indent}&nbsp;&nbsp;&nbsp;&nbsp;<em>Style:</em> ${section.style}</p>`;
            }
            
            if (section.argumentOrder && section.argumentOrder.length > 0) {
                html += `<p>${indent}&nbsp;&nbsp;&nbsp;&nbsp;<em>Argument Order:</em> ${section.argumentOrder.join(' → ')}</p>`;
            }
            
            if (section.keyPoints && section.keyPoints.length > 0) {
                html += `<p>${indent}&nbsp;&nbsp;&nbsp;&nbsp;<em>Key Points:</em></p>`;
                section.keyPoints.forEach(point => {
                    html += `<p>${indent}&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;• ${point}</p>`;
                });
            }
            
            if (section.metadata.targetLength) {
                html += `<p>${indent}&nbsp;&nbsp;&nbsp;&nbsp;<em>Target Length:</em> ${section.metadata.targetLength}</p>`;
            }
            
            if (section.metadata.tone) {
                html += `<p>${indent}&nbsp;&nbsp;&nbsp;&nbsp;<em>Tone:</em> ${section.metadata.tone}</p>`;
            }
            
            if (section.subsections && section.subsections.length > 0) {
                html += this.renderBlueprintSectionsAsText(section.subsections, level + 1);
            }
        });
        
        return html;
    }
    
    // Note: renderBlueprintSections method removed - no longer using form-based UI
    
    hideBlueprintContent() {
        const blueprintContent = document.querySelector('.blueprint-content');
        if (blueprintContent) {
            blueprintContent.style.display = 'none';
        }
    }
    
    addBlueprintSection(parentId = null) {
        if (!this.blueprintManager) return;
        
        const section = this.blueprintManager.addSection(parentId);
        this.showBlueprintContent(); // Refresh display
    }
    
    updateSectionTitle(sectionId, title) {
        if (!this.blueprintManager) return;
        
        this.blueprintManager.updateSection(sectionId, { title });
    }
    
    updateSectionField(sectionId, field, value) {
        if (!this.blueprintManager) return;
        
        this.blueprintManager.updateSection(sectionId, { [field]: value });
    }
    
    updateArgumentOrder(sectionId, value) {
        if (!this.blueprintManager) return;
        
        const order = value.split(/[→,]/).map(s => s.trim()).filter(s => s);
        this.blueprintManager.updateSection(sectionId, { argumentOrder: order });
    }
    
    updateKeyPoints(sectionId, value) {
        if (!this.blueprintManager) return;
        
        const points = value.split('\n').map(s => s.trim()).filter(s => s);
        this.blueprintManager.updateSection(sectionId, { keyPoints: points });
    }
    
    updateSectionMetadata(sectionId, field, value) {
        if (!this.blueprintManager) return;
        
        const section = this.blueprintManager.findSection(sectionId);
        if (section) {
            section.metadata[field] = value;
            this.blueprintManager.updateModified();
        }
    }
    
    removeSection(sectionId) {
        if (!this.blueprintManager) return;
        
        if (confirm('Remove this section and all its subsections?')) {
            this.blueprintManager.removeSection(sectionId);
            this.showBlueprintContent(); // Refresh display
        }
    }
    
    toggleSectionDetails(sectionId) {
        const details = document.getElementById(`details-${sectionId}`);
        if (details) {
            details.style.display = details.style.display === 'none' ? 'block' : 'none';
            const button = details.parentElement.querySelector('.section-btn');
            if (button) {
                button.textContent = details.style.display === 'none' ? '▼' : '▲';
            }
        }
    }
    
    clearBlueprint() {
        if (!this.blueprintManager) return;
        
        if (confirm('Clear the entire blueprint? This cannot be undone.')) {
            const title = this.titleField.value || 'Untitled Document';
            this.blueprintManager.createBlueprint(title);
            this.showBlueprintContent();
        }
    }
    
    saveBlueprintToServer() {
        if (!this.blueprintManager) return;
        
        // Save blueprint to document metadata
        const docId = this.getCurrentDocumentId();
        if (!this.documentMetadata) {
            this.documentMetadata = {};
        }
        this.documentMetadata[docId] = {
            ...this.documentMetadata[docId],
            blueprint: this.blueprintManager.currentBlueprint
        };
        
        this.saveMetadata(docId, this.documentMetadata[docId]);
        this.showStatus('Blueprint saved', 2000);
    }
    
    addBlueprintFact() {
        const metadata = this.getDocumentMetadata();
        if (!metadata.requiredFacts) metadata.requiredFacts = [];
        metadata.requiredFacts.push({ claim: '[ NEW FACT ]', source: '[ SOURCE ]' });
        this.saveDocumentMetadata();
        this.showBlueprintContent();
    }
    
    async analyzeBlueprintContent() {
        const content = this.getPlainTextContent();
        const title = this.titleField.value || 'Untitled';
        
        // Show loading state
        const analyzeBtn = document.querySelector('.blueprint-analyze-btn');
        if (analyzeBtn) {
            analyzeBtn.textContent = '⏳ ANALYZING...';
            analyzeBtn.disabled = true;
        }
        
        try {
            // Use AI to analyze the content
            const prompt = `Analyze this document and extract:
1. Current document structure (main sections, organization)
2. Detected purpose (what the document is trying to achieve)
3. Key points made (list the main arguments or information presented)
4. Narrative flow (how the story/information unfolds)

Document Title: ${title}
Content: ${content.substring(0, 3000)}${content.length > 3000 ? '...' : ''}

Return as JSON with keys: currentStructure, detectedPurpose, keyPoints (array), narrativeFlow`;
            
            const response = await fetch('/api/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    command: prompt,
                    context: { 
                        content: content,
                        isBlueprintAnalysis: true 
                    }
                })
            });
            
            if (response.ok) {
                // Parse the streaming response
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.substring(6);
                            if (data && data !== '[DONE]') {
                                try {
                                    const parsed = JSON.parse(data);
                                    if (parsed.choices && parsed.choices[0] && parsed.choices[0].delta && parsed.choices[0].delta.content) {
                                        fullResponse += parsed.choices[0].delta.content;
                                    }
                                } catch (e) {
                                    fullResponse += data;
                                }
                            }
                        }
                    }
                }
                
                // Parse the analysis
                let analysis;
                try {
                    const jsonMatch = fullResponse.match(/\{[\s\S]*\}/);
                    if (jsonMatch) {
                        analysis = JSON.parse(jsonMatch[0]);
                    }
                } catch (e) {
                    console.error('Failed to parse analysis:', e);
                    analysis = {
                        currentStructure: 'Analysis failed - could not parse response',
                        detectedPurpose: 'Analysis failed - could not parse response',
                        keyPoints: [],
                        narrativeFlow: 'Analysis failed - could not parse response'
                    };
                }
                
                // Update metadata
                const metadata = this.getDocumentMetadata();
                metadata.currentStructure = analysis.currentStructure;
                metadata.detectedPurpose = analysis.detectedPurpose;
                metadata.keyPoints = analysis.keyPoints || [];
                metadata.narrativeFlow = analysis.narrativeFlow;
                metadata.lastAnalyzed = new Date().toISOString();
                
                // Generate gap analysis if we have intended state
                if (metadata.intendedStructure || metadata.intendedPurpose) {
                    metadata.gapAnalysis = this.generateGapAnalysis(metadata);
                }
                
                this.saveDocumentMetadata();
                this.showBlueprintContent();
            }
        } catch (error) {
            console.error('Blueprint analysis error:', error);
            this.showStatus('Analysis failed', 3000);
        } finally {
            if (analyzeBtn) {
                analyzeBtn.textContent = '⚡ ANALYZE CONTENT';
                analyzeBtn.disabled = false;
            }
        }
    }
    
    async generateBlueprint() {
        if (!this.blueprintManager) {
            this.showStatus('Blueprint system not ready', 2000);
            return;
        }
        
        const content = this.getPlainTextContent();
        const title = this.titleField.value || 'Untitled';
        
        // Show loading state
        const generateBtn = document.querySelector('.blueprint-generate-btn');
        if (generateBtn) {
            generateBtn.textContent = '⏳ ANALYZING TEXT...';
            generateBtn.disabled = true;
        }
        
        try {
            this.showStatus('Analyzing document structure...', 0);
            
            // First, generate basic structure from text
            const blueprint = this.blueprintManager.generateFromText(content, title);
            
            // Now enhance with AI analysis
            const prompt = `Analyze this document and generate a comprehensive blueprint structure.

Document Title: ${title}
Content: ${content.substring(0, 5000)}${content.length > 5000 ? '...' : ''}

Provide a detailed analysis in JSON format with:
{
  "globalIntent": "The overall purpose and goal of this document",
  "documentStyle": "The writing style (e.g., academic, business, creative)",
  "targetAudience": "Who this document is written for",
  "sections": [
    {
      "title": "Section title",
      "intent": "What this section aims to achieve",
      "style": "Writing style for this section",
      "argumentOrder": ["point1", "point2", "point3"],
      "keyPoints": ["Main idea 1", "Main idea 2"],
      "metadata": {
        "targetLength": "300-500 words",
        "tone": "formal/informal/etc",
        "notes": "Any special considerations"
      }
    }
  ]
}

Analyze the existing structure and provide intent, style, and metadata for each section.`;
            
            const response = await fetch('/api/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    command: prompt,
                    context: { 
                        content: content,
                        isBlueprintGeneration: true 
                    }
                })
            });
            
            if (response.ok) {
                // Parse the streaming response
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let fullResponse = '';
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunk = decoder.decode(value);
                    const lines = chunk.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const data = line.substring(6);
                            if (data && data !== '[DONE]') {
                                try {
                                    const parsed = JSON.parse(data);
                                    if (parsed.choices && parsed.choices[0] && parsed.choices[0].delta && parsed.choices[0].delta.content) {
                                        fullResponse += parsed.choices[0].delta.content;
                                    }
                                } catch (e) {
                                    fullResponse += data;
                                }
                            }
                        }
                    }
                }
                
                // Parse the AI analysis
                let aiAnalysis;
                try {
                    const jsonMatch = fullResponse.match(/\{[\s\S]*\}/);
                    if (jsonMatch) {
                        aiAnalysis = JSON.parse(jsonMatch[0]);
                    }
                } catch (e) {
                    console.error('Failed to parse AI analysis:', e);
                    this.showStatus('Failed to parse AI response', 3000);
                    return;
                }
                
                // Merge AI analysis with generated blueprint
                if (aiAnalysis) {
                    this.blueprintManager.currentBlueprint.globalIntent = aiAnalysis.globalIntent || '';
                    this.blueprintManager.currentBlueprint.documentStyle = aiAnalysis.documentStyle || '';
                    this.blueprintManager.currentBlueprint.targetAudience = aiAnalysis.targetAudience || '';
                    
                    // Update sections with AI insights
                    if (aiAnalysis.sections && Array.isArray(aiAnalysis.sections)) {
                        aiAnalysis.sections.forEach((aiSection, index) => {
                            if (this.blueprintManager.currentBlueprint.sections[index]) {
                                const section = this.blueprintManager.currentBlueprint.sections[index];
                                Object.assign(section, {
                                    intent: aiSection.intent || section.intent,
                                    style: aiSection.style || section.style,
                                    argumentOrder: aiSection.argumentOrder || section.argumentOrder,
                                    keyPoints: aiSection.keyPoints || section.keyPoints
                                });
                                Object.assign(section.metadata, aiSection.metadata || {});
                            }
                        });
                    }
                    
                    this.blueprintManager.updateModified();
                }
                
                // Save blueprint to document metadata
                this.saveBlueprintToServer();
                
                // Refresh blueprint display
                this.showBlueprintContent();
                
                this.showStatus('Blueprint generated successfully', 3000);
            }
        } catch (error) {
            console.error('Blueprint generation error:', error);
            this.showStatus('Failed to generate blueprint', 3000);
        } finally {
            if (generateBtn) {
                generateBtn.textContent = '🔧 AUTO-GENERATE BLUEPRINT';
                generateBtn.disabled = false;
            }
        }
    }
    
    async generateTextFromBlueprint() {
        console.log('generateTextFromBlueprint called');
        console.log('blueprintManager:', this.blueprintManager);
        console.log('currentBlueprint:', this.blueprintManager?.currentBlueprint);
        
        if (!this.blueprintManager) {
            this.showStatus('Blueprint manager not initialized', 2000);
            console.error('BlueprintManager not found');
            return;
        }
        
        if (!this.blueprintManager.currentBlueprint) {
            // Try to create a default blueprint from current content
            const title = this.titleField.value || 'Untitled Document';
            const content = this.getPlainTextContent();
            this.blueprintManager.createBlueprint(title);
            
            // If there's content, generate blueprint from it first
            if (content.trim()) {
                await this.generateBlueprint();
                return; // generateBlueprint will call generateTextFromBlueprint again
            }
        }
        
        const generateBtn = document.getElementById('bp-generate-text-btn');
        if (generateBtn) {
            generateBtn.textContent = '⏳ GENERATING TEXT...';
            generateBtn.disabled = true;
        }
        
        try {
            this.showStatus('Generating text from blueprint with Claude Opus 4...', 0);
            
            const blueprintPrompt = this.blueprintManager.toBlueprintPrompt();
            console.log('Blueprint prompt:', blueprintPrompt);
            
            const response = await fetch('/api/blueprint-to-text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    blueprint: this.blueprintManager.currentBlueprint,
                    prompt: blueprintPrompt,
                    useExtendedThinking: true
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                
                if (result.success && result.content) {
                    // Exit blueprint mode
                    this.toggleBlueprintMode();
                    
                    // Clear editor and parse the generated content
                    this.editor.innerHTML = '';
                    
                    // Split content into paragraphs and add to editor
                    const lines = result.content.split('\n');
                    let currentParagraph = '';
                    
                    for (const line of lines) {
                        const trimmedLine = line.trim();
                        
                        if (trimmedLine === '') {
                            if (currentParagraph) {
                                const p = document.createElement('p');
                                p.textContent = currentParagraph;
                                this.editor.appendChild(p);
                                currentParagraph = '';
                            }
                        } else if (trimmedLine.startsWith('#')) {
                            if (currentParagraph) {
                                const p = document.createElement('p');
                                p.textContent = currentParagraph;
                                this.editor.appendChild(p);
                                currentParagraph = '';
                            }
                            
                            const level = trimmedLine.match(/^#+/)[0].length;
                            const text = trimmedLine.replace(/^#+\s*/, '');
                            const heading = document.createElement(`h${Math.min(level, 6)}`);
                            heading.textContent = text;
                            this.editor.appendChild(heading);
                        } else {
                            currentParagraph = currentParagraph ? currentParagraph + ' ' + trimmedLine : trimmedLine;
                        }
                    }
                    
                    // Add any remaining paragraph
                    if (currentParagraph) {
                        const p = document.createElement('p');
                        p.textContent = currentParagraph;
                        this.editor.appendChild(p);
                    }
                    
                    this.lastKnownGoodState = this.editor.innerHTML;
                    
                    // Update word count
                    this.updateWordCount();
                    
                    // Save the document
                    this.saveDocument();
                    
                    // Check for pagination
                    setTimeout(() => {
                        this.checkForPageBreak();
                    }, 100);
                    
                    this.showStatus('Text generated successfully from blueprint', 3000);
                    
                    // Show thinking process if available
                    if (result.thinking) {
                        console.log('Claude Opus 4 thinking process:', result.thinking);
                    }
                } else {
                    console.error('Generation failed:', result);
                    this.showStatus('Failed to generate text: ' + (result.error || 'Unknown error'), 3000);
                }
            } else {
                console.error('Server response:', response.status, response.statusText);
                const errorText = await response.text();
                console.error('Error details:', errorText);
                this.showStatus(`Server error: ${response.status}`, 3000);
            }
        } catch (error) {
            console.error('Text generation error:', error);
            this.showStatus('Failed to generate text from blueprint', 3000);
        } finally {
            if (generateBtn) {
                generateBtn.textContent = '⚡ GENERATE TEXT';
                generateBtn.disabled = false;
            }
        }
    }
    
    generateGapAnalysis(metadata) {
        const gaps = [];
        
        if (metadata.intendedStructure && metadata.currentStructure) {
            if (metadata.intendedStructure !== metadata.currentStructure) {
                gaps.push(`STRUCTURE: Document structure differs from intended design`);
            }
        }
        
        if (metadata.intendedPurpose && metadata.detectedPurpose) {
            if (!metadata.detectedPurpose.includes(metadata.intendedPurpose)) {
                gaps.push(`PURPOSE: Current purpose may not align with intended goal`);
            }
        }
        
        if (metadata.requiredFacts && metadata.requiredFacts.length > 0) {
            const missingFacts = metadata.requiredFacts.filter(fact => 
                !metadata.keyPoints.some(point => point.includes(fact.claim))
            );
            if (missingFacts.length > 0) {
                gaps.push(`FACTS: ${missingFacts.length} required facts may be missing`);
            }
        }
        
        if (metadata.desiredTone && metadata.narrativeFlow) {
            gaps.push(`TONE: Review if narrative matches desired tone`);
        }
        
        return gaps.length > 0 ? gaps.join('\n\n') : 'Document appears aligned with intended blueprint';
    }
    
    exportBlueprint() {
        if (!this.blueprintManager || !this.blueprintManager.currentBlueprint) {
            this.showStatus('No blueprint to export', 2000);
            return;
        }
        
        const blueprintJson = this.blueprintManager.exportBlueprint();
        const title = this.blueprintManager.currentBlueprint.title || 'untitled';
        
        const blob = new Blob([blueprintJson], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${title.replace(/[^a-z0-9]/gi, '_')}_blueprint.json`;
        a.click();
        URL.revokeObjectURL(url);
        
        this.showStatus('Blueprint exported', 2000);
    }
    
    importBlueprint() {
        if (!this.blueprintManager) {
            this.showStatus('Blueprint system not ready', 2000);
            return;
        }
        
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json';
        
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            try {
                const text = await file.text();
                if (this.blueprintManager.importBlueprint(text)) {
                    this.showBlueprintContent();
                    this.showStatus('Blueprint imported successfully', 2000);
                } else {
                    this.showStatus('Failed to import blueprint', 3000);
                }
            } catch (error) {
                console.error('Import error:', error);
                this.showStatus('Error importing blueprint', 3000);
            }
        };
        
        input.click();
    }
    
    async syncBlueprints() {
        // Save all blueprints to server for Claude access
        try {
            const response = await fetch('/api/save-metadata', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: '.edith/metadata/blueprints.json',
                    metadata: this.documentMetadata || {}
                })
            });
            
            if (response.ok) {
                this.showStatus('Blueprints synced for Claude access', 2000);
            }
        } catch (error) {
            console.error('Sync error:', error);
            this.showStatus('Sync failed', 2000);
        }
    }
    
    getDocumentMetadata() {
        // Get metadata for current document
        const docId = this.getCurrentDocumentId();
        return this.documentMetadata?.[docId] || {
            structure: '',
            intent: '',
            facts: [],
            tone: ''
        };
    }
    
    saveDocumentMetadata() {
        // Save edited metadata
        const metaContent = document.querySelector('.meta-content');
        if (!metaContent) return;
        
        const docId = this.getCurrentDocumentId();
        const metadata = {
            structure: metaContent.querySelector('[data-field="structure"]')?.textContent || '',
            intent: metaContent.querySelector('[data-field="intent"]')?.textContent || '',
            facts: Array.from(metaContent.querySelectorAll('.fact-item')).map(item => ({
                claim: item.querySelector('.fact-claim')?.textContent || '',
                source: item.querySelector('.fact-source')?.textContent || ''
            })),
            tone: metaContent.querySelector('[data-field="tone"]')?.textContent || ''
        };
        
        if (!this.documentMetadata) {
            this.documentMetadata = {};
        }
        
        this.documentMetadata[docId] = metadata;
        
        // Save to storage
        this.saveMetadata(docId, metadata);
    }
    
    getCurrentDocumentId() {
        return this.titleField.value.replace(/[^a-z0-9]/gi, '_').toLowerCase() || 'untitled';
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the editor when DOM is ready
// Nuclear reset function
window.resetEditor = function() {
    const editor = document.getElementById('editor');
    if (!editor) {
        console.error('No editor found');
        return;
    }
    
    // Remove all potential blocking classes
    editor.classList.remove('preview-mode');
    document.body.classList.remove('blueprint-mode');
    
    // Force contenteditable
    editor.contentEditable = true;
    editor.setAttribute('contenteditable', 'true');
    
    // Reset all inline styles that could block editing
    editor.style.pointerEvents = 'auto';
    editor.style.userSelect = 'text';
    editor.style.webkitUserSelect = 'text';
    editor.style.mozUserSelect = 'text';
    editor.style.msUserSelect = 'text';
    editor.style.cursor = 'text';
    editor.style.display = 'block';
    editor.style.visibility = 'visible';
    editor.style.opacity = '1';
    
    // Clear any potential readonly or disabled attributes
    editor.removeAttribute('readonly');
    editor.removeAttribute('disabled');
    
    // Focus the editor
    editor.focus();
    
    console.log('Editor reset complete');
    console.log('ContentEditable:', editor.contentEditable);
    console.log('Is focused:', document.activeElement === editor);
    
    // Test typing
    try {
        document.execCommand('insertText', false, 'Can you type now? ');
        console.log('Test text inserted successfully');
    } catch (e) {
        console.error('Could not insert test text:', e);
    }
    
    return editor;
};

// Force clean all pages
window.forceCleanPages = function() {
    const container = document.getElementById('editor-container');
    const allPages = container.querySelectorAll('.page-wrapper');
    
    console.log(`Force cleaning ${allPages.length} pages...`);
    
    // Keep only the first page
    allPages.forEach((page, index) => {
        if (index > 0) {
            console.log(`Removing page at index ${index}`);
            page.remove();
        }
    });
    
    // Clear the app's page tracking
    if (window.edithApp) {
        window.edithApp.pages.clear();
        window.edithApp.currentPage = 1;
        const firstPage = container.querySelector('.page-wrapper');
        if (firstPage) {
            window.edithApp.pages.set(1, firstPage);
            // Ensure it has the right data-page attribute
            firstPage.setAttribute('data-page', '1');
        }
    }
    
    console.log('Force clean complete');
    window.debugPages();
};

// Debug pagination
window.debugPages = function() {
    const container = document.getElementById('editor-container');
    const allPages = container.querySelectorAll('.page-wrapper');
    console.log('=== PAGE DEBUG ===');
    console.log(`Total pages in DOM: ${allPages.length}`);
    
    allPages.forEach((page, index) => {
        const pageNum = page.getAttribute('data-page') || 'NO-DATA-PAGE';
        const editor = page.querySelector('.editor-content');
        const content = editor ? editor.textContent.substring(0, 50) + '...' : 'NO EDITOR';
        console.log(`Page ${index + 1}: data-page="${pageNum}", content="${content}"`);
    });
    
    if (window.edithApp) {
        console.log(`Pages Map size: ${window.edithApp.pages.size}`);
        console.log(`Current page: ${window.edithApp.currentPage}`);
    }
    
    return allPages;
};

// EMERGENCY RECOVERY
window.recoverContent = function() {
    const container = document.getElementById('editor-container');
    const allPages = container.querySelectorAll('.page-wrapper');
    
    console.log('=== RECOVERY ATTEMPT ===');
    console.log(`Found ${allPages.length} pages`);
    
    let allContent = [];
    
    // Collect content from ALL pages
    allPages.forEach((page, index) => {
        const editor = page.querySelector('.editor-content');
        if (editor && editor.children.length > 0) {
            console.log(`Page ${index + 1} has ${editor.children.length} elements`);
            allContent.push(...Array.from(editor.children));
        }
    });
    
    if (allContent.length > 0) {
        console.log(`Recovered ${allContent.length} total elements`);
        
        // Put everything back in page 1
        const firstEditor = document.getElementById('editor');
        if (firstEditor) {
            firstEditor.innerHTML = '';
            allContent.forEach(el => {
                firstEditor.appendChild(el);
            });
            console.log('Content restored to page 1');
        }
    } else {
        console.log('No content found to recover');
        
        // Check undo stack
        if (window.edithApp && window.edithApp.undoStack.length > 0) {
            console.log(`Undo stack has ${window.edithApp.undoStack.length} items`);
            console.log('Try pressing Ctrl+Z or Cmd+Z');
        }
    }
};

// Global test function for debugging
window.testEditor = function() {
    const editor = document.getElementById('editor');
    if (!editor) {
        console.error('No editor found');
        return;
    }
    
    console.log('Testing editor...');
    console.log('1. Element:', editor);
    console.log('2. ContentEditable:', editor.contentEditable);
    console.log('3. IsContentEditable:', editor.isContentEditable);
    console.log('4. Current content:', editor.textContent);
    
    // Try to focus
    editor.focus();
    console.log('5. Document activeElement:', document.activeElement === editor ? 'Editor is focused' : 'Editor NOT focused');
    
    // Try to insert text using execCommand
    try {
        document.execCommand('insertText', false, 'TEST');
        console.log('6. execCommand result: Success');
    } catch (e) {
        console.log('6. execCommand failed:', e);
    }
    
    // Check for overlapping elements
    const rect = editor.getBoundingClientRect();
    const elementAtCenter = document.elementFromPoint(rect.left + rect.width/2, rect.top + rect.height/2);
    console.log('7. Element at center:', elementAtCenter === editor ? 'Editor' : elementAtCenter);
    
    return editor;
};

document.addEventListener('DOMContentLoaded', () => {
    window.edithApp = new MarkdownEditor();
    
    // Initialize BlueprintManager when module is loaded
    const checkBlueprintManager = setInterval(() => {
        if (window.BlueprintManager) {
            window.edithApp.blueprintManager = new window.BlueprintManager();
            clearInterval(checkBlueprintManager);
        }
    }, 100);
    
    // Diagnostic: Check if editor is working
    setTimeout(() => {
        const editor = document.getElementById('editor');
        if (editor) {
            console.log('Editor diagnostics:');
            console.log('- Element found:', editor);
            console.log('- ContentEditable:', editor.contentEditable);
            console.log('- IsContentEditable:', editor.isContentEditable);
            console.log('- Has event listeners:', window.edithApp && window.edithApp.editor === editor);
            
            // Force enable contenteditable if needed
            if (editor.contentEditable !== 'true') {
                console.warn('Editor contenteditable was not true, fixing...');
                editor.contentEditable = 'true';
            }
            
            // Check if blueprint mode is hiding the editor
            if (document.body.classList.contains('blueprint-mode')) {
                console.warn('Blueprint mode is active, might be hiding editor');
                // Ensure editor is visible for debugging
                editor.style.display = 'block';
                editor.style.visibility = 'visible';
                editor.style.opacity = '1';
            }
            
            // Check and remove preview mode if active
            if (editor.classList.contains('preview-mode')) {
                console.warn('Preview mode was active, removing...');
                editor.classList.remove('preview-mode');
            }
            
            // Test if we can programmatically add content
            try {
                const testContent = editor.textContent;
                editor.textContent = testContent + ' [test]';
                if (editor.textContent.includes('[test]')) {
                    console.log('✓ Can modify editor content programmatically');
                    editor.textContent = testContent; // Remove test
                } else {
                    console.error('✗ Cannot modify editor content');
                }
            } catch (e) {
                console.error('Error testing editor:', e);
            }
            
            // Check for any event listeners that might block input
            // Note: getEventListeners only works in Chrome DevTools console, not in scripts
            console.log('Note: Run getEventListeners(document.getElementById("editor")) in console to see listeners');
            
            // Check computed styles
            const styles = window.getComputedStyle(editor);
            console.log('Editor computed styles:');
            console.log('- user-select:', styles.userSelect);
            console.log('- pointer-events:', styles.pointerEvents);
            console.log('- -webkit-user-modify:', styles.webkitUserModify);
            
            // Force fix any CSS issues
            if (styles.pointerEvents === 'none') {
                console.warn('Fixing pointer-events: none');
                editor.style.pointerEvents = 'auto';
            }
            if (styles.userSelect === 'none') {
                console.warn('Fixing user-select: none');
                editor.style.userSelect = 'text';
            }
            
            // Make absolutely sure editor is editable
            editor.setAttribute('contenteditable', 'true');
            editor.style.cursor = 'text';
            
            // Try to set focus one more time
            setTimeout(() => {
                editor.focus();
                console.log('Final focus attempt - Active element:', document.activeElement === editor ? 'Success' : 'Failed');
            }, 500);
        } else {
            console.error('Editor element not found!');
        }
    }, 1000);
});