const express = require('express');
const fs = require('fs').promises;
const path = require('path');
require('dotenv').config();
const ClaudeIntegration = require('./claude_integration');

const app = express();
const PORT = process.env.PORT || 3000;

// Initialize Claude integration
const claudeIntegration = new ClaudeIntegration();

// Middleware with increased body size limit (50MB)
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ limit: '50mb', extended: true }));
app.use(express.static('.'));

// Use Obsidian vault directory
const DOCS_DIR = '/Users/brain/Obsidian/Cloud_Vould';
const EDITH_DIR = path.join(__dirname, '.edith');
const BACKUPS_DIR = path.join(EDITH_DIR, 'backups');
const LOGS_DIR = path.join(EDITH_DIR, 'logs');
const METADATA_DIR = path.join(EDITH_DIR, 'metadata');

// Ensure directories exist
fs.mkdir(DOCS_DIR, { recursive: true }).catch(console.error);
fs.mkdir(BACKUPS_DIR, { recursive: true }).catch(console.error);
fs.mkdir(LOGS_DIR, { recursive: true }).catch(console.error);
fs.mkdir(METADATA_DIR, { recursive: true }).catch(console.error);

// Save document endpoint
app.post('/api/save', async (req, res) => {
    try {
        const { title, content } = req.body;
        // Create a clean filename from title
        const cleanTitle = title.replace(/[^a-z0-9]/gi, '_').toLowerCase() || 'untitled';
        const filename = `${cleanTitle}.md`;
        const filepath = path.join(DOCS_DIR, filename);
        
        await fs.writeFile(filepath, content, 'utf8');
        console.log(`Saved: ${filepath}`);
        
        res.json({ success: true, filename, path: filepath });
    } catch (error) {
        console.error('Save error:', error);
        res.status(500).json({ error: 'Failed to save document' });
    }
});

// Load document endpoint
app.get('/api/load/:filename', async (req, res) => {
    try {
        // Validate filename to prevent path traversal
        const filename = req.params.filename;
        if (filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
            return res.status(400).json({ error: 'Invalid filename' });
        }
        
        // Additional validation: ensure it's a .md file
        if (!filename.endsWith('.md')) {
            return res.status(400).json({ error: 'Only markdown files are allowed' });
        }
        
        const filepath = path.join(DOCS_DIR, filename);
        
        // Ensure the resolved path is within DOCS_DIR
        const resolvedPath = path.resolve(filepath);
        const resolvedDocsDir = path.resolve(DOCS_DIR);
        if (!resolvedPath.startsWith(resolvedDocsDir)) {
            return res.status(400).json({ error: 'Invalid file path' });
        }
        
        const content = await fs.readFile(filepath, 'utf8');
        const title = filename.replace('.md', '').replace(/_/g, ' ');
        
        res.json({ title, content });
    } catch (error) {
        console.error('Load error:', error);
        if (error.code === 'ENOENT') {
            res.status(404).json({ error: 'Document not found' });
        } else {
            res.status(500).json({ error: 'Error loading document' });
        }
    }
});

// Delete document endpoint
app.delete('/api/delete/:filename', async (req, res) => {
    try {
        // Validate filename to prevent path traversal
        const filename = req.params.filename;
        if (filename.includes('..') || filename.includes('/') || filename.includes('\\')) {
            return res.status(400).json({ error: 'Invalid filename' });
        }
        
        // Additional validation: ensure it's a .md file
        if (!filename.endsWith('.md')) {
            return res.status(400).json({ error: 'Only markdown files can be deleted' });
        }
        
        const filepath = path.join(DOCS_DIR, filename);
        
        // Ensure the resolved path is within DOCS_DIR
        const resolvedPath = path.resolve(filepath);
        const resolvedDocsDir = path.resolve(DOCS_DIR);
        if (!resolvedPath.startsWith(resolvedDocsDir)) {
            return res.status(400).json({ error: 'Invalid file path' });
        }
        
        await fs.unlink(filepath);
        
        res.json({ success: true });
    } catch (error) {
        console.error('Delete error:', error);
        if (error.code === 'ENOENT') {
            res.status(404).json({ error: 'Document not found' });
        } else {
            res.status(500).json({ error: 'Error deleting document' });
        }
    }
});

