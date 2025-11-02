const { query } = require("@anthropic-ai/claude-code");
const path = require('path');
const fs = require('fs').promises;
const fetch = (...args) => import('node-fetch').then(({default: fetch}) => fetch(...args));

class ClaudeIntegration {
    constructor() {
        this.sessions = new Map();
        this.DOCS_DIR = '/Users/brain/Obsidian/Cloud_Vould';
    }

    /**
     * Process complex multi-file operations with Claude
     * @param {Object} params - Parameters for the operation
     * @param {string} params.command - The user's command/request
     * @param {Array<string>} params.files - List of files involved
     * @param {string} params.currentFile - Currently active file
     * @param {Object} params.context - Additional context
     * @param {string} params.sessionId - Optional session ID for continuing conversations
     */
    async *processComplexOperation({ command, files, currentFile, context, sessionId }) {
        const messages = [];
        const abortController = new AbortController();
        
        try {
            // Always include CLAUDE.md rules
            let claudeRules = '';
            try {
                claudeRules = await fs.readFile(path.join(__dirname, 'CLAUDE.md'), 'utf8');
            } catch (err) {
                console.error('Warning: Could not read CLAUDE.md:', err);
            }
            
            // Build the prompt with file context
            let prompt = claudeRules ? `${claudeRules}\n\n---\n\n` : '';
            prompt += `Complex operation requested: ${command}\n\n`;
            
            // Get file map for Claude
            let fileMap = [];
            let blueprints = {};
            try {
                const response = await fetch('http://localhost:3000/api/file-map');
                if (response.ok) {
                    fileMap = await response.json();
                }
                
                // Also get blueprints for quick understanding
                const blueprintResponse = await fetch('http://localhost:3000/api/metadata', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: '.edith/metadata/blueprints.json' })
                });
                
