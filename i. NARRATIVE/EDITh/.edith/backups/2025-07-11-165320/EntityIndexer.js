import { ArgumentExtractor } from './ArgumentExtractor.js';

export class EntityIndexer {
    constructor(app) {
        this.app = app;
        this.entityGraph = new Map(); // entityId -> EntityNode
        this.mentionIndex = new Map(); // entityId -> [mentions]
        this.typeIndex = new Map(); // type -> Set(entityIds)
        this.lastIndexTime = 0;
        this.indexVersion = 0;
        this.isIndexing = false;
        
        // Initialize argument extractor
        this.argumentExtractor = new ArgumentExtractor(
            this.app.unitManager, 
            this.app.modelScheduler
        );
        
        this.settings = {
            lightPassInterval: 2000, // 2 seconds after typing stops
            heavyPassInterval: 90000, // 90 seconds idle
            escalationThreshold: 5000, // tokens to trigger Mini
            maxTokensPerBatch: 250,
            entityTypes: {
                light: ['person', 'organization', 'phone', 'email', 'url'],
                heavy: ['footnote', 'heading', 'date', 'custom'],
                argument: ['claim', 'evidence', 'warrant', 'objection', 'rebuttal', 'qualifier']
            }
        };
        
        this.setupEventListeners();
        this.schedulePeriodicIndexing();
    }
    
    setupEventListeners() {
        const mainEditor = document.getElementById('main-text-editor');
        
        if (mainEditor) {
            // Light pass on typing pause
            let typingTimer;
            mainEditor.addEventListener('input', () => {
                clearTimeout(typingTimer);
                typingTimer = setTimeout(() => {
                    this.scheduleLightPass();
                }, this.settings.lightPassInterval);
            });
            
            // Heavy pass on significant events
            document.addEventListener('keydown', (e) => {
                if (e.ctrlKey && e.key === 'i') {
                    e.preventDefault();
                    this.scheduleHeavyPass();
                }
            });
        }
    }
    
    async scheduleLightPass() {
        if (this.isIndexing) return;
        
        const editor = document.getElementById('main-text-editor');
        if (!editor) return;
        
        const text = editor.value;
        const recentSpan = this.getRecentSpan(text, this.settings.maxTokensPerBatch);
        
        if (recentSpan.length > 10) {
            await this.performLightPass(recentSpan);
        }
    }
    
    async scheduleHeavyPass() {
        if (this.isIndexing) return;
        
        const editor = document.getElementById('main-text-editor');
        if (!editor) return;
        
        const text = editor.value;
        await this.performHeavyPass(text);
    }
    
    getRecentSpan(text, maxTokens) {
        // Get the last paragraph or a reasonable chunk
        const paragraphs = text.split('\n\n');
        const lastParagraph = paragraphs[paragraphs.length - 1];
        
        // Estimate tokens and truncate if needed
        const estimatedTokens = Math.ceil(lastParagraph.length / 4);
        if (estimatedTokens <= maxTokens) {
            return lastParagraph;
        }
        
        // Take the last N characters that fit in token limit
        const maxChars = maxTokens * 4;
        return lastParagraph.slice(-maxChars);
    }
    
    async performLightPass(text) {
        this.isIndexing = true;
        
        try {
            const entities = await this.extractEntitiesLight(text);
            this.updateEntityGraph(entities, 'light');
            
            // Notify UI of index update
            this.notifyIndexUpdate();
            
        } catch (error) {
            console.error('Light pass error:', error);
        } finally {
            this.isIndexing = false;
        }
    }
    
    async performHeavyPass(text) {
        this.isIndexing = true;
        
        try {
            const model = this.selectHeavyPassModel(text);
            const entities = await this.extractEntitiesHeavy(text, model);
            this.updateEntityGraph(entities, 'heavy');
            
            // Extract arguments if this is from the main editor
            const mainEditor = document.getElementById('main-text-editor');
            if (mainEditor && mainEditor.value === text) {
                await this.extractAndIndexArguments();
            }
            
            // Full reindex
            this.indexVersion++;
            this.lastIndexTime = Date.now();
            
            this.notifyIndexUpdate();
            
        } catch (error) {
            console.error('Heavy pass error:', error);
        } finally {
            this.isIndexing = false;
        }
    }
    