// List documents endpoint
app.get('/api/documents', async (req, res) => {
    try {
        const files = await fs.readdir(DOCS_DIR);
        const mdFiles = [];
        
        for (const file of files) {
            if (file.endsWith('.md')) {
                const filepath = path.join(DOCS_DIR, file);
                const stats = await fs.stat(filepath);
                mdFiles.push({
                    name: file,
                    modified: stats.mtime,
                    size: stats.size
                });
            }
        }
        
        // Sort by modified date, newest first
        mdFiles.sort((a, b) => b.modified - a.modified);
        
        res.json(mdFiles);
    } catch (error) {
        console.error('List documents error:', error);
        res.status(500).json({ error: 'Failed to list documents' });
    }
});

// Gemini gap filling endpoint
app.post('/api/fill-gap', async (req, res) => {
    console.log('Gap fill request received:', req.body);
    try {
        const { context, gap, additionalContext } = req.body;
        const { spawn } = require('child_process');
        
        // Call Python script
        const python = spawn('python3', [path.join(__dirname, 'gemini_gap_filler.py')]);
        
        let result = '';
        let error = '';
        
        python.stdout.on('data', (data) => {
            result += data.toString();
        });
        
        python.stderr.on('data', (data) => {
            error += data.toString();
            console.error('Python stderr:', data.toString());
        });
        
        // Add timeout
        const timeout = setTimeout(() => {
            python.kill();
            console.error('Python script timeout');
            res.status(500).json({ error: 'Timeout' });
        }, 10000);
        
        python.on('close', (code) => {
            clearTimeout(timeout);
            console.log('Python closed with code:', code, 'Result:', result);
            if (code !== 0 || error) {
                console.error('Python error:', error);
                res.status(500).json({ error: 'Failed to get suggestion' });
            } else {
                try {
                    const response = JSON.parse(result);
                    res.json(response);
                } catch (e) {
                    console.error('Failed to parse:', result);
                    res.status(500).json({ error: 'Failed to parse response' });
                }
            }
        });
        
        // Send input to Python script with additional context
        python.stdin.write(JSON.stringify({ context, gap, additionalContext }));
        python.stdin.end();
        
    } catch (error) {
        console.error('Gemini error:', error);
        res.status(500).json({ error: 'Failed to get suggestion' });
    }
});

// Footnote endpoints
const FOOTNOTES_DIR = path.join(DOCS_DIR, '.footnotes');
fs.mkdir(FOOTNOTES_DIR, { recursive: true }).catch(console.error);

// Save footnote
app.post('/api/footnotes', async (req, res) => {
    try {
        const footnote = req.body;
        const filename = `${Date.now()}_${footnote.documentId}.json`;
        const filepath = path.join(FOOTNOTES_DIR, filename);
        
        await fs.writeFile(filepath, JSON.stringify(footnote, null, 2), 'utf8');
        
        res.json({ success: true, id: filename });
    } catch (error) {
        console.error('Save footnote error:', error);
        res.status(500).json({ error: 'Failed to save footnote' });
    }
});

// List footnotes
app.get('/api/footnotes', async (req, res) => {
    try {
        const files = await fs.readdir(FOOTNOTES_DIR);
        const footnotes = [];
        
        for (const file of files) {
            if (file.endsWith('.json')) {
                const content = await fs.readFile(path.join(FOOTNOTES_DIR, file), 'utf8');
                const footnote = JSON.parse(content);
                footnote.id = file;
                footnotes.push(footnote);
            }
        }
        
        res.json(footnotes);
    } catch (error) {
        console.error('List footnotes error:', error);
        res.status(500).json({ error: 'Failed to list footnotes' });
    }
});

// Get footnote
app.get('/api/footnotes/:id', async (req, res) => {
    try {
        const filepath = path.join(FOOTNOTES_DIR, req.params.id);
        const content = await fs.readFile(filepath, 'utf8');
        const footnote = JSON.parse(content);
        footnote.id = req.params.id;
        
        res.json(footnote);
    } catch (error) {
        res.status(404).json({ error: 'Footnote not found' });
    }
});

