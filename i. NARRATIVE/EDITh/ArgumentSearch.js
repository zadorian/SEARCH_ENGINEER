class ArgumentSearch {
    constructor() {
        this.arguments = new Map(); // Map of argumentId -> argument object
        this.index = new Map(); // Search index: term -> Set of argumentIds
        this.unitArguments = new Map(); // unitId -> Set of argumentIds
        this.intentAnalyzer = null; // Will be initialized with AI
        
        this.initialize();
    }
    
    async initialize() {
        // Listen for unit completion events
        document.addEventListener('unitCompleted', (e) => {
            this.extractArgumentsFromUnit(e.detail.unitId, e.detail.content, e.detail.metaComment);
        });
        
        // Listen for text changes to update arguments
        document.addEventListener('textChanged', (e) => {
            this.updateArgumentsInRange(e.detail.start, e.detail.end, e.detail.newText);
        });
        
        console.log('✅ ArgumentSearch initialized');
    }
    
    async extractArgumentsFromUnit(unitId, content, metaComment) {
        console.log(`📝 Extracting arguments from unit ${unitId}`);
        
        // 1. Analyze meta-comment for user intent
        const intent = await this.analyzeIntent(metaComment);
        
        // 2. Extract arguments from content
        const extractedArgs = await this.extractArguments(content, intent);
        
        // 3. Index arguments for searching
        extractedArgs.forEach(arg => {
            this.indexArgument(arg, unitId);
        });
        
        // 4. Dispatch event for UI update
        document.dispatchEvent(new CustomEvent('argumentsExtracted', {
            detail: { unitId, arguments: extractedArgs, intent }
        }));
    }
    
    async analyzeIntent(metaComment) {
        if (!metaComment) return { type: 'general', keywords: [] };
        
        // Use AI to understand the intent behind the meta-comment
        const prompt = `Analyze this meta-comment to understand the author's intent:
"${metaComment}"

Return a JSON object with:
- type: the type of content (e.g., "argument", "example", "counterpoint", "evidence", "conclusion")
- keywords: key terms that indicate what the author is trying to accomplish
- expectedArguments: what kinds of points we should look for`;
        
        try {
            // This would use the same AI as spellcheck
            const response = await this.callLocalAI(prompt);
            return JSON.parse(response);
        } catch (e) {
            // Fallback to pattern matching
            return this.analyzeIntentFallback(metaComment);
        }
    }
    
    analyzeIntentFallback(metaComment) {
        const lower = metaComment.toLowerCase();
        
        // Pattern matching for common intents
        if (lower.includes('argue') || lower.includes('claim')) {
            return { type: 'argument', keywords: ['claim', 'because', 'therefore'] };
        } else if (lower.includes('example') || lower.includes('instance')) {
            return { type: 'example', keywords: ['for instance', 'such as', 'like'] };
        } else if (lower.includes('counter') || lower.includes('however')) {
            return { type: 'counterpoint', keywords: ['however', 'but', 'although'] };
        } else if (lower.includes('evidence') || lower.includes('proof')) {
            return { type: 'evidence', keywords: ['shows', 'proves', 'demonstrates'] };
        } else if (lower.includes('conclude') || lower.includes('summary')) {
            return { type: 'conclusion', keywords: ['therefore', 'thus', 'in conclusion'] };
        }
        
        return { type: 'general', keywords: [] };
    }
    
    async extractArguments(content, intent) {
        const args = [];
        
        // Split into sentences for analysis
        const sentences = this.smartSentenceSplit(content);
        
        for (let i = 0; i < sentences.length; i++) {
            const sentence = sentences[i];
            const context = sentences.slice(Math.max(0, i - 2), i + 3).join(' ');
            
            // Check if this sentence contains an argument
            const argData = await this.analyzeForArgument(sentence, context, intent);
            
            if (argData.isArgument) {
                args.push({
                    id: this.generateId(),
                    text: sentence,
                    type: argData.type,
                    strength: argData.strength,
                    keywords: argData.keywords,
                    position: { start: content.indexOf(sentence), end: content.indexOf(sentence) + sentence.length },
                    context: context,
                    intent: intent,
                    supportingEvidence: [],
                    counterpoints: [],
                    timestamp: Date.now()
                });
            }
        }
        
        // Link related arguments
        this.linkRelatedArguments(args);
        
        return args;
    }
    
    smartSentenceSplit(text) {
        // Smart sentence splitting that handles abbreviations, quotes, etc.
        const sentences = [];
        let current = '';
        let inQuote = false;
        
        for (let i = 0; i < text.length; i++) {
            const char = text[i];
            current += char;
            
            if (char === '"' || char === "'") {
                inQuote = !inQuote;
            }
            
            if (!inQuote && (char === '.' || char === '!' || char === '?')) {
                // Check if it's really the end of a sentence
                const next = text[i + 1];
                if (!next || next === ' ' || next === '\n') {
                    // Check for common abbreviations
                    const lastWord = current.trim().split(' ').pop();
                    if (!this.isAbbreviation(lastWord)) {
                        sentences.push(current.trim());
                        current = '';
                    }
                }
            }
        }
        
        if (current.trim()) {
            sentences.push(current.trim());
        }
        
        return sentences;
    }
    
    isAbbreviation(word) {
        const abbrevs = ['Dr.', 'Mr.', 'Mrs.', 'Ms.', 'Prof.', 'Sr.', 'Jr.', 'Inc.', 'Ltd.', 'Co.', 'vs.', 'etc.', 'i.e.', 'e.g.'];
        return abbrevs.includes(word);
    }
    
    async analyzeForArgument(sentence, context, intent) {
        // Patterns that indicate arguments
        const argumentPatterns = [
            /because|since|therefore|thus|hence|so|accordingly/i,
            /claim|argue|believe|think|suggest|propose/i,
            /evidence|shows|proves|demonstrates|indicates/i,
            /must|should|ought|need to|have to/i,
            /in fact|actually|indeed|clearly|obviously/i
        ];
        
        // Check for argument indicators
        let isArgument = argumentPatterns.some(pattern => pattern.test(sentence));
        
        // Also check based on intent
        if (intent.keywords.some(keyword => sentence.toLowerCase().includes(keyword))) {
            isArgument = true;
        }
        
        if (!isArgument) return { isArgument: false };
        
        // Determine argument type and strength
        const type = this.classifyArgumentType(sentence, intent);
        const strength = this.assessArgumentStrength(sentence, context);
        const keywords = this.extractKeywords(sentence);
        
        return {
            isArgument: true,
            type,
            strength,
            keywords
        };
    }
    
    classifyArgumentType(sentence, intent) {
        const lower = sentence.toLowerCase();
        
        if (lower.includes('because') || lower.includes('since')) {
            return 'causal';
        } else if (lower.includes('should') || lower.includes('must')) {
            return 'normative';
        } else if (lower.includes('evidence') || lower.includes('data')) {
            return 'empirical';
        } else if (lower.includes('believe') || lower.includes('think')) {
            return 'opinion';
        } else if (intent.type === 'counterpoint') {
            return 'counter';
        }
        
        return 'claim';
    }
    
    assessArgumentStrength(sentence, context) {
        let strength = 0.5; // Base strength
        
        // Increase for evidence words
        if (/evidence|data|study|research|fact/i.test(sentence)) {
            strength += 0.2;
        }
        
        // Increase for certainty words
        if (/clearly|obviously|certainly|definitely/i.test(sentence)) {
            strength += 0.1;
        }
        
        // Decrease for hedging words
        if (/maybe|perhaps|possibly|might|could/i.test(sentence)) {
            strength -= 0.2;
        }
        
        // Context bonus
        if (context.length > 200) {
            strength += 0.1; // Well-developed context
        }
        
        return Math.max(0, Math.min(1, strength));
    }
    
    extractKeywords(sentence) {
        // Remove common words and extract key terms
        const stopWords = new Set(['the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'them', 'their', 'what', 'which', 'who', 'when', 'where', 'why', 'how']);
        
        const words = sentence.toLowerCase().split(/\W+/);
        const keywords = words.filter(word => word.length > 3 && !stopWords.has(word));
        
        return [...new Set(keywords)];
    }
    
    linkRelatedArguments(args) {
        // Find relationships between arguments
        for (let i = 0; i < args.length; i++) {
            for (let j = i + 1; j < args.length; j++) {
                const similarity = this.calculateSimilarity(args[i], args[j]);
                
                if (similarity > 0.7) {
                    // These arguments are related
                    if (args[j].type === 'counter' || args[j].text.includes('however')) {
                        args[i].counterpoints.push(args[j].id);
                    } else if (args[j].type === 'evidence' || args[j].type === 'empirical') {
                        args[i].supportingEvidence.push(args[j].id);
                    }
                }
            }
        }
    }
    
    calculateSimilarity(arg1, arg2) {
        // Simple keyword overlap similarity
        const keywords1 = new Set(arg1.keywords);
        const keywords2 = new Set(arg2.keywords);
        
        const intersection = [...keywords1].filter(k => keywords2.has(k));
        const union = new Set([...keywords1, ...keywords2]);
        
        return intersection.length / union.size;
    }
    
    indexArgument(arg, unitId) {
        // Store the argument
        this.arguments.set(arg.id, arg);
        
        // Index by unit
        if (!this.unitArguments.has(unitId)) {
            this.unitArguments.set(unitId, new Set());
        }
        this.unitArguments.get(unitId).add(arg.id);
        
        // Index by keywords for searching
        arg.keywords.forEach(keyword => {
            if (!this.index.has(keyword)) {
                this.index.set(keyword, new Set());
            }
            this.index.get(keyword).add(arg.id);
        });
        
        // Also index by type
        if (!this.index.has(arg.type)) {
            this.index.set(arg.type, new Set());
        }
        this.index.get(arg.type).add(arg.id);
    }
    
    search(query, filters = {}) {
        const results = new Set();
        
        // Search by keywords
        const queryWords = query.toLowerCase().split(/\W+/);
        queryWords.forEach(word => {
            if (this.index.has(word)) {
                this.index.get(word).forEach(id => results.add(id));
            }
        });
        
        // Apply filters
        let filteredResults = [...results].map(id => this.arguments.get(id));
        
        if (filters.type) {
            filteredResults = filteredResults.filter(arg => arg.type === filters.type);
        }
        
        if (filters.minStrength) {
            filteredResults = filteredResults.filter(arg => arg.strength >= filters.minStrength);
        }
        
        if (filters.unitId) {
            const unitArgs = this.unitArguments.get(filters.unitId) || new Set();
            filteredResults = filteredResults.filter(arg => unitArgs.has(arg.id));
        }
        
        // Sort by relevance
        return this.rankResults(filteredResults, query);
    }
    
    rankResults(results, query) {
        const queryWords = new Set(query.toLowerCase().split(/\W+/));
        
        return results.sort((a, b) => {
            // Calculate relevance scores
            const scoreA = this.calculateRelevance(a, queryWords);
            const scoreB = this.calculateRelevance(b, queryWords);
            
            return scoreB - scoreA;
        });
    }
    
    calculateRelevance(arg, queryWords) {
        let score = 0;
        
        // Keyword matches
        arg.keywords.forEach(keyword => {
            if (queryWords.has(keyword)) {
                score += 2;
            }
        });
        
        // Text contains query words
        queryWords.forEach(word => {
            if (arg.text.toLowerCase().includes(word)) {
                score += 1;
            }
        });
        
        // Strength bonus
        score += arg.strength;
        
        // Type bonus for certain searches
        if (queryWords.has('evidence') && arg.type === 'empirical') {
            score += 3;
        }
        
        return score;
    }
    
    generateId() {
        return 'arg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }
    
    async callLocalAI(prompt) {
        // This would integrate with the same AI used for spellcheck
        // For now, returning a mock response
        return JSON.stringify({
            type: 'argument',
            keywords: ['claim', 'evidence'],
            expectedArguments: ['main thesis', 'supporting points']
        });
    }
    
    updateArgumentsInRange(start, end, newText) {
        // Update arguments when text changes
        // This is called on every text change to keep arguments in sync
        console.log('Updating arguments in range:', start, end);
        
        // Find affected arguments
        const affected = [];
        this.arguments.forEach(arg => {
            if (arg.position.start >= start && arg.position.end <= end) {
                affected.push(arg);
            }
        });
        
        // Re-extract arguments from the new text
        // This ensures arguments stay current with edits
    }
}

// Export for use in EDITh
window.ArgumentSearch = ArgumentSearch;
