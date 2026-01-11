/**
 * Entity Recognition System for Corporella Claude
 * Detects and marks: Companies, People, Addresses, Emails, Phone Numbers
 */

class EntityRecognizer {
    constructor() {
        // Regex patterns for entity detection
        this.patterns = {
            email: /\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b/g,
            phone: /\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b/g,
            ukPhone: /\b(?:\+?44[-.\s]?|0)(?:\d{4}[-.\s]?\d{6}|\d{3}[-.\s]?\d{3}[-.\s]?\d{4})\b/g,

            // Common address patterns
            address: /\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*(?:\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr|Court|Ct|Place|Pl|Square|Sq|Terrace|Way))[,\s]+[A-Z][a-z]+(?:[,\s]+[A-Z]{2})?\s+\d{5}(?:-\d{4})?\b/gi,
            ukAddress: /\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*[,\s]+[A-Z][a-z]+[,\s]+[A-Z]{1,2}\d{1,2}\s*\d[A-Z]{2}\b/gi,

            // Company suffixes
            companySuffixes: /\b(?:Ltd|Limited|LLC|Inc|Corp|Corporation|PLC|LLP|LP|GmbH|S\.A\.|AG|B\.V\.|S\.L\.|Pty|Co\.)\b/gi,

            // Person name patterns (simplified - will enhance with NLP if needed)
            personName: /\b(?:Mr|Mrs|Ms|Dr|Prof|Sir|Dame|Lord|Lady)\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b/g,
            capitalizedName: /\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b/g
        };