// Delete footnote
app.delete('/api/footnotes/:id', async (req, res) => {
    try {
        const filepath = path.join(FOOTNOTES_DIR, req.params.id);
        await fs.unlink(filepath);
        
        res.json({ success: true });
    } catch (error) {
        res.status(404).json({ error: 'Footnote not found' });
    }
});

// Search notes endpoint for context panel
app.get('/api/search-notes', async (req, res) => {
    try {
        const query = req.query.q || '';
        if (!query) {
            return res.json([]);
        }
        
        const results = [];
        const files = await fs.readdir(DOCS_DIR);
        
        // Search through all markdown files
        for (const file of files) {
            if (!file.endsWith('.md')) continue;
            
            const filepath = path.join(DOCS_DIR, file);
            const content = await fs.readFile(filepath, 'utf8');
            const title = file.replace('.md', '').replace(/_/g, ' ');
            
            // Check if query matches title or content
            const lowerQuery = query.toLowerCase();
            const lowerTitle = title.toLowerCase();
            const lowerContent = content.toLowerCase();
            
            let matches = false;
            let tags = [];
            
            // Check for hashtag search
            if (query.startsWith('#')) {
                // Extract all hashtags from content
                const hashtagMatches = content.match(/#\w+/g) || [];
                tags = hashtagMatches.map(tag => tag.toLowerCase());
                
                if (tags.includes(query.toLowerCase())) {
                    matches = true;
                }
            } else {
                // Regular title/content search
                if (lowerTitle.includes(lowerQuery) || lowerContent.includes(lowerQuery)) {
                    matches = true;
                }
                
                // Also extract tags for display
                const hashtagMatches = content.match(/#\w+/g) || [];
                tags = hashtagMatches.slice(0, 5); // Limit to first 5 tags
            }
            
            if (matches) {
                // Get preview of content (first 200 chars)
                const preview = content.substring(0, 200).replace(/\n/g, ' ').trim();
                
                results.push({
                    filename: file,
                    title: title,
                    content: content,
                    preview: preview + (content.length > 200 ? '...' : ''),
                    tags: tags
                });
            }
        }
        
        // Sort by relevance (title matches first)
        results.sort((a, b) => {
            const aInTitle = a.title.toLowerCase().includes(query.toLowerCase());
            const bInTitle = b.title.toLowerCase().includes(query.toLowerCase());
            if (aInTitle && !bInTitle) return -1;
            if (!aInTitle && bInTitle) return 1;
            return 0;
        });
        
        // Limit results
        res.json(results.slice(0, 10));
    } catch (error) {
        console.error('Search error:', error);
        res.status(500).json({ error: 'Search failed' });
    }
});

// Save metadata endpoint
app.post('/api/save-metadata', async (req, res) => {
    try {
        const { path: metadataPath, metadata } = req.body;
        const METADATA_DIR = path.join(DOCS_DIR, '.edith', 'metadata');
        
        // Ensure metadata directory exists
        await fs.mkdir(METADATA_DIR, { recursive: true });
        
        // Save metadata file
        const fullPath = path.join(DOCS_DIR, metadataPath);
        await fs.writeFile(fullPath, JSON.stringify(metadata, null, 2), 'utf8');
        
        res.json({ success: true });
    } catch (error) {
        console.error('Save metadata error:', error);
        res.status(500).json({ error: 'Failed to save metadata' });
    }
});

// Get metadata endpoint
app.post('/api/metadata', async (req, res) => {
    try {
        const { path: metadataPath } = req.body;
        const fullPath = path.join(DOCS_DIR, metadataPath);
        
        try {
            const content = await fs.readFile(fullPath, 'utf8');
            const metadata = JSON.parse(content);
            res.json({ metadata });
        } catch (err) {
            // Return empty metadata if file doesn't exist
            res.json({ metadata: {} });
        }
    } catch (error) {
        console.error('Get metadata error:', error);
        res.status(500).json({ error: 'Failed to get metadata' });
    }
});

// Get file map for Claude
app.get('/api/file-map', async (req, res) => {
    try {
        const fileMap = [];
        const files = await fs.readdir(DOCS_DIR);
        const METADATA_DIR = path.join(DOCS_DIR, '.edith', 'metadata');
        
        for (const file of files) {
            if (!file.endsWith('.md')) continue;
            
            const filepath = path.join(DOCS_DIR, file);
            const stats = await fs.stat(filepath);
            const title = file.replace('.md', '').replace(/_/g, ' ');
            
            // Try to load metadata if it exists
            let metadata = null;
            try {
                const metadataPath = path.join(METADATA_DIR, `${file}.json`);
                const metadataContent = await fs.readFile(metadataPath, 'utf8');
                metadata = JSON.parse(metadataContent);
            } catch (err) {
                // No metadata file yet
            }
            
            fileMap.push({
                filename: file,
                title: title,
                path: filepath,
                size: stats.size,
                modified: stats.mtime,
                metadata: metadata
            });
        }
        
        res.json(fileMap);
    } catch (error) {
        console.error('File map error:', error);
        res.status(500).json({ error: 'Failed to get file map' });
    }
});

// Claude complex operations endpoint
app.post('/api/claude-complex', async (req, res) => {
    console.log('Claude complex operation request:', req.body);
    
    // Set headers for streaming
    res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*'
    });
    
    try {
        const { command, files, currentFile, context, sessionId } = req.body;
        
        // Process with Claude
        const messageStream = claudeIntegration.processComplexOperation({
            command,
            files,
            currentFile,
            context,
            sessionId
        });
        
        // Stream messages to client
        for await (const message of messageStream) {
            res.write(`data: ${JSON.stringify(message)}\n\n`);
        }
        
        res.write(`data: [DONE]\n\n`);
        res.end();
        
    } catch (error) {
        console.error('Claude endpoint error:', error);
        res.write(`data: ${JSON.stringify({
            type: 'error',
            message: 'Failed to process with Claude'
        })}\n\n`);
        res.end();
    }
});

