// TORPEDO Crawl Visualization
class TorpedoViz {
    constructor(container) {
        this.container = container;
        this.nodes = new Map(); // url -> {x, y, extractions, parent}
        this.edges = [];
        this.nodeId = 0;
        this.width = container.clientWidth || 800;
        this.height = 400;
        this.tooltip = null;
        this.init();
    }
    
    init() {
        this.container.innerHTML = `
            <svg id="torpedo-svg" width="100%" height="400" style="background:#0a0a12;border-radius:4px;">
                <defs>
                    <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="#4a9eff"/>
                    </marker>
                </defs>
                <g id="edges"></g>
                <g id="nodes"></g>
            </svg>
            <div id="torpedo-tooltip" style="display:none;position:absolute;background:#1a1a25;border:1px solid #4a9eff;border-radius:4px;padding:8px;font-size:11px;max-width:300px;z-index:1000;color:#e0e0e0;"></div>
        `;
        this.svg = this.container.querySelector("#torpedo-svg");
        this.edgesG = this.container.querySelector("#edges");
        this.nodesG = this.container.querySelector("#nodes");
        this.tooltip = this.container.querySelector("#torpedo-tooltip");
    }
    
    formatUrl(url) {
        return url.replace(/^https?:\/\/(www\.)?/, "").substring(0, 50);
    }
    
    addNode(url, parent, extractions = []) {
        if (this.nodes.has(url)) {
            // Update extractions
            const node = this.nodes.get(url);
            node.extractions = [...node.extractions, ...extractions];
            this.updateNode(url);
            return;
        }
        
        const parentNode = parent ? this.nodes.get(parent) : null;
        const level = parentNode ? parentNode.level + 1 : 0;
        const siblings = [...this.nodes.values()].filter(n => n.level === level).length;
        
        const x = 50 + level * 150;
        const y = 50 + siblings * 50;
        
        this.nodes.set(url, {
            id: this.nodeId++,
            url,
            x,
            y,
            level,
            extractions,
            parent
        });
        
        if (parent && this.nodes.has(parent)) {
            this.edges.push({from: parent, to: url});
        }
        
        this.render();
    }
    
    updateNode(url) {
        this.render();
    }
    
    render() {
        // Clear
        this.edgesG.innerHTML = "";
        this.nodesG.innerHTML = "";
        
        // Draw edges
        this.edges.forEach(e => {
            const from = this.nodes.get(e.from);
            const to = this.nodes.get(e.to);
            if (from && to) {
                const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                line.setAttribute("x1", from.x + 60);
                line.setAttribute("y1", from.y + 12);
                line.setAttribute("x2", to.x - 5);
                line.setAttribute("y2", to.y + 12);
                line.setAttribute("stroke", "#4a9eff");
                line.setAttribute("stroke-width", "1");
                line.setAttribute("marker-end", "url(#arrow)");
                this.edgesG.appendChild(line);
            }
        });
        
        // Draw nodes
        this.nodes.forEach((node, url) => {
            const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
            g.setAttribute("transform", `translate(${node.x},${node.y})`);
            
            // Capsule background
            const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
            rect.setAttribute("width", "120");
            rect.setAttribute("height", "24");
            rect.setAttribute("rx", "12");
            rect.setAttribute("fill", "#1a1a25");
            rect.setAttribute("stroke", "#3a3a4a");
            rect.setAttribute("stroke-width", "1");
            g.appendChild(rect);
            
            // URL text
            const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
            text.setAttribute("x", "8");
            text.setAttribute("y", "16");
            text.setAttribute("fill", "#e0e0e0");
            text.setAttribute("font-size", "9");
            text.setAttribute("font-family", "monospace");
            text.textContent = this.formatUrl(url);
            g.appendChild(text);
            
            // Extraction count badge
            if (node.extractions.length > 0) {
                const badge = document.createElementNS("http://www.w3.org/2000/svg", "circle");
                badge.setAttribute("cx", "115");
                badge.setAttribute("cy", "12");
                badge.setAttribute("r", "10");
                badge.setAttribute("fill", this.getBadgeColor(node.extractions.length));
                g.appendChild(badge);
                
                const count = document.createElementNS("http://www.w3.org/2000/svg", "text");
                count.setAttribute("x", "115");
                count.setAttribute("y", "16");
                count.setAttribute("text-anchor", "middle");
                count.setAttribute("fill", "#fff");
                count.setAttribute("font-size", "9");
                count.setAttribute("font-weight", "bold");
                count.textContent = node.extractions.length;
                g.appendChild(count);
            }
            
            // Hover events
            g.style.cursor = "pointer";
            g.addEventListener("mouseenter", (e) => this.showTooltip(e, node));
            g.addEventListener("mouseleave", () => this.hideTooltip());
            
            this.nodesG.appendChild(g);
        });
        
        // Adjust SVG viewBox
        const maxX = Math.max(...[...this.nodes.values()].map(n => n.x)) + 150;
        const maxY = Math.max(...[...this.nodes.values()].map(n => n.y)) + 50;
        this.svg.setAttribute("viewBox", `0 0 ${Math.max(maxX, 800)} ${Math.max(maxY, 400)}`);
    }
    
    getBadgeColor(count) {
        if (count >= 10) return "#22c55e"; // green
        if (count >= 5) return "#eab308";  // yellow
        if (count >= 1) return "#4a9eff";  // blue
        return "#666";
    }
    
    showTooltip(event, node) {
        let html = `<strong>${node.url}</strong><br><br>`;
        if (node.extractions.length > 0) {
            html += `<strong>Extractions (${node.extractions.length}):</strong><br>`;
            node.extractions.slice(0, 10).forEach(e => {
                html += `<div style="margin:2px 0;padding:2px 4px;background:#0a0a12;border-radius:2px;">`;
                html += `<span style="color:${this.getTypeColor(e.type)}">${e.type}</span>: ${e.value}`;
                html += `</div>`;
            });
            if (node.extractions.length > 10) {
                html += `<div style="color:#888">...and ${node.extractions.length - 10} more</div>`;
            }
        } else {
            html += `<span style="color:#888">No extractions</span>`;
        }
        
        this.tooltip.innerHTML = html;
        this.tooltip.style.display = "block";
        this.tooltip.style.left = (event.pageX + 10) + "px";
        this.tooltip.style.top = (event.pageY + 10) + "px";
    }
    
    hideTooltip() {
        this.tooltip.style.display = "none";
    }
    
    getTypeColor(type) {
        const colors = {
            person: "#22c55e",
            company: "#4a9eff",
            email: "#eab308",
            phone: "#f97316",
            address: "#a855f7",
            lei: "#06b6d4",
            iban: "#ec4899"
        };
        return colors[type?.toLowerCase()] || "#888";
    }
    
    clear() {
        this.nodes.clear();
        this.edges = [];
        this.nodeId = 0;
        this.render();
    }
}

// Global instance
let torpedoViz = null;

function initTorpedoViz() {
    const container = document.getElementById("torpedo-viz-container");
    if (container && !torpedoViz) {
        torpedoViz = new TorpedoViz(container);
    }
    return torpedoViz;
}