        // Entity type tracking
        this.detectedEntities = {
            companies: new Set(),
            people: new Set(),
            addresses: new Set(),
            emails: new Set(),
            phones: new Set()
        };
    }

    /**
     * Main detection method - analyzes text and returns marked-up HTML
     */
    detectAndMark(text, fieldName = '') {
        if (!text || typeof text !== 'string') {
            return text;
        }

        let markedText = text;
        const entities = [];

        // 1. Detect and mark emails
        markedText = markedText.replace(this.patterns.email, (match) => {
            entities.push({ type: 'email', value: match });
            this.detectedEntities.emails.add(match);
            return this.wrapEntity(match, 'email');
        });

        // 2. Detect and mark phone numbers
        markedText = markedText.replace(this.patterns.phone, (match) => {
            entities.push({ type: 'phone', value: match });
            this.detectedEntities.phones.add(match);
            return this.wrapEntity(match, 'phone');
        });

        markedText = markedText.replace(this.patterns.ukPhone, (match) => {
            entities.push({ type: 'phone', value: match });
            this.detectedEntities.phones.add(match);
            return this.wrapEntity(match, 'phone');
        });

        // 3. Detect and mark addresses
        markedText = markedText.replace(this.patterns.address, (match) => {
            entities.push({ type: 'address', value: match });
            this.detectedEntities.addresses.add(match);
            return this.wrapEntity(match, 'address');
        });

        markedText = markedText.replace(this.patterns.ukAddress, (match) => {
            entities.push({ type: 'address', value: match });
            this.detectedEntities.addresses.add(match);
            return this.wrapEntity(match, 'address');
        });

        // 4. Detect and mark companies (by suffix)
        markedText = markedText.replace(this.patterns.companySuffixes, (match, offset, string) => {
            // Get the full company name (including words before the suffix)
            const before = string.substring(0, offset);
            const words = before.split(/\s+/);
            const companyWords = [];

            // Grab capitalized words before the suffix
            for (let i = words.length - 1; i >= 0 && i >= words.length - 5; i--) {
                if (/^[A-Z]/.test(words[i])) {
                    companyWords.unshift(words[i]);
                } else {
                    break;
                }
            }

            const fullCompany = companyWords.join(' ') + ' ' + match;
            entities.push({ type: 'company', value: fullCompany });
            this.detectedEntities.companies.add(fullCompany);

            return match; // Don't wrap here - will be wrapped by full name
        });

        // 5. Detect people (by field name hints)
        if (this.isPersonField(fieldName)) {
            markedText = markedText.replace(this.patterns.personName, (match) => {
                entities.push({ type: 'person', value: match });
                this.detectedEntities.people.add(match);
                return this.wrapEntity(match, 'person');
            });

            markedText = markedText.replace(this.patterns.capitalizedName, (match) => {
                // Avoid false positives by checking if already wrapped
                if (!match.includes('<span')) {
                    entities.push({ type: 'person', value: match });
                    this.detectedEntities.people.add(match);
                    return this.wrapEntity(match, 'person');
                }
                return match;
            });
        }

        // 6. Detect and wrap URLs (for website field) - white background, black text
        if (fieldName.toLowerCase().includes('website') || fieldName.toLowerCase().includes('url')) {
            // Match URLs that aren't already wrapped
            const urlPattern = /(?<!href=["']|class=["'][^"']*["']>)(https?:\/\/[^\s<]+)/gi;
            markedText = markedText.replace(urlPattern, (match) => {
                return this.wrapURL(match);
            });
        }

        // 7. Wrap jurisdiction values (if field is jurisdiction) - white background, black text
        if (fieldName.toLowerCase() === 'jurisdiction' && markedText && !markedText.includes('<span')) {
            markedText = this.wrapJurisdiction(markedText);
        }

        return markedText;
    }

    /**
     * Check if field name suggests it contains person data
     */
    isPersonField(fieldName) {
        const personFields = [
            'officer', 'director', 'secretary', 'shareholder', 'owner',
            'contact', 'agent', 'representative', 'person', 'name',
            'ceo', 'cfo', 'cto', 'president', 'manager', 'beneficiary'
        ];

        const lowerField = fieldName.toLowerCase();
        return personFields.some(term => lowerField.includes(term));
    }

    /**
     * Wrap entity in styled span with data attributes
     */
    wrapEntity(text, type) {
        const typeIcons = {
            company: '🏢',
            person: '👤',
            address: '📍',
            email: '📧',
            phone: '📞'
        };

        // NO ICONS - just clean badges
        return `<span class="entity-badge entity-${type}" data-entity-type="${type}" data-entity-value="${this.escapeHtml(text)}">${this.escapeHtml(text)}</span>`;
    }

    /**
     * Detect entities in structured data (objects, arrays)
     */
    detectInData(data, fieldName = '') {
        if (!data) return data;

        // Handle strings
        if (typeof data === 'string') {
            return this.detectAndMark(data, fieldName);
        }

        // Handle arrays
        if (Array.isArray(data)) {
            return data.map((item, index) =>
                this.detectInData(item, `${fieldName}[${index}]`)
            );
        }

        // Handle objects
        if (typeof data === 'object') {
            const result = {};
            for (const [key, value] of Object.entries(data)) {
                result[key] = this.detectInData(value, key);
            }
            return result;
        }

        return data;
    }

    /**
     * Get all detected entities by type
     */
    getDetectedEntities(type = null) {
        if (type) {
            return Array.from(this.detectedEntities[type] || []);
        }

        return {
            companies: Array.from(this.detectedEntities.companies),
            people: Array.from(this.detectedEntities.people),
            addresses: Array.from(this.detectedEntities.addresses),
            emails: Array.from(this.detectedEntities.emails),
            phones: Array.from(this.detectedEntities.phones)
        };
    }

    /**
     * Clear detected entities
     */
    clear() {
        this.detectedEntities = {
            companies: new Set(),
            people: new Set(),
            addresses: new Set(),
            emails: new Set(),
            phones: new Set()
        };
    }

    /**
     * HTML escape utility
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Setup click handlers for entity badges
     */
    setupClickHandlers() {
        document.addEventListener('click', (e) => {
            const badge = e.target.closest('.entity-badge');
            if (!badge) return;

            const entityType = badge.dataset.entityType;
            const entityValue = badge.dataset.entityValue;

            this.handleEntityClick(entityType, entityValue, badge);
        });
    }

    /**
     * Handle entity badge click
     */
    handleEntityClick(type, value, element) {
        console.log(`Entity clicked: ${type} = "${value}"`);

        // Add visual feedback
        element.classList.add('entity-clicked');
        setTimeout(() => element.classList.remove('entity-clicked'), 300);

        // Trigger custom event for future profile opening
        const event = new CustomEvent('entityClicked', {
            detail: { type, value, element },
            bubbles: true
        });
        element.dispatchEvent(event);

        // TODO: Future implementation - open entity profile
        // For now, just highlight
        this.highlightRelatedEntities(type, value);
    }

    /**
     * Highlight all occurrences of the same entity
     */
    highlightRelatedEntities(type, value) {
        const badges = document.querySelectorAll(`.entity-${type}[data-entity-value="${value}"]`);
        badges.forEach(badge => {
            badge.classList.add('entity-highlighted');
            setTimeout(() => badge.classList.remove('entity-highlighted'), 2000);
        });
    }

    /**
     * Wrap URL in website badge (white background, black text)
     */
    wrapURL(url) {
        return `<a href="${this.escapeHtml(url)}" class="website-badge" target="_blank" rel="noopener noreferrer">${this.escapeHtml(url)}</a>`;
    }

    /**
     * Wrap jurisdiction in jurisdiction badge (white background, black text)
     */
    wrapJurisdiction(jurisdiction) {
        return `<span class="jurisdiction-badge">${this.escapeHtml(jurisdiction)}</span>`;
    }
}

// Export for use in main application
window.EntityRecognizer = EntityRecognizer;

// Auto-initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (!window.entityRecognizer) {
        window.entityRecognizer = new EntityRecognizer();
        window.entityRecognizer.setupClickHandlers();
        console.log('✅ Entity Recognizer initialized');
    }
});
