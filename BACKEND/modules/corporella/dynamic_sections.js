/**
 * Dynamic Section & Button Rendering System for Corporella Claude
 * Inspired by hierarchical operator buttons with animations
 */

class DynamicSectionManager {
    constructor() {
        this.sections = new Map();
        this.activeSection = null;
        this.animationDelay = 50; // ms between button animations
    }

    /**
     * Register a dynamic section with its data sources
     */
    registerSection(sectionId, config) {
        this.sections.set(sectionId, {
            id: sectionId,
            label: config.label,
            icon: config.icon || '📚',
            sources: config.sources || [],
            children: config.children || null,
            isVisible: false,
            container: null
        });
    }

    /**
     * Context detection - determines which sections should be visible
     * based on entity data
     */
    detectContext(entity) {
        const context = {
            hasJurisdiction: !!(entity?.about?.jurisdiction),
            hasCorporateRegistry: !!(entity?.about?._corporate_registry_sources),
            hasLitigation: !!(entity?.compliance?.litigation?._wiki_sources),
            hasRegulatory: !!(entity?.compliance?.regulatory?._wiki_sources),
            hasReputation: !!(entity?.compliance?.reputation?._wiki_sources),
            hasOther: !!(entity?.compliance?.other?._wiki_sources),
            jurisdiction: entity?.about?.jurisdiction || null
        };
        return context;
    }

    /**
     * Render dynamic buttons with staggered animation
     * Similar to the operator button pattern
     */
    renderDynamicButtons(containerId, sources, options = {}) {
        const container = document.getElementById(containerId);
        if (!container || !sources || sources.length === 0) return;

        // Clear existing content
        container.innerHTML = '';

        // Add section label if provided
        if (options.label) {
            const labelDiv = document.createElement('div');
            labelDiv.className = 'section-label';
            labelDiv.innerHTML = `${options.label}:`; // NO ICONS
            container.appendChild(labelDiv);
        }

        // Create button container
        const buttonContainer = document.createElement('div');
        buttonContainer.className = 'button-grid';
        container.appendChild(buttonContainer);

        // Render buttons with staggered animation
        sources.forEach((source, index) => {
            // Create button wrapper
            const wrapper = document.createElement('div');
            wrapper.className = 'button-wrapper';
            wrapper.style.opacity = '0';
            wrapper.style.transform = 'translateY(-10px) scale(0.9)';

            // Create button
            const button = document.createElement('a');
            button.className = 'dynamic-source-btn';
            button.href = source.url;
            button.target = '_blank';
            button.rel = 'noopener noreferrer';

            // NO ICONS - just title
            button.innerHTML = source.title;

            // Add tooltip
            button.title = source.url;

            // Handle click analytics (optional)
            button.addEventListener('click', () => {
                this.trackSourceClick(source);
            });

            wrapper.appendChild(button);
            buttonContainer.appendChild(wrapper);

            // Animate in with delay
            setTimeout(() => {
                wrapper.style.transition = 'all 0.3s ease-out';
                wrapper.style.opacity = '1';
                wrapper.style.transform = 'translateY(0) scale(1)';
            }, index * this.animationDelay);
        });

        // Add "show more" if there are many sources
        if (sources.length > 6 && options.collapsible) {
            this.addShowMoreButton(buttonContainer, sources);
        }
    }

