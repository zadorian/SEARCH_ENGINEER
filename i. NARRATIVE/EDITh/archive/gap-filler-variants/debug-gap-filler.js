// EMERGENCY DEBUG SCRIPT - Paste this in EDITh console NOW!
console.log('🔍 DEBUGGING GAP FILLER...');

// Check if SmartGapFiller exists
console.log('1. SmartGapFiller exists?', typeof window.app?.smartGapFiller);

// Check the main editor
const mainEditor = document.getElementById('main-text-editor');
console.log('2. Main editor found?', !!mainEditor);

// Force attach listener
if (mainEditor) {
    console.log('3. Forcing listener attachment...');
    
    // Remove any existing listeners
    const newEditor = mainEditor.cloneNode(true);
    mainEditor.parentNode.replaceChild(newEditor, mainEditor);
    
    let processingFlag = false;
    
    // Add debug listener
    newEditor.addEventListener('input', function(e) {
        const text = e.target.value;
        console.log('🎯 Input detected, last char:', text[text.length - 1]);
        
        if (processingFlag) return;
        
        // Check for sentence end
        if (/[.!?]$/.test(text)) {
            console.log('📍 Sentence end detected!');
            
            // Look for gaps
            const gaps = text.match(/\[([^\]]*)\]/g);
            if (gaps) {
                console.log('✅ GAPS FOUND:', gaps);
                processingFlag = true;
                
                // Extract last sentence
                const sentences = text.split(/[.!?]/);
                const lastSentence = sentences[sentences.length - 2] + text[text.length - 1];
                console.log('📝 Last sentence:', lastSentence);
                
                // Find gaps in last sentence
                const sentenceGaps = lastSentence.match(/\[([^\]]*)\]/g);
                if (sentenceGaps) {
                    console.log('🎉 PROCESSING GAPS:', sentenceGaps);
                    
                    // Visual feedback
                    e.target.style.backgroundColor = 'rgba(52, 211, 153, 0.2)';
                    
                    // Replace gaps (mock)
                    let newSentence = lastSentence;
                    sentenceGaps.forEach((gap, i) => {
                        const replacement = gap.includes('?') ? `[ANSWER ${i+1}]` : `[${gap.slice(1,-1)} FILLED]`;
                        newSentence = newSentence.replace(gap, replacement);
                    });
                    
                    // Update text
                    const beforeLastSentence = text.substring(0, text.lastIndexOf(lastSentence));
                    e.target.value = beforeLastSentence + newSentence;
                    
                    setTimeout(() => {
                        e.target.style.backgroundColor = '';
                        processingFlag = false;
                    }, 1000);
                }
            }
        }
    });
    
    console.log('✅ DEBUG LISTENER ATTACHED!');
    console.log('Try typing: The capital of France is [?].');
} else {
    console.error('❌ NO MAIN EDITOR FOUND!');
    
    // Try to find any textarea
    const anyTextarea = document.querySelector('textarea');
    console.log('Any textarea found?', !!anyTextarea);
    if (anyTextarea) {
        console.log('Textarea ID:', anyTextarea.id);
        console.log('Textarea classes:', anyTextarea.className);
    }
}

// Check if SmartGapFiller initialized
if (window.app && window.app.smartGapFiller) {
    console.log('4. SmartGapFiller initialized:', window.app.smartGapFiller);
    console.log('5. isProcessing:', window.app.smartGapFiller.isProcessing);
} else {
    console.error('❌ SmartGapFiller NOT initialized!');
}

console.log('🎯 DEBUG COMPLETE - Try typing now!');