    selectHeavyPassModel(text) {
        const tokenCount = Math.ceil(text.length / 4);
        
        if (tokenCount > this.settings.escalationThreshold) {
            return 'mini'; // Or 'o3' for very complex documents
        }
        
        return 'nano';
    }
    
    async extractEntitiesLight(text) {
        const systemPrompt = `Extract entities from text. Return JSON array:
[{"type": "person|organization|phone|email|url", "text": "entity text", "offset": number}]

Focus on clear, unambiguous entities. Be conservative.`;
        
        try {
            const response = await this.callEntityAPI(systemPrompt, text, 'nano');
            return this.parseEntityResponse(response, text);
            
        } catch (error) {
            console.error('Light entity extraction error:', error);
            return [];
        }
    }
    
    async extractEntitiesHeavy(text, model) {
        const systemPrompt = `Extract comprehensive entities from text. Return JSON array:
[{"type": "person|organization|phone|email|url|footnote|heading|date|location|custom", "text": "entity text", "offset": number, "metadata": {}}]

Include:
- All people, organizations, contact info
- Headings and structural elements  
- Dates and temporal references
- Footnote markers and references
- Domain-specific entities

Provide rich metadata where applicable.`;
        
        try {
            const response = await this.callEntityAPI(systemPrompt, text, model);
            return this.parseEntityResponse(response, text);
            
        } catch (error) {
            console.error('Heavy entity extraction error:', error);
            return [];
        }
    }
    