    /**
     * Hierarchical section rendering (like primary/secondary operators)
     */
    renderHierarchicalSections(entity) {
        const context = this.detectContext(entity);

        // Primary sections (always visible if data exists)
        const primarySections = [
            {
                id: 'corporateRegistry',
                condition: context.hasCorporateRegistry,
                data: entity?.about?._corporate_registry_sources,
                config: {
                    label: 'Corporate Registry',
                    children: [
                        { label: 'Official Records', filter: 'official' },
                        { label: 'Third Party', filter: 'third-party' }
                    ]
                }
            },
            {
                id: 'litigation',
                condition: context.hasLitigation,
                data: entity?.compliance?.litigation?._wiki_sources,
                config: {
                    label: 'Litigation',
                    children: [
                        { label: 'Court Records', filter: 'court' },
                        { label: 'Case Law', filter: 'case-law' }
                    ]
                }
            },
            {
                id: 'regulatory',
                condition: context.hasRegulatory,
                data: entity?.compliance?.regulatory?._wiki_sources,
                config: {
                    label: 'Regulatory'
                }
            },
            {
                id: 'assets',
                condition: !!(entity?.compliance?.assets?._wiki_sources),
                data: entity?.compliance?.assets?._wiki_sources,
                config: {
                    label: 'Assets'
                }
            },
            {
                id: 'licensing',
                condition: !!(entity?.compliance?.licensing?._wiki_sources),
                data: entity?.compliance?.licensing?._wiki_sources,
                config: {
                    label: 'Licensing'
                }
            },
            {
                id: 'political',
                condition: !!(entity?.compliance?.political?._wiki_sources),
                data: entity?.compliance?.political?._wiki_sources,
                config: {
                    label: 'Political'
                }
            },
            {
                id: 'reputation',
                condition: context.hasReputation,
                data: entity?.compliance?.reputation?._wiki_sources,
                config: {
                    label: 'Media & Reputation'
                }
            },
            {
                id: 'breaches',
                condition: !!(entity?.compliance?.breaches?._wiki_sources),
                data: entity?.compliance?.breaches?._wiki_sources,
                config: {
                    label: 'Breaches'
                }
            },
            {
                id: 'other',
                condition: context.hasOther,
                data: entity?.compliance?.other?._wiki_sources,
                config: {
                    label: 'Further Public Records'
                }
            }
        ];

        // Render each section
        primarySections.forEach((section, sectionIndex) => {
            if (section.condition) {
                setTimeout(() => {
                    this.renderSection(section);
                }, sectionIndex * 100); // Stagger section appearance
            }
        });
    }

    /**
     * Render individual section with optional hierarchy
     */
    renderSection(section) {
        const container = document.getElementById(`${section.id}Sources`);
        if (!container) return;

        // Fade in container
        container.style.opacity = '0';
        container.style.transition = 'opacity 0.3s ease-in';

        if (section.config.children) {
            // Render with hierarchy (primary -> secondary)
            this.renderWithHierarchy(container, section);
        } else {
            // Render flat list
            this.renderDynamicButtons(section.id + 'Sources', section.data, {
                label: section.config.label,
                icon: section.config.icon
            });
        }

        // Fade in
        setTimeout(() => {
            container.style.opacity = '1';
        }, 50);
    }

    /**
     * Render hierarchical buttons (primary with expandable secondary)
     */
    renderWithHierarchy(container, section) {
        container.innerHTML = '';

        // Create primary container
        const primaryDiv = document.createElement('div');
        primaryDiv.className = 'primary-buttons';

        // Add section header
        const header = document.createElement('div');
        header.className = 'section-header';
        header.innerHTML = section.config.label; // NO ICONS
        primaryDiv.appendChild(header);

        // Group sources by category if children defined
        const categorized = this.categorizeSourcesByType(section.data);

        // Create expandable groups
        section.config.children.forEach((child, index) => {
            const filtered = categorized[child.filter] || [];
            if (filtered.length === 0) return;

            const groupDiv = document.createElement('div');
            groupDiv.className = 'source-group';

            // Create expandable header
            const groupHeader = document.createElement('div');
            groupHeader.className = 'group-header';
            groupHeader.innerHTML = `
                <span class="group-label">${child.label}</span>
                <span class="group-count">${filtered.length}</span>
                <span class="group-arrow">▶</span>
            `;
            groupHeader.style.cursor = 'pointer';

            // Create content container
            const groupContent = document.createElement('div');
            groupContent.className = 'group-content';
            groupContent.style.display = 'none';

            // Add click handler for expand/collapse
            groupHeader.addEventListener('click', () => {
                const isOpen = groupContent.style.display !== 'none';
                if (isOpen) {
                    groupContent.style.display = 'none';
                    groupHeader.querySelector('.group-arrow').innerHTML = '▶';
                } else {
                    groupContent.style.display = 'block';
                    groupHeader.querySelector('.group-arrow').innerHTML = '▼';
                    // Render buttons on first open
                    if (groupContent.children.length === 0) {
                        this.renderButtonsInContainer(groupContent, filtered);
                    }
                }
            });

            groupDiv.appendChild(groupHeader);
            groupDiv.appendChild(groupContent);

            // Animate in
            setTimeout(() => {
                groupDiv.style.opacity = '0';
                primaryDiv.appendChild(groupDiv);
                setTimeout(() => {
                    groupDiv.style.transition = 'opacity 0.3s ease-in';
                    groupDiv.style.opacity = '1';
                }, 50);
            }, index * 100);
        });

        container.appendChild(primaryDiv);
    }