// Check if operation should use Claude
app.post('/api/should-use-claude', (req, res) => {
    const { command, files, isComplexEdit } = req.body;
    const shouldUse = claudeIntegration.shouldUseClaude({ command, files, isComplexEdit });
    res.json({ useClaude: shouldUse });
});

// AI Command endpoint with streaming
app.post('/api/command', async (req, res) => {
    console.log('Command request received:', req.body);
    
    // Set headers for streaming
    res.writeHead(200, {
        'Content-Type': 'text/plain',
        'Transfer-Encoding': 'chunked',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
    });
    
    try {
        const { command, context } = req.body;
        const { spawn } = require('child_process');
        
        // Call Python script for AI processing
        // Use v2 if smart processing is enabled
        const scriptName = context.processingMode === 'smart' ? 
            'ai_command_processor_v2.py' : 'ai_command_processor.py';
        const python = spawn('python3', [path.join(__dirname, scriptName)]);
        
        let result = '';
        let error = '';
        
        python.stdout.on('data', (data) => {
            const chunk = data.toString();
            // Stream each line to the client
            const lines = chunk.split('\n');
            lines.forEach(line => {
                if (line.trim()) {
                    res.write(`data: ${line}\n\n`);
                }
            });
        });
        
        python.stderr.on('data', (data) => {
            error += data.toString();
            console.error('Python stderr:', data.toString());
        });
        
        // Add timeout to prevent hanging
        const timeout = setTimeout(() => {
            console.error('Python process timeout');
            python.kill('SIGTERM');
            res.write(`data: ${JSON.stringify({type: 'error', message: 'Command processing timeout'})}\n\n`);
            res.end();
        }, 30000); // 30 second timeout
        
        python.on('close', (code) => {
            clearTimeout(timeout);
            console.log('Python closed with code:', code);
            if (code !== 0 || error) {
                console.error('Python error:', error);
                res.write(`data: ${JSON.stringify({type: 'error', message: 'Failed to process command'})}\n\n`);
            }
            res.end();
        });
        
        python.on('error', (err) => {
            clearTimeout(timeout);
            console.error('Python process error:', err);
            res.write(`data: ${JSON.stringify({type: 'error', message: 'Python process failed'})}\n\n`);
            res.end();
        });
        
        // Send input to Python script
        python.stdin.write(JSON.stringify({ command, context }));
        python.stdin.end();
        
    } catch (error) {
        console.error('Command processing error:', error);
        res.write(`data: ${JSON.stringify({type: 'error', message: 'Command processing failed'})}\n\n`);
        res.end();
    }
});