    async callEntityAPI(systemPrompt, text, model) {
        // Use the new entity extraction service
        const response = await fetch('/api/extract-entities', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                content: text
            })
        });
        
        if (!response.ok) {
            throw new Error(`Entity API error: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || 'Entity extraction failed');
        }
        
        // Convert the response format to match expected format
        const entities = [];
        if (data.entities) {
            data.entities.forEach(entity => {
                entities.push({
                    type: entity.type,
                    text: entity.name,
                    offset: entity.positions?.[0] || 0,
                    metadata: {
                        mentions: entity.mentions,
                        context: entity.context,
                        confidence: entity.confidence
                    }
                });
            });
        }
        
        return JSON.stringify(entities);
    }
    
    getModelEndpoint(model) {
        switch (model) {
            case 'nano': return 'gpt-4.1-nano';
            case 'mini': return 'gpt-4.1-mini';
            case 'o3': return 'o3-mini';
            default: return 'gpt-4.1-nano';
        }
    }
    
    parseEntityResponse(response, originalText) {
        try {
            // Response is already a JSON string of entities array
            const entities = JSON.parse(response);
            
            // Validate and normalize entities
            return entities
                .filter(entity => this.validateEntity(entity, originalText))
                .map(entity => this.normalizeEntity(entity));
            
        } catch (error) {
            console.error('Failed to parse entity response:', error);
            return [];
        }
    }
    
    validateEntity(entity, originalText) {
        // Basic validation
        if (!entity.type || !entity.text || typeof entity.offset !== 'number') {
            return false;
        }
        
        // Check if offset is reasonable
        if (entity.offset < 0 || entity.offset >= originalText.length) {
            return false;
        }
        
        // Verify text matches at offset
        const extractedText = originalText.substr(entity.offset, entity.text.length);
        const similarity = this.calculateStringSimilarity(entity.text, extractedText);
        
        return similarity > 0.8; // 80% similarity threshold
    }
    
    calculateStringSimilarity(str1, str2) {
        const longer = str1.length > str2.length ? str1 : str2;
        const shorter = str1.length > str2.length ? str2 : str1;
        
        if (longer.length === 0) return 1.0;
        
        const distance = this.levenshteinDistance(longer, shorter);
        return (longer.length - distance) / longer.length;
    }
    
    levenshteinDistance(str1, str2) {
        const matrix = [];
        
        for (let i = 0; i <= str2.length; i++) {
            matrix[i] = [i];
        }
        
        for (let j = 0; j <= str1.length; j++) {
            matrix[0][j] = j;
        }
        
        for (let i = 1; i <= str2.length; i++) {
            for (let j = 1; j <= str1.length; j++) {
                if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
                    matrix[i][j] = matrix[i - 1][j - 1];
                } else {
                    matrix[i][j] = Math.min(
                        matrix[i - 1][j - 1] + 1,
                        matrix[i][j - 1] + 1,
                        matrix[i - 1][j] + 1
                    );
                }
            }
        }
        
        return matrix[str2.length][str1.length];
    }
    
    normalizeEntity(entity) {
        return {
            id: this.generateEntityId(entity),
            type: entity.type.toLowerCase(),
            text: entity.text.trim(),
            offset: entity.offset,
            metadata: entity.metadata || {},
            mentions: entity.metadata?.mentions || 1,
            context: entity.metadata?.context || '',
            confidence: entity.metadata?.confidence || 0.9,
            firstSeen: Date.now(),
            lastSeen: Date.now()
        };
    }
    
    generateEntityId(entity) {
        // Create deterministic ID based on type and normalized text
        const normalizedText = entity.text.toLowerCase().trim();
        const hash = this.simpleHash(entity.type + '::' + normalizedText);
        return `${entity.type}_${hash}`;
    }
    
    simpleHash(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32-bit integer
        }
        return Math.abs(hash).toString(36);
    }
    
    updateEntityGraph(entities, passType) {
        for (const entity of entities) {
            const existingEntity = this.entityGraph.get(entity.id);
            
            if (existingEntity) {
                // Update existing entity
                existingEntity.mentions++;
                existingEntity.lastSeen = Date.now();
                
                // Add new mention
                this.addMention(entity.id, entity.offset);
                
            } else {
                // Add new entity
                this.entityGraph.set(entity.id, entity);
                this.addToTypeIndex(entity.type, entity.id);
                this.addMention(entity.id, entity.offset);
            }
        }
        
        // Update index metadata
        this.lastIndexTime = Date.now();
    }
    
    addMention(entityId, offset) {
        if (!this.mentionIndex.has(entityId)) {
            this.mentionIndex.set(entityId, []);
        }
        
        const mentions = this.mentionIndex.get(entityId);
        
        // Avoid duplicate mentions at same offset
        if (!mentions.some(mention => Math.abs(mention.offset - offset) < 5)) {
            mentions.push({
                offset: offset,
                timestamp: Date.now()
            });
        }
    }
    
    addToTypeIndex(type, entityId) {
        if (!this.typeIndex.has(type)) {
            this.typeIndex.set(type, new Set());
        }
        
        this.typeIndex.get(type).add(entityId);
    }
    
    notifyIndexUpdate() {
        // Notify UI components of index changes
        if (this.app.leftRail) {
            this.app.leftRail.updateEntityTree();
        }
        
        // Dispatch custom event
        document.dispatchEvent(new CustomEvent('entityIndexUpdated', {
            detail: {
                version: this.indexVersion,
                entityCount: this.entityGraph.size,
                timestamp: this.lastIndexTime
            }
        }));
    }
    
    schedulePeriodicIndexing() {
        // Heavy pass every 90 seconds when idle
        setInterval(() => {
            const timeSinceLastEdit = Date.now() - this.lastIndexTime;
            
            if (timeSinceLastEdit > this.settings.heavyPassInterval && !this.isIndexing) {
                this.scheduleHeavyPass();
            }
        }, this.settings.heavyPassInterval);
    }
    
    async extractAndIndexArguments() {
        try {
            // Extract arguments from all units in the document
            const argumentThreads = await this.argumentExtractor.extractFromDocument();
            
            // Convert argument threads to entity-like structures for indexing
            for (const thread of argumentThreads) {
                const argumentEntity = {
                    id: thread.id,
                    type: `argument-${thread.type}`,
                    text: thread.text,
                    metadata: {
                        keywords: thread.keywords || [],
                        instances: thread.instances,
                        totalStrength: thread.totalStrength,
                        evolution: thread.evolution || []
                    },
                    mentions: thread.instances.length,
                    lastSeen: Date.now(),
                    isArgument: true
                };
                
                // Add to entity graph
                this.entityGraph.set(thread.id, argumentEntity);
                
                // Add to type index
                const argumentType = `argument-${thread.type}`;
                if (!this.typeIndex.has(argumentType)) {
                    this.typeIndex.set(argumentType, new Set());
                }
                this.typeIndex.get(argumentType).add(thread.id);
                
                // Create mention entries for each instance
                const mentions = thread.instances.map(instance => ({
                    unitId: instance.unitId,
                    unitTitle: instance.unitTitle,
                    positions: instance.positions,
                    confidence: instance.confidence,
                    timestamp: Date.now()
                }));
                
                this.mentionIndex.set(thread.id, mentions);
            }
            
            console.log(`Indexed ${argumentThreads.length} argument threads`);
            
        } catch (error) {
            console.error('Argument extraction and indexing failed:', error);
        }
    }

    // Public API methods
    
    getEntitiesByType(type) {
        const entityIds = this.typeIndex.get(type) || new Set();
        return Array.from(entityIds).map(id => this.entityGraph.get(id));
    }
    
    getArgumentsByType(argumentType) {
        return this.getEntitiesByType(`argument-${argumentType}`);
    }
    
    getAllArguments() {
        const argumentEntities = [];
        for (const [type, entityIds] of this.typeIndex.entries()) {
            if (type.startsWith('argument-')) {
                const entities = Array.from(entityIds).map(id => this.entityGraph.get(id));
                argumentEntities.push(...entities);
            }
        }
        return argumentEntities;
    }
    
    getEntityById(entityId) {
        return this.entityGraph.get(entityId);
    }
    
    getMentions(entityId) {
        return this.mentionIndex.get(entityId) || [];
    }
    
    searchEntities(query) {
        const results = [];
        const lowerQuery = query.toLowerCase();
        
        for (const [id, entity] of this.entityGraph) {
            if (entity.text.toLowerCase().includes(lowerQuery)) {
                results.push({
                    ...entity,
                    relevance: this.calculateRelevance(entity, query)
                });
            }
        }
        
        return results.sort((a, b) => b.relevance - a.relevance);
    }
    
    calculateRelevance(entity, query) {
        const textMatch = entity.text.toLowerCase().includes(query.toLowerCase()) ? 1 : 0;
        const mentionWeight = Math.log(entity.mentions + 1) / 10;
        const recentWeight = (Date.now() - entity.lastSeen) < 60000 ? 0.2 : 0;
        
        return textMatch + mentionWeight + recentWeight;
    }
    
    getEntityTree() {
        const tree = {};
        
        for (const [type, entityIds] of this.typeIndex) {
            tree[type] = {
                count: entityIds.size,
                entities: Array.from(entityIds)
                    .map(id => this.entityGraph.get(id))
                    .sort((a, b) => b.mentions - a.mentions)
            };
        }
        
        return tree;
    }
    
    getIndexStats() {
        return {
            totalEntities: this.entityGraph.size,
            totalMentions: Array.from(this.mentionIndex.values())
                .reduce((sum, mentions) => sum + mentions.length, 0),
            typeBreakdown: Object.fromEntries(
                Array.from(this.typeIndex.entries())
                    .map(([type, ids]) => [type, ids.size])
            ),
            lastIndexed: this.lastIndexTime,
            version: this.indexVersion,
            isIndexing: this.isIndexing
        };
    }
    
    clearIndex() {
        this.entityGraph.clear();
        this.mentionIndex.clear();
        this.typeIndex.clear();
        this.indexVersion++;
        this.notifyIndexUpdate();
    }
}