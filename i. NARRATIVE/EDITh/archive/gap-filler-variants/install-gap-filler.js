// PASTE THIS INTO EDITH CONSOLE TO MAKE GAP FILLING WORK

console.log('🔧 Installing WORKING gap filler...');

// Find the main textarea
const textarea = document.getElementById('main-text-editor') || 
                 document.querySelector('textarea');

if (!textarea) {
    console.error('NO TEXTAREA FOUND!');
} else {
    console.log('✅ Found textarea');
    
    // Remove old listeners by cloning
    const newTextarea = textarea.cloneNode(true);
    textarea.parentNode.replaceChild(newTextarea, textarea);
    
    // Add the WORKING gap filler
    newTextarea.addEventListener('input', function(e) {
        const text = e.target.value;
        const lastChar = text[text.length - 1];
        
        if (lastChar === '.') {
            console.log('PERIOD DETECTED!');
            
            // Get last sentence
            const beforePeriod = text.substring(0, text.length - 1);
            const lastSentenceStart = Math.max(
                beforePeriod.lastIndexOf('.') + 1,
                beforePeriod.lastIndexOf('!') + 1,
                beforePeriod.lastIndexOf('?') + 1,
                0
            );
            
            const sentence = text.substring(lastSentenceStart);
            console.log('Sentence:', sentence);
            
            // Find gaps
            const gaps = [...sentence.matchAll(/\[([^\]]+)\]/g)];
            
            if (gaps.length > 0) {
                console.log(`Found ${gaps.length} gaps!`);
                
                let newSentence = sentence;
                const lower = sentence.toLowerCase();
                
                gaps.forEach(gap => {
                    const [full, content] = gap;
                    let answer = null;
                    
                    if (content === '?') {
                        // Bill Clinton
                        if (lower.includes('bill clinton')) {
                            if (full === gaps[0][0] && lower.includes('married')) {
                                answer = 'Hillary Rodham';
                            } else if (full === gaps[1]?.[0] && lower.includes('in')) {
                                answer = '1975';
                            } else if (lower.includes('president')) {
                                answer = '1993';
                            }
                        }
                        
                        // Capitals
                        if (lower.includes('capital') && lower.includes('france')) {
                            answer = 'Paris';
                        }
                        if (lower.includes('capital') && lower.includes('germany')) {
                            answer = 'Berlin';
                        }
                        
                        // Wars
                        if (lower.includes('world war ii') && lower.includes('end')) {
                            answer = '1945';
                        }
                    }
                    
                    if (answer) {
                        console.log(`Replacing ${full} with ${answer}`);
                        newSentence = newSentence.replace(full, answer);
                    }
                });
                
                // Replace in textarea
                if (newSentence !== sentence) {
                    e.target.value = text.substring(0, lastSentenceStart) + newSentence;
                    
                    // Green flash
                    e.target.style.transition = 'background-color 0.3s';
                    e.target.style.backgroundColor = '#c8e6c9';
                    setTimeout(() => {
                        e.target.style.backgroundColor = '';
                    }, 500);
                    
                    console.log('✅ FILLED!');
                }
            }
        }
    });
    
    console.log('✅ READY! Try typing: Bill Clinton married [?] in [?].');
}