// Claude backup operations
app.post('/api/claude/backup', async (req, res) => {
    try {
        const { files, operation, context } = req.body;
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
        const backupDir = path.join(BACKUPS_DIR, timestamp);
        
        // Create backup directory
        await fs.mkdir(backupDir, { recursive: true });
        
        // Create manifest
        const manifest = {
            timestamp: new Date().toISOString(),
            operation,
            context,
            files: []
        };
        
        // Backup each file
        for (const file of files) {
            const sourcePath = path.join(__dirname, file);
            const backupPath = path.join(backupDir, path.basename(file));
            
            try {
                const content = await fs.readFile(sourcePath, 'utf8');
                await fs.writeFile(backupPath, content, 'utf8');
                manifest.files.push({
                    original: file,
                    backup: path.basename(file),
                    size: content.length
                });
            } catch (err) {
                console.error(`Failed to backup ${file}:`, err);
            }
        }
        
        // Save manifest
        await fs.writeFile(
            path.join(backupDir, 'manifest.json'),
            JSON.stringify(manifest, null, 2),
            'utf8'
        );
        
        // Update latest symlink
        const latestPath = path.join(BACKUPS_DIR, 'latest');
        try {
            await fs.unlink(latestPath);
        } catch (err) {
            // Ignore if doesn't exist
        }
        await fs.symlink(backupDir, latestPath);
        
        res.json({ success: true, backupId: timestamp, manifest });
    } catch (error) {
        console.error('Backup error:', error);
        res.status(500).json({ error: 'Failed to create backup' });
    }
});

// Claude logging operations
app.post('/api/claude/log', async (req, res) => {
    try {
        const { operation, files, status, context, backupId } = req.body;
        const logPath = path.join(LOGS_DIR, 'claude_operations.log');
        
        const logEntry = `[${new Date().toISOString()}] Operation: ${operation}
Files Modified:
${files.map(f => `  - ${f.path} (${f.description})`).join('\n')}
${backupId ? `Backup Created: .edith/backups/${backupId}/` : 'No backup created'}
Context: ${context}
Status: ${status}
${'='.repeat(80)}
`;
        
        await fs.appendFile(logPath, logEntry, 'utf8');
        res.json({ success: true });
    } catch (error) {
        console.error('Logging error:', error);
        res.status(500).json({ error: 'Failed to write log' });
    }
});

// List available backups
app.get('/api/claude/backups', async (req, res) => {
    try {
        const backups = [];
        const dirs = await fs.readdir(BACKUPS_DIR);
        
        for (const dir of dirs) {
            if (dir === 'latest') continue;
            
            try {
                const manifestPath = path.join(BACKUPS_DIR, dir, 'manifest.json');
                const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
                backups.push({
                    id: dir,
                    ...manifest
                });
            } catch (err) {
                // Skip invalid backups
            }
        }
        
        // Sort by timestamp, newest first
        backups.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        res.json(backups);
    } catch (error) {
        console.error('List backups error:', error);
        res.status(500).json({ error: 'Failed to list backups' });
    }
});

