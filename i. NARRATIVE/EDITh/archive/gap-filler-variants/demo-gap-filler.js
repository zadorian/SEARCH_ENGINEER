javascript:(function(){
    const editor = document.getElementById('main-text-editor');
    if (editor) {
        // Clear and focus
        editor.value = '';
        editor.focus();
        
        // Type a test sentence
        const text = 'The president of the US today is called [?].';
        let i = 0;
        
        function typeChar() {
            if (i < text.length) {
                editor.value += text[i];
                i++;
                
                // Trigger input event on the last character
                if (i === text.length) {
                    editor.dispatchEvent(new Event('input', {bubbles: true}));
                }
                
                setTimeout(typeChar, 50);
            }
        }
        
        typeChar();
    } else {
        alert('Editor not found!');
    }
})();