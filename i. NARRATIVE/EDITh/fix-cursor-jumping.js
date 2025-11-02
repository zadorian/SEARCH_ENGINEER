// Fix for cursor jumping issue in EDITh editor
// This script disables problematic event handlers that interfere with typing

(function() {
    console.log(' Fixing cursor jumping issue...');
    
    // 1. Disable wiki link auto-completion
    if (window.app && window.app.editor) {
        const editor = window.app.editor;
        
        // Clone the editor to remove all event listeners
        const newEditor = editor.cloneNode(true);
        editor.parentNode.replaceChild(newEditor, editor);
        window.app.editor = newEditor;
        
        // Re-attach only essential event listeners
        newEditor.addEventListener('input', () => {
            // Only schedule auto-save, don't do any DOM manipulation
            if (window.app.scheduleAutoSave) {
                window.app.scheduleAutoSave();
            }
        });
        
        console.log(' Removed problematic input handlers from main editor');
    }
    
    // 2. Disable SmartGapFiller if it exists
    if (window.app && window.app.smartGapFiller) {
        // Remove the global input listener
        document.removeEventListener('input', window.app.smartGapFiller.handleInput);
        
        // Disable the SmartGapFiller
        window.app.smartGapFiller.isProcessing = true; // Prevent it from processing
        window.app.smartGapFiller = null;
        
        console.log(' Disabled SmartGapFiller');
    }
    
    // 3. Clear any active timers
    if (window.app) {
        if (window.app.typingTimer) {
            clearTimeout(window.app.typingTimer);
            window.app.typingTimer = null;
        }
        if (window.app.punctuationTimeout) {
            clearTimeout(window.app.punctuationTimeout);
            window.app.punctuationTimeout = null;
        }
        console.log(' Cleared active timers');
    }
    
    // 4. Disable the wiki autocomplete feature
    if (window.app) {
        window.app.wikiAutocompleteActive = false;
        const autocomplete = document.querySelector('.wiki-autocomplete');
        if (autocomplete) {
            autocomplete.remove();
        }
    }
    
    console.log('🎉 Cursor jumping fix applied!');
    console.log('Note: Some features like wiki links [[]] and gap filling have been disabled.');
    console.log('To restore full functionality, refresh the page.');
    
})();