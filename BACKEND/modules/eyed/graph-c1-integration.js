// Cymonides-1 (C-1) Elasticsearch graph integration for EYE-D
// Provides a minimal bridge for loading/syncing vis.js nodes/edges to cymonides-1-{projectId}.

(function () {
    'use strict';

    let currentProjectId = null;
    let syncSuppressed = false;

    const positionQueue = new Map(); // nodeId -> {x, y, timer}
    const POSITION_SYNC_DEBOUNCE_MS = 500;

    async function fetchJson(url, options) {
        const resp = await fetch(url, options);
        const text = await resp.text();
        let data = null;
        try {
            data = text ? JSON.parse(text) : null;
        } catch (e) {
            throw new Error(`Invalid JSON from ${url}: ${text?.slice(0, 200)}`);
        }
        if (!resp.ok) {
            const msg = (data && (data.error || data.message)) || resp.statusText || 'Request failed';
            throw new Error(`${resp.status} ${msg}`);
        }
        return data;
    }

    function getCurrentProjectId() {
        return currentProjectId;
    }

    function isSyncSuppressed() {
        return syncSuppressed === true;
    }

    function setSyncSuppressed(value) {
        syncSuppressed = value === true;
    }

    async function initializeC1Integration(projectId, options = {}) {
        if (!projectId) return;

        currentProjectId = String(projectId);
        const limit = Number.isFinite(options.limit) ? options.limit : 2000;

        setSyncSuppressed(true);
        try {
            const data = await fetchJson(`/api/c1/export?projectId=${encodeURIComponent(currentProjectId)}&limit=${encodeURIComponent(limit)}`);
            const graphState = data?.graph_state || { nodes: [], edges: [] };

            if (typeof window.loadGraphState !== 'function') {
                throw new Error('loadGraphState(graphState) is not available');
            }

            window.loadGraphState(graphState);

            if (window.network && typeof window.network.fit === 'function') {
                setTimeout(() => {
                    try {
                        window.network.fit();
                    } catch (e) {
                        // ignore
                    }
                }, 250);
            }
        } finally {
            setSyncSuppressed(false);
        }
    }

    async function syncNodeToC1(node) {
        if (!currentProjectId) return;
        if (isSyncSuppressed()) return;
        if (!node || !node.id) return;

        const payload = {
            projectId: currentProjectId,
            node: {
                id: node.id,
                label: node.label,
                type: node.type,
                x: node.x,
                y: node.y,
                data: node.data,
                shape: node.shape,
            },
        };

        try {
            await fetchJson('/api/c1/sync-node', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        } catch (e) {
            console.error('[C-1] syncNodeToC1 failed:', e);
        }
    }

    async function syncEdgeToC1(edge) {
        if (!currentProjectId) return;
        if (isSyncSuppressed()) return;
        if (!edge || !edge.from || !edge.to) return;

        // Pull node snapshots from global vis.js datasets when available.
        const fromNode = window.nodes && typeof window.nodes.get === 'function' ? window.nodes.get(edge.from) : null;
        const toNode = window.nodes && typeof window.nodes.get === 'function' ? window.nodes.get(edge.to) : null;
        if (!fromNode || !toNode) return;

        const payload = {
            projectId: currentProjectId,
            edge: {
                id: edge.id,
                from: edge.from,
                to: edge.to,
                label: edge.label,
                title: edge.title,
                color: edge.color,
                arrows: edge.arrows,
            },
            fromNode,
            toNode,
        };

        try {
            await fetchJson('/api/c1/sync-edge', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
        } catch (e) {
            console.error('[C-1] syncEdgeToC1 failed:', e);
        }
    }

    function schedulePositionSync(nodeId, x, y) {
        if (!currentProjectId) return;
        if (!nodeId) return;
        if (isSyncSuppressed()) return;

        const key = String(nodeId);
        const existing = positionQueue.get(key);
        if (existing && existing.timer) {
            existing.x = x;
            existing.y = y;
            return;
        }

        const entry = { x, y, timer: null };
        entry.timer = setTimeout(async () => {
            positionQueue.delete(key);
            try {
                await fetchJson('/api/c1/sync-position', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ projectId: currentProjectId, nodeId: key, x: entry.x, y: entry.y }),
                });
            } catch (e) {
                console.error('[C-1] sync-position failed:', e);
            }
        }, POSITION_SYNC_DEBOUNCE_MS);

        positionQueue.set(key, entry);
    }

    window.C1Integration = {
        getCurrentProjectId,
        isSyncSuppressed,
        initializeC1Integration,
        syncNodeToC1,
        syncEdgeToC1,
        schedulePositionSync,
    };
})();