    /**
     * Render buttons directly in a container
     */
    renderButtonsInContainer(container, sources) {
        sources.forEach((source, index) => {
            const button = document.createElement('a');
            button.className = 'dynamic-source-btn secondary';
            button.href = source.url;
            button.target = '_blank';
            button.innerHTML = source.title; // NO ICONS
            button.style.opacity = '0';
            button.style.transform = 'translateX(-20px)';

            container.appendChild(button);

            // Animate in
            setTimeout(() => {
                button.style.transition = 'all 0.2s ease-out';
                button.style.opacity = '1';
                button.style.transform = 'translateX(0)';
            }, index * 30);
        });
    }

    /**
     * Categorize sources by type for hierarchical display
     */
    categorizeSourcesByType(sources) {
        const categories = {
            'official': [],
            'third-party': [],
            'court': [],
            'case-law': [],
            'other': []
        };

        sources.forEach(source => {
            const title = source.title.toLowerCase();
            if (title.includes('companies house') || title.includes('registry')) {
                categories.official.push(source);
            } else if (title.includes('court') || title.includes('bailii')) {
                categories.court.push(source);
            } else if (title.includes('case') || title.includes('law')) {
                categories['case-law'].push(source);
            } else if (title.includes('occrp') || title.includes('duedil')) {
                categories['third-party'].push(source);
            } else {
                categories.other.push(source);
            }
        });

        return categories;
    }

    /**
     * Get appropriate icon for source type
     */
    getSourceIcon(source) {
        const title = source.title.toLowerCase();
        if (title.includes('companies house')) return '🏛️';
        if (title.includes('court')) return '⚖️';
        if (title.includes('occrp')) return '🔍';
        if (title.includes('charity')) return '❤️';
        if (title.includes('bailii')) return '📚';
        if (title.includes('github')) return '💻';
        if (title.includes('news')) return '📰';
        return '🔗';
    }

    /**
     * Track source clicks for analytics
     */
    trackSourceClick(source) {
        console.log('Source clicked:', source.title, source.url);
        // Could send to analytics service
    }

    /**
     * Add "Show More" functionality for long lists
     */
    addShowMoreButton(container, allSources) {
        const visibleCount = 6;
        const buttons = container.querySelectorAll('.button-wrapper');

        // Initially hide extras
        buttons.forEach((btn, i) => {
            if (i >= visibleCount) {
                btn.style.display = 'none';
            }
        });

        // Add show more button
        const showMoreBtn = document.createElement('button');
        showMoreBtn.className = 'show-more-btn';
        showMoreBtn.innerHTML = `Show ${allSources.length - visibleCount} more...`;
        showMoreBtn.onclick = () => {
            buttons.forEach(btn => {
                btn.style.display = 'block';
            });
            showMoreBtn.style.display = 'none';
        };

        container.appendChild(showMoreBtn);
    }
}

// Export for use in main application
window.DynamicSectionManager = DynamicSectionManager;