// Restore from backup
app.post('/api/claude/restore', async (req, res) => {
    try {
        const { backupId } = req.body;
        const backupDir = path.join(BACKUPS_DIR, backupId);
        
        // Read manifest
        const manifestPath = path.join(backupDir, 'manifest.json');
        const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
        
        // Restore each file
        const restored = [];
        for (const file of manifest.files) {
            const backupPath = path.join(backupDir, file.backup);
            const targetPath = path.join(__dirname, file.original);
            
            try {
                const content = await fs.readFile(backupPath, 'utf8');
                await fs.writeFile(targetPath, content, 'utf8');
                restored.push(file.original);
            } catch (err) {
                console.error(`Failed to restore ${file.original}:`, err);
            }
        }
        
        // Log the restoration
        const logEntry = `[${new Date().toISOString()}] RESTORATION
Restored from backup: ${backupId}
Original operation: ${manifest.operation}
Files restored: ${restored.join(', ')}
${'='.repeat(80)}
`;
        
        const logPath = path.join(LOGS_DIR, 'claude_operations.log');
        await fs.appendFile(logPath, logEntry, 'utf8');
        
        res.json({ success: true, restored });
    } catch (error) {
        console.error('Restore error:', error);
        res.status(500).json({ error: 'Failed to restore backup' });
    }
});

// Gemini orchestration endpoints for large document processing
app.post('/api/gemini-plan', async (req, res) => {
    try {
        const { command, documentStructure, context } = req.body;
        
        // Call Python script for Gemini planning
        const { spawn } = require('child_process');
        const python = spawn('python3', [path.join(__dirname, 'gemini_orchestration.py'), 'plan']);
        
        let result = '';
        let error = '';
        
        python.stdout.on('data', (data) => {
            result += data.toString();
        });
        
        python.stderr.on('data', (data) => {
            error += data.toString();
        });
        
        python.on('close', (code) => {
            if (code !== 0) {
                console.error('Gemini planning error:', error);
                res.status(500).json({ error: 'Failed to create execution plan' });
            } else {
                try {
                    const planData = JSON.parse(result);
                    res.json(planData);
                } catch (parseError) {
                    console.error('Failed to parse plan response:', parseError);
                    res.status(500).json({ error: 'Invalid plan response' });
                }
            }
        });
        
        // Send input to Python script
        python.stdin.write(JSON.stringify({ command, documentStructure, context }));
        python.stdin.end();
        
    } catch (error) {
        console.error('Gemini planning error:', error);
        res.status(500).json({ error: 'Failed to create execution plan' });
    }
});

app.post('/api/gpt-process-unit', async (req, res) => {
    try {
        const { unit, instruction, originalCommand, context, isCorrection } = req.body;
        
        // Call Python script for GPT processing
        const { spawn } = require('child_process');
        const python = spawn('python3', [path.join(__dirname, 'ai_command_processor.py'), 'process-unit']);
        
        let result = '';
        let error = '';
        
        python.stdout.on('data', (data) => {
            result += data.toString();
        });
        
        python.stderr.on('data', (data) => {
            error += data.toString();
        });
        
        python.on('close', (code) => {
            if (code !== 0) {
                console.error('GPT processing error:', error);
                res.status(500).json({ error: 'Failed to process unit' });
            } else {
                try {
                    const processedData = JSON.parse(result);
                    res.json(processedData);
                } catch (parseError) {
                    console.error('Failed to parse process response:', parseError);
                    res.status(500).json({ error: 'Invalid process response' });
                }
            }
        });
        
        // Send input to Python script
        python.stdin.write(JSON.stringify({ unit, instruction, originalCommand, context, isCorrection }));
        python.stdin.end();
        
    } catch (error) {
        console.error('GPT unit processing error:', error);
        res.status(500).json({ error: 'Failed to process unit' });
    }
});

app.post('/api/gemini-review', async (req, res) => {
    try {
        const { command, originalUnits, processedUnits, executionPlan } = req.body;
        
        // Call Python script for Gemini review
        const { spawn } = require('child_process');
        const python = spawn('python3', [path.join(__dirname, 'gemini_orchestration.py'), 'review']);
        
        let result = '';
        let error = '';
        
        python.stdout.on('data', (data) => {
            result += data.toString();
        });
        
        python.stderr.on('data', (data) => {
            error += data.toString();
        });
        
        python.on('close', (code) => {
            if (code !== 0) {
                console.error('Gemini review error:', error);
                res.status(500).json({ error: 'Failed to review changes' });
            } else {
                try {
                    const reviewData = JSON.parse(result);
                    res.json(reviewData);
                } catch (parseError) {
                    console.error('Failed to parse review response:', parseError);
                    res.status(500).json({ error: 'Invalid review response' });
                }
            }
        });
        
        // Send input to Python script
        python.stdin.write(JSON.stringify({ command, originalUnits, processedUnits, executionPlan }));
        python.stdin.end();
        
    } catch (error) {
        console.error('Gemini review error:', error);
        res.status(500).json({ error: 'Failed to review changes' });
    }
});