                if (blueprintResponse.ok) {
                    const data = await blueprintResponse.json();
                    blueprints = data.metadata || {};
                }
            } catch (err) {
                console.error('Error getting file map or blueprints:', err);
            }
            
            // Add blueprints overview first for quick understanding
            if (Object.keys(blueprints).length > 0) {
                prompt += `\nDOCUMENT BLUEPRINTS (Mind Maps):\n`;
                prompt += '```\n';
                for (const [docId, blueprint] of Object.entries(blueprints)) {
                    if (blueprint.currentStructure || blueprint.intendedPurpose) {
                        prompt += `\n${docId}:\n`;
                        if (blueprint.detectedPurpose) {
                            prompt += `  PURPOSE: ${blueprint.detectedPurpose}\n`;
                        }
                        if (blueprint.currentStructure) {
                            prompt += `  STRUCTURE: ${blueprint.currentStructure}\n`;
                        }
                        if (blueprint.keyPoints && blueprint.keyPoints.length > 0) {
                            prompt += `  KEY POINTS: ${blueprint.keyPoints.slice(0, 3).join('; ')}${blueprint.keyPoints.length > 3 ? '...' : ''}\n`;
                        }
                        if (blueprint.gapAnalysis) {
                            prompt += `  STATUS: ${blueprint.gapAnalysis.split('\n')[0]}\n`;
                        }
                    }
                }
                prompt += '```\n\n';
            }
            
            // Add file map overview
            if (fileMap.length > 0) {
                prompt += `\nAvailable files in the project (${fileMap.length} total):\n`;
                prompt += '```\n';
                fileMap.forEach(file => {
                    prompt += `${file.filename} - ${file.title}`;
                    
                    // Check if we have a blueprint for this file
                    const docId = file.filename.replace('.md', '');
                    if (blueprints[docId]) {
                        const bp = blueprints[docId];
                        if (bp.detectedPurpose) {
                            prompt += ` | ${bp.detectedPurpose}`;
                        } else if (bp.intendedPurpose) {
                            prompt += ` | Intended: ${bp.intendedPurpose}`;
                        }
                    } else if (file.metadata && file.metadata.purpose) {
                        prompt += ` | ${file.metadata.purpose}`;
                    }
                    prompt += '\n';
                });
                prompt += '```\n\n';
                
                prompt += 'IMPORTANT: Use the blueprints above to quickly understand each file\'s purpose and structure without loading full content.\n';
                prompt += 'When you need more context, selectively load only the relevant files based on their blueprints.\n\n';
            }
            
            // Add current file context
            if (currentFile) {
                prompt += `Current file: ${currentFile}\n`;
                try {
                    const content = await fs.readFile(path.join(this.DOCS_DIR, currentFile), 'utf8');
                    prompt += `\nCurrent file content:\n\`\`\`markdown\n${content}\n\`\`\`\n`;
                } catch (err) {
                    console.error('Error reading current file:', err);
                }
            }
            
            // Add other files context with metadata
            if (files && files.length > 0) {
                prompt += `\nFiles in context (${files.length}):\n`;
                
                // Separate main project files from context panel files
                const contextFileNames = context.contextFiles ? context.contextFiles.map(f => f.filename) : [];
                const mainFiles = files.filter(f => !contextFileNames.includes(f));
                const contextPanelFiles = files.filter(f => contextFileNames.includes(f));
                
                // List main project files
                if (mainFiles.length > 0) {
                    prompt += '\nMain project files:\n';
                    for (const file of mainFiles) {
                        const fileInfo = fileMap.find(f => f.filename === file);
                        prompt += `- ${file}`;
                        if (fileInfo && fileInfo.metadata) {
                            const meta = fileInfo.metadata;
                            if (meta.purpose) prompt += ` - ${meta.purpose}`;
                            if (meta.structure && meta.structure.length > 0) {
                                prompt += `\n  Structure: ${meta.structure.join(', ')}`;
                            }
                        }
                        prompt += '\n';
                    }
                }
                
                // List context panel files with their content
                if (contextPanelFiles.length > 0 && context.contextFiles) {
                    prompt += '\nContext panel files (loaded for reference and editing):\n';
                    for (const ctxFile of context.contextFiles) {
                        prompt += `\n--- ${ctxFile.filename} ---\n`;
                        prompt += `Title: ${ctxFile.title}\n`;
                        prompt += `Content preview:\n${ctxFile.content.substring(0, 500)}...\n`;
                        prompt += `[Full content available for reading/editing]\n`;
                    }
                }
                
                prompt += '\nIMPORTANT: You have access to read and edit ALL these files. Plan carefully before making changes.\n';
            }
            
            // Add entity information if available
            if (context && context.entities) {
                prompt += '\n\nENTITY INFORMATION:\n';
                prompt += 'The following entities have been extracted from the documents:\n\n';
                
                // Group entities by type
                const entitiesByType = {};
                context.entities.forEach(entity => {
                    const type = entity.type || 'unknown';
                    if (!entitiesByType[type]) entitiesByType[type] = [];
                    entitiesByType[type].push(entity);
                });
                
                // Display entities with their occurrences
                for (const [type, entities] of Object.entries(entitiesByType)) {
                    prompt += `${type.toUpperCase()}:\n`;
                    entities.forEach(entity => {
                        const name = entity.name || entity.text || entity.value || '';
                        const mentions = entity.mentions || 1;
                        const sources = entity.documentSources ? 
                            entity.documentSources.map(s => s.title || s.filename).join(', ') : 
                            'main document';
                        prompt += `  - ${name} (${mentions} mentions in: ${sources})\n`;
                    });
                    prompt += '\n';
                }
                
                prompt += 'Consider these entities when performing operations across documents.\n';
            }
            
            // Add any additional context
            if (context && context.notes) {
                prompt += `\nAdditional context:\n${context.notes}\n`;
            }
            
            prompt += '\n\nIMPORTANT: Follow the MANDATORY WORKFLOW from CLAUDE.md:\n';
            prompt += '1. EXAMINE all relevant files first\n';
            prompt += '2. CREATE A DETAILED PLAN with checklist\n';
            prompt += '3. EXECUTE one step at a time with verification\n';
            prompt += '4. CREATE BACKUPS before modifying files\n';
            prompt += '5. LOG all operations for future reference\n';
            prompt += '\nThe backup/log endpoints are available at:\n';
            prompt += '- POST /api/claude/backup - Create backup before changes\n';
            prompt += '- POST /api/claude/log - Log operations after completion\n';
            prompt += '- GET /api/claude/backups - List available backups\n';
            prompt += '- POST /api/claude/restore - Restore from backup\n';
            
            // Configure options
            const options = {
                maxTurns: 10,
                permissionMode: 'plan', // Use planning mode for complex operations
                cwd: this.DOCS_DIR,
                allowedTools: ['Read', 'Write', 'Edit', 'MultiEdit', 'Glob', 'Grep'],
                outputFormat: 'stream-json'
            };
            
            // If continuing a session
            if (sessionId && this.sessions.has(sessionId)) {
                options.resume = sessionId;
            }
            
            // Stream responses from Claude
            for await (const message of query({
                prompt,
                abortController,
                options
            })) {
                messages.push(message);
                
                // Store session ID for future use
                if (message.session_id && !sessionId) {
                    this.sessions.set(message.session_id, {
                        started: new Date(),
                        messages: []
                    });
                    sessionId = message.session_id;
                }
                
                // Store messages in session
                if (sessionId && this.sessions.has(sessionId)) {
                    this.sessions.get(sessionId).messages.push(message);
                }
                
                // Yield message for streaming to client
                yield message;
            }
            
        } catch (error) {
            console.error('Claude integration error:', error);
            yield {
                type: 'error',
                message: error.message
            };
        }
    }
    
    /**
     * Check if an operation should use Claude instead of GPT/Gemini
     * @param {Object} params - Operation parameters
     * @returns {boolean} - Whether to use Claude
     */
    shouldUseClaude({ command, files, isComplexEdit, hasContextFiles }) {
        // Use Claude for complex multi-document operations that need planning
        
        // 1. Multiple files from different sources (context panel + main)
        if (hasContextFiles && files && files.length > 0) return true;
        
        // 2. Multiple files are involved
        if (files && files.length > 1) return true;
        
        // 3. Command indicates complex compilation/collection operations
        const complexKeywords = [
            // Multi-document operations
            'compile', 'collect', 'gather', 'combine', 'consolidate',
            'across', 'from all', 'from multiple', 'from context',
            'merge', 'integrate', 'synthesize', 'extract from',
            
            // Planning operations
            'plan', 'organize', 'structure', 'design', 'architect',
            'refactor', 'restructure', 'reorganize',
            
            // Analysis operations
            'analyze across', 'compare between', 'find patterns',
            'cross-reference', 'correlate',
            
            // Explicit multi-file
            'multiple files', 'across files', 'all files', 'every file',
            'context files', 'panel files', 'all documents'
        ];
        
        const commandLower = command.toLowerCase();
        if (complexKeywords.some(keyword => commandLower.includes(keyword))) {
            return true;
        }
        
        // 4. Command references both Context and Target
        if (commandLower.includes('context') && commandLower.includes('target')) {
            return true;
        }
        
        // 5. Explicitly marked as complex
        if (isComplexEdit) return true;
        
        // Otherwise use GPT/Gemini for simple single-file operations
        return false;
    }
    
    /**
     * Get session history
     * @param {string} sessionId - Session ID
     * @returns {Object|null} - Session data or null
     */
    getSession(sessionId) {
        return this.sessions.get(sessionId) || null;
    }
    
    /**
     * Clear old sessions (older than 1 hour)
     */
    cleanupSessions() {
        const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
        
        for (const [sessionId, session] of this.sessions.entries()) {
            if (session.started < oneHourAgo) {
                this.sessions.delete(sessionId);
            }
        }
    }
}

module.exports = ClaudeIntegration;