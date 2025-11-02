// This file shows the fixes needed for keyboard shortcuts

// In EditorEnhancements.js, the setupKeyboardShortcuts method needs to be fixed:

setupKeyboardShortcuts() {
    // Use capture phase to ensure we get the events first
    document.addEventListener('keydown', (e) => {
        // For Mac, use metaKey; for Windows/Linux, use ctrlKey
        const cmdKey = e.metaKey || e.ctrlKey;
        
        // Debug log
        console.log('Key pressed:', e.key, 'Cmd/Ctrl:', cmdKey, 'Shift:', e.shiftKey);
        
        // Quick Tag: Cmd/Ctrl + T (without Shift)
        if (cmdKey && !e.shiftKey && e.key.toLowerCase() === 't') {
            e.preventDefault();
            e.stopPropagation();
            console.log('Quick tag triggered!');
            this.quickTag();
            return false;
        }
        
        // Toggle tag visibility: Cmd/Ctrl + Shift + T
        if (cmdKey && e.shiftKey && e.key.toLowerCase() === 't') {
            e.preventDefault();
            e.stopPropagation();
            console.log('Toggle tags triggered!');
            this.tagManager.toggleTagVisibility();
            return false;
        }
        
        // Show version history: Cmd/Ctrl + Shift + H
        if (cmdKey && e.shiftKey && e.key.toLowerCase() === 'h') {
            e.preventDefault();
            e.stopPropagation();
            console.log('Show history triggered!');
            this.showVersionHistory();
            return false;
        }
        
        // Save version: Cmd/Ctrl + Shift + S
        if (cmdKey && e.shiftKey && e.key.toLowerCase() === 's') {
            e.preventDefault();
            e.stopPropagation();
            console.log('Save version triggered!');
            this.versionHistory.createVersion('manual');
            this.showNotification('Version saved!');
            return false;
        }
    }, true); // Use capture phase!
}

// The quickTag method should select text first if nothing is selected:
quickTag() {
    const selection = window.getSelection();
    
    // If no text selected, select the word at cursor
    if (!selection.toString().trim()) {
        // Try to select current word
        const range = selection.getRangeAt(0);
        const node = range.startContainer;
        
        if (node.nodeType === Node.TEXT_NODE) {
            const text = node.textContent;
            const offset = range.startOffset;
            
            // Find word boundaries
            let start = offset;
            let end = offset;
            
            while (start > 0 && /\w/.test(text[start - 1])) start--;
            while (end < text.length && /\w/.test(text[end])) end++;
            
            if (start < end) {
                range.setStart(node, start);
                range.setEnd(node, end);
                selection.removeAllRanges();
                selection.addRange(range);
            }
        }
    }
    
    // Now show tagging UI
    if (selection.toString().trim()) {
        this.tagManager.showTaggingOptions(selection);
    } else {
        this.showNotification('Select text to tag');
    }
}