// Blueprint to text generation endpoint using Claude Opus 4
app.post('/api/blueprint-to-text', async (req, res) => {
    try {
        const { blueprint, prompt, useExtendedThinking } = req.body;
        
        if (!blueprint || !prompt) {
            return res.status(400).json({ error: 'Blueprint and prompt are required' });
        }
        
        console.log('Generating text from blueprint with Claude Opus 4...');
        
        // Call Python script for Claude Opus 4 processing
        const { spawn } = require('child_process');
        const pythonScript = path.join(__dirname, 'claude_opus_processor.py');
        const python = spawn('python3', [pythonScript]);
        
        let result = '';
        let error = '';
        
        python.stdout.on('data', (data) => {
            result += data.toString();
        });
        
        python.stderr.on('data', (data) => {
            error += data.toString();
        });
        
        python.on('close', (code) => {
            if (code !== 0) {
                console.error('Claude Opus 4 processing error:', error);
                res.status(500).json({ error: 'Failed to generate text from blueprint' });
            } else {
                try {
                    const responseData = JSON.parse(result);
                    res.json({
                        success: true,
                        content: responseData.content,
                        thinking: responseData.thinking || null
                    });
                } catch (parseError) {
                    console.error('Failed to parse Claude response:', parseError);
                    res.status(500).json({ error: 'Invalid response from Claude' });
                }
            }
        });
        
        // Send input to Python script
        python.stdin.write(JSON.stringify({
            blueprint: blueprint,
            prompt: prompt,
            useExtendedThinking: useExtendedThinking
        }));
        python.stdin.end();
        
    } catch (error) {
        console.error('Blueprint to text error:', error);
        res.status(500).json({ error: 'Failed to process blueprint' });
    }
});

// Entity extraction endpoint
app.post('/api/extract-entities', async (req, res) => {
    console.log('Entity extraction request received');
    console.log('Content length:', req.body.content ? req.body.content.length : 0);
    try {
        const { content } = req.body;
        const { spawn } = require('child_process');
        
        // Call Python entity extraction service with environment
        const env = { ...process.env };
        // Ensure OpenAI API key is passed
        if (process.env.OPENAI_API_KEY) {
            env.OPENAI_API_KEY = process.env.OPENAI_API_KEY;
        }
        
        const python = spawn('python3', [path.join(__dirname, 'entity_extraction_service.py')], {
            env: env
        });
        
        let result = '';
        let error = '';
        
        python.stdout.on('data', (data) => {
            result += data.toString();
        });
        
        python.stderr.on('data', (data) => {
            error += data.toString();
            console.error('Entity extraction stderr:', data.toString());
        });
        
        // Add timeout
        const timeout = setTimeout(() => {
            python.kill();
            console.error('Entity extraction timeout');
            res.status(500).json({ error: 'Entity extraction timeout' });
        }, 30000); // 30 second timeout
        
        python.on('close', (code) => {
            clearTimeout(timeout);
            console.log('Entity extraction closed with code:', code);
            if (code !== 0 || error) {
                console.error('Entity extraction error:', error);
                res.status(500).json({ error: 'Failed to extract entities' });
            } else {
                try {
                    const response = JSON.parse(result);
                    res.json(response);
                } catch (e) {
                    console.error('Failed to parse entity response:', result);
                    res.status(500).json({ error: 'Failed to parse entity response' });
                }
            }
        });
        
        // Send input to Python script
        python.stdin.write(JSON.stringify({ 
            content: content,
            command: 'extract' 
        }));
        python.stdin.end();
        
    } catch (error) {
        console.error('Entity extraction error:', error);
        res.status(500).json({ error: 'Failed to extract entities' });
    }
});

app.listen(PORT, () => {
    console.log(`EDITh server running on http://localhost:${PORT}`);
});