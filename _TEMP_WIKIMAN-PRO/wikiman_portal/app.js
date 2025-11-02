(() => {
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  const status = (msg) => { $('#status').textContent = msg || ''; };
  const server = { available: false };

  // Chat / Communication (localStorage)
  const CHAT_KEY = 'wikiman_portal_chat_v1';
  let chat = [];
  const loadChat = async () => {
    if (server.available) {
      try {
        const res = await fetch('/api/chat');
        if (res.ok) {
          const data = await res.json();
          chat = Array.isArray(data.items) ? data.items : [];
          return;
        }
      } catch {}
    }
    try { chat = JSON.parse(localStorage.getItem(CHAT_KEY) || '[]'); } catch { chat = []; }
  };
  const saveChat = async () => {
    if (server.available) {
      try {
        await fetch('/api/chat/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ items: chat }) });
        return;
      } catch {}
    }
    localStorage.setItem(CHAT_KEY, JSON.stringify(chat));
  };
  const renderChat = () => {
    const list = $('#chatList');
    list.innerHTML = '';
    chat.forEach((item, idx) => {
      const el = document.createElement('div');
      el.className = 'chat-item' + (item.role === 'assistant' ? ' assistant' : '');
      el.innerHTML = `
        <span class="type">${item.role === 'assistant' ? 'bot' : item.type}</span>
        <div class="text">${escapeHTML(item.text)}</div>
        <div class="meta">${new Date(item.ts).toLocaleString()}<br/>
          <a class="link" data-act="toggle" data-idx="${idx}">${item.done ? 'Mark undone' : 'Mark done'}</a>
          · <a class="link" data-act="del" data-idx="${idx}">Delete</a>
          ${item.done ? ' · <span class="done">✔ done</span>' : ''}
        </div>`;
      list.appendChild(el);
    });
  };
  const escapeHTML = (s) => String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  // Graph (vis-network)
  let network = null;
  let graphData = { nodes: [], edges: [] };
  const loadGraph = async (path) => {
    try {
      $('#graphSource').textContent = `Graph: ${path}`;
      const res = await fetch(path);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // Accept both vis-compatible and custom structures
      graphData = {
        nodes: (data.nodes || []).map(n => ({ id: n.id, label: n.label, color: n.color, shape: n.shape || 'dot', size: n.size || 14, title: n.title || '' })),
        edges: (data.edges || data.links || []).map(e => ({ from: e.from || e.source, to: e.to || e.target, label: e.label || e.relationship_type || '' }))
      };
      renderGraph();
      renderLegend(data.nodes || []);
      status('Graph loaded');
    } catch (err) {
      $('#graphSource').textContent = 'Graph: not found';
      status(`Graph load failed: ${err.message}`);
    }
  };
  const renderGraph = () => {
    const container = $('#graph');
    const nodes = new vis.DataSet(graphData.nodes);
    const edges = new vis.DataSet(graphData.edges);
    if (network) network.destroy();
    network = new vis.Network(container, { nodes, edges }, {
      interaction: { hover: true, navigationButtons: true, multiselect: true },
      physics: { stabilization: true },
      nodes: { font: { color: '#e5e7eb' } },
      edges: { color: { color: '#556' }, smooth: true }
    });

    // Create chat note on node focus
    network.on('click', (params) => {
      if (!params.nodes?.length) return;
      const nodeId = params.nodes[0];
      const n = nodes.get(nodeId);
      if (!n) return;
      chat.unshift({ text: `Focused node: ${n.label}`, type: 'note', ts: Date.now(), done: false });
      saveChat();
      renderChat();
    });
  };
  const escapeAttr = (s) => String(s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  const renderLegend = (nodes) => {
    const byType = {};
    nodes.forEach(n => {
      const k = (n.type || 'unknown');
      byType[k] = byType[k] || n.color || '#888';
    });
    const legend = $('#legend');
    legend.innerHTML = Object.entries(byType).sort().map(([t, c]) => `
      <span class="pill" style="border-color:${c}; color:${c}">${t}</span>
    `).join(' ');
  };

  // Project system
  let project = null;
  let lastDiff = '';
  let lastBefore = '';
  let lastAfter = '';
  const loadProjectFromFile = (file) => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(JSON.parse(reader.result));
    reader.onerror = (e) => reject(e);
    reader.readAsText(file);
  });
  const loadProjectFromPath = async (path) => {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  };
  const renderProject = () => {
    const src = $('#projectSource');
    if (!project) { src.textContent = 'No project loaded'; return; }
    src.textContent = 'Project loaded';

    // Stats
    const stats = $('#projectStats');
    stats.innerHTML = '';
    const pushStat = (k, v) => {
      const el = document.createElement('div');
      el.className = 'stat';
      el.innerHTML = `<div class="k">${k}</div><div class="v">${v}</div>`;
      stats.appendChild(el);
    };
    if (project.statistics) {
      Object.entries(project.statistics).forEach(([k, v]) => pushStat(k.replace(/_/g,' '), v));
    }
    pushStat('notes', (project.timeline || []).length);
    pushStat('outgoing edges', (project.relationships?.outgoing || []).length);

    // Edges
    renderEdges();

    // Diff controls
    updateDiffControls();
  };
  const edgeMatches = (e, term) => {
    const t = term.toLowerCase();
    const hay = [e.relationship_type, e.node_type, e.value, e.name, e.context].join(' ').toLowerCase();
    return hay.includes(t);
  };
  const renderEdges = () => {
    const list = $('#edgesList');
    list.innerHTML = '';
    if (!project) return;
    const term = ($('#edgeFilter').value || '').trim();
    const edges = (project.relationships?.outgoing || []).filter(e => !term || edgeMatches(e, term));
    edges.forEach((e, idx) => {
      const el = document.createElement('div');
      el.className = 'edge';
      const label = escapeHTML(e.value || e.name || e.node_type || '');
      el.innerHTML = `
        <div class="h">
          <span class="pill">${escapeHTML(e.relationship_type || '')}</span>
          <span class="pill">${escapeHTML(e.node_type || '')}</span>
          <a class="link" data-edge-idx="${idx}">${label}</a>
        </div>
        <div class="ctx">${escapeHTML(e.context || '')}</div>
      `;
      list.appendChild(el);
    });
  };

  // Highlight graph node when clicking edge target
  const focusNodeByValue = (value) => {
    if (!network) return;
    const match = graphData.nodes.find(n => (n.label||'').includes(value));
    if (match) {
      network.selectNodes([match.id]);
      network.focus(match.id, { scale: 1.2, animation: true });
    }
  };

  // Wire up events
  const initEvents = () => {
    // Chat actions
    $('#chatForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = ($('#chatInput').value || '').trim();
      const type = $('#chatType').value;
      if (!text) return;
      chat.unshift({ text, type, ts: Date.now(), done: false });
      await saveChat();
      $('#chatInput').value = '';
      $('#noteUrl').value = '';
      renderChat();
      if (server.available) {
        console.log('Server available, sending to WikiMan:', text);
        try {
          const name = ($('#projectName').value || 'Portal Session').trim();
          const res = await fetch('/api/wikiman/chat', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ text, project_name: name }) });
          const js = await res.json();
          console.log('WikiMan response:', js);
          if (res.ok && js.reply) {
            chat.unshift({ text: js.reply, type: 'note', role: 'assistant', ts: Date.now(), done: false });
            await saveChat();
            renderChat();
            if (js.project_name) {
              $('#projectName').value = js.project_name;
              status(`Project set to ${js.project_name}`, 'success');
            }
            if (js.diff) {
              lastDiff = js.diff;
              renderDiff();
              updateDiffControls();
              $('#toggleDiff').textContent = 'Hide';
              $('#diffView').classList.remove('hidden');
            }
            if (js.before) lastBefore = js.before;
            if (js.after) lastAfter = js.after;
          }
        } catch (err) {
          console.error('WikiMan chat error:', err);
          status('WikiMan chat error - check console', 'error');
        }
      } else {
        console.log('Server not available - server.available:', server.available);
      }
    });
    $('#chatList').addEventListener('click', (e) => {
      const a = e.target.closest('a.link');
      if (!a) return;
      const idx = +a.dataset.idx;
      const act = a.dataset.act;
      if (act === 'del') { chat.splice(idx, 1); }
      if (act === 'toggle') { chat[idx].done = !chat[idx].done; }
      saveChat();
      renderChat();
    });

    // Export chat
    $('#exportChat').addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(chat, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `wikiman_chat_${new Date().toISOString().slice(0,19).replace(/[:T]/g,'-')}.json`;
      a.click();
    });

    // Reset layout
    $('#resetUI').addEventListener('click', () => {
      if (confirm('Reset chat and reload?')) {
        localStorage.removeItem(CHAT_KEY);
        location.reload();
      }
    });

    // Edge filter
    $('#edgeFilter').addEventListener('input', renderEdges);

    // Edge click -> focus graph
    $('#edgesList').addEventListener('click', (e) => {
      const link = e.target.closest('a[data-edge-idx]');
      if (!link) return;
      const idx = +link.dataset.edgeIdx;
      const eObj = (project.relationships?.outgoing || [])[idx];
      if (eObj) focusNodeByValue(eObj.value || eObj.name || '');
    });

    // Diff actions
    $('#toggleDiff').addEventListener('click', () => {
      const pre = $('#diffView');
      const isHidden = pre.classList.toggle('hidden');
      $('#toggleDiff').textContent = isHidden ? 'Show' : 'Hide';
    });
    $('#copyDiff').addEventListener('click', async () => {
      if (!lastDiff) return;
      try { await navigator.clipboard.writeText(lastDiff); status('Diff copied', 'success'); } catch { status('Copy failed', 'error'); }
    });
    $('#downloadDiff').addEventListener('click', () => {
      if (!lastDiff) return;
      const blob = new Blob([lastDiff], { type: 'text/plain' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `wikiman_diff_${new Date().toISOString().slice(0,19).replace(/[:T]/g,'-')}.diff`;
      a.click();
    });
    
    // Apply Patch Locally button
    $('#saveAfter').addEventListener('click', async () => {
      if (!lastAfter) return;
      const name = ($('#projectName').value || 'Portal Session').trim();
      try {
        const res = await fetch('/api/wikiman/save_after', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ project_name: name })
        });
        const js = await res.json();
        if (!res.ok) throw new Error(js.error || 'Save failed');
        status(`Saved rewritten content to ${js.path}`, 'success');
      } catch (e) {
        status(`Save error: ${e.message}`, 'error');
      }
    });
    
    // 2-up toggle
    $('#toggleTwoUp').addEventListener('click', () => {
      const twoUp = $('#twoUp');
      const diffView = $('#diffView');
      const isHidden = twoUp.classList.toggle('hidden');
      if (!isHidden) {
        // Show 2-up, hide diff
        diffView.classList.add('hidden');
        $('#toggleDiff').textContent = 'Show';
        // Render before/after
        $('#beforeView').textContent = lastBefore || '(No before text available)';
        $('#afterView').textContent = lastAfter || '(No after text available)';
        $('#toggleTwoUp').textContent = 'Diff';
      } else {
        // Hide 2-up
        $('#toggleTwoUp').textContent = '2-Up';
      }
    });

    // Project file loader
    $('#projectFile').addEventListener('change', async (ev) => {
      const file = ev.target.files?.[0];
      if (!file) return;
      try {
        project = await loadProjectFromFile(file);
        $('#projectSource').textContent = `Project: ${file.name}`;
        renderProject();
        status('Project loaded from file');
      } catch (err) {
        status(`Project load failed: ${err.message}`);
      }
    });

    // Server-powered actions
    if (server.available) {
      // Add + Attach (creates narrative note, optional source URL)
      $('#attachNote').addEventListener('click', async () => withButton('attachNote', 'Adding…', async () => {
        const text = ($('#chatInput').value || '').trim();
        const type = $('#chatType').value;
        const url = ($('#noteUrl').value || '').trim();
        const name = ($('#projectName').value || 'Portal Session').trim();
        if (!text) { status('Enter note text'); return; }
        const res = await fetch('/api/project/add_note', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_name: name, text, type, source_url: url })
        });
        const js = await res.json();
        if (!res.ok) throw new Error(js.error || 'Add note failed');
        // Also keep it in local chat for continuity
        chat.unshift({ text, type, ts: Date.now(), done: false });
        await saveChat();
        $('#chatInput').value = '';
        $('#noteUrl').value = '';
        renderChat();
        // Refresh project/graph
        try {
          project = js.export;
          $('#projectSource').textContent = `Project: server export (${name})`;
          renderProject();
          await loadGraph('/api/graph');
        } catch {}
        status(url ? 'Note added with source' : 'Note added', 'success');
      }).catch(e => status(`Add note error: ${e.message}`, 'error')));
      $('#refreshGraph').addEventListener('click', async () => withButton('refreshGraph', 'Refreshing…', async () => {
        const res = await fetch('/api/refresh/graph', { method: 'POST' });
        const js = await res.json();
        if (!res.ok) throw new Error(js.error || 'Refresh failed');
        await loadGraph('/api/graph');
        status(`Graph refreshed: ${js.stats.total_nodes} nodes / ${js.stats.total_edges} edges`, 'success');
      }).catch(e => status(`Graph refresh error: ${e.message}`, 'error')));

      $('#exportProject').addEventListener('click', async () => withButton('exportProject', 'Exporting…', async () => {
        const name = ($('#projectName').value || 'Portal Session').trim();
        const res = await fetch('/api/project/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_name: name }) });
        const js = await res.json();
        if (!res.ok) throw new Error(js.error || 'Export failed');
        project = js.export;
        $('#projectSource').textContent = `Project: server export (${name})`;
        renderProject();
        status(`Exported project to ${js.project_path}`, 'success');
      }).catch(e => status(`Project export error: ${e.message}`, 'error')));

      $('#commitChat').addEventListener('click', async () => withButton('commitChat', 'Committing…', async () => {
        const name = ($('#projectName').value || 'Portal Session').trim();
        const res = await fetch('/api/project/commit_chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project_name: name, items: chat }) });
        const js = await res.json();
        if (!res.ok) throw new Error(js.error || 'Commit failed');
        project = js.export;
        $('#projectSource').textContent = `Project: server export (${name})`;
        renderProject();
        await loadGraph('/api/graph');
        status(`Committed ${js.added} chat items → project`, 'success');
      }).catch(e => status(`Commit error: ${e.message}`, 'error')));

      // Archive/Delete project
      const refreshProjectSelect = (items) => {
        const sel = $('#projectSelect');
        sel.innerHTML = '<option value="">• Select project…</option>' +
          (items || []).map(it => {
            const label = (it.name || it.value) + (it.status === 'archived' ? ' (archived)' : '');
            return `<option value="${escapeAttr(it.name || it.value)}">${escapeHTML(label)}</option>`;
          }).join('');
      };
      $('#archiveProject').addEventListener('click', async () => withButton('archiveProject','Archiving…', async () => {
        const name = ($('#projectName').value || '').trim();
        if (!name) { status('Select or enter a project name'); return; }
        if (!confirm(`Archive project "${name}"?`)) return;
        const r = await fetch('/api/project/archive', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ project_name: name }) });
        const js = await r.json();
        if (!r.ok) throw new Error(js.error || 'Archive failed');
        refreshProjectSelect(js.projects || []);
        status(`Archived project → ${name}`,'success');
      }).catch(e => status(`Archive error: ${e.message}`,'error')));
      $('#deleteProject').addEventListener('click', async () => withButton('deleteProject','Deleting…', async () => {
        const name = ($('#projectName').value || '').trim();
        if (!name) { status('Select or enter a project name'); return; }
        if (!confirm(`Delete project "${name}" (soft delete)?`)) return;
        const r = await fetch('/api/project/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ project_name: name }) });
        const js = await r.json();
        if (!r.ok) throw new Error(js.error || 'Delete failed');
        refreshProjectSelect(js.projects || []);
        const sel = $('#projectSelect');
        if (!Array.from(sel.options).some(o => o.value === name)) {
          sel.value = '';
          $('#projectName').value = '';
          project = null;
          renderProject();
        }
        status(`Deleted project → ${name}`,'success');
      }).catch(e => status(`Delete error: ${e.message}`,'error')));

      $('#undoProject').addEventListener('click', async () => withButton('undoProject','Restoring…', async () => {
        const name = ($('#projectName').value || '').trim();
        if (!name) { status('Enter a project name to restore'); return; }
        const r = await fetch('/api/project/restore', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ project_name: name }) });
        const js = await r.json();
        if (!r.ok) throw new Error(js.error || 'Restore failed');
        refreshProjectSelect(js.projects || []);
        const sel = $('#projectSelect');
        sel.value = name;
        status(`Restored project → ${name}`,'success');
      }).catch(e => status(`Undo error: ${e.message}`,'error')));
    } else {
      // Hide server-only buttons if API not present
      ['refreshGraph','exportProject','commitChat','attachNote','projectSelect','newProject','projectDesc','archiveProject','deleteProject','undoProject'].forEach(id => { const el = document.getElementById(id); if (el) el.style.display = 'none'; });
    }
  };

  // Boot
  const boot = async () => {
    // Detect server
    try {
      const res = await fetch('/api/health');
      server.available = res.ok;
      console.log('Server detection - available:', server.available);
    } catch (err) { 
      server.available = false;
      console.log('Server detection failed:', err);
    }

    initEvents();
    await loadChat();
    renderChat();

    // Try load defaults if reachable
    const defaults = window.WIKIMAN_DEFAULTS || {};
    if (server.available) {
      // Prefer server-provided graph/project
      try { await loadGraph('/api/graph'); } catch {}
      try {
        project = await loadProjectFromPath('/api/project');
        $('#projectSource').textContent = 'Project: server';
        renderProject();
      } catch {}

      // Load project list for switcher
      try {
        const res = await fetch('/api/projects');
        if (res.ok) {
          const js = await res.json();
          const sel = $('#projectSelect');
          sel.innerHTML = '<option value="">• Select project…</option>' +
            (js.items || []).map(it => {
              const label = (it.name || it.value) + (it.status === 'archived' ? ' (archived)' : '');
              return `<option value="${escapeAttr(it.name || it.value)}">${escapeHTML(label)}</option>`;
            }).join('');
          sel.addEventListener('change', async () => {
            const name = sel.value;
            if (!name) return;
            $('#projectName').value = name;
            try {
              const r2 = await fetch('/api/project/switch', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ project_name: name }) });
              const js2 = await r2.json();
              if (!r2.ok) throw new Error(js2.error || 'Switch failed');
              project = js2.export;
              $('#projectSource').textContent = `Project: ${name}`;
              renderProject();
              await loadGraph('/api/graph');
              status(`Switched project → ${name}`);
            } catch(e) { status(`Switch error: ${e.message}`); }
          });
        }
      } catch {}
    }
    if (!network && defaults.graphPath) await loadGraph(defaults.graphPath);
    if (!project && defaults.projectPath) {
      try {
        project = await loadProjectFromPath(defaults.projectPath);
        $('#projectSource').textContent = `Project: ${defaults.projectPath}`;
        renderProject();
      } catch (err) {
        status(`Project auto-load skipped: ${err.message}`);
      }
    }
  };

  const updateDiffControls = () => {
    const has = !!lastDiff;
    const hasAfter = !!lastAfter;
    const copy = $('#copyDiff');
    const dl = $('#downloadDiff');
    const save = $('#saveAfter');
    if (copy) copy.disabled = !has;
    if (dl) dl.disabled = !has;
    if (save) save.disabled = !hasAfter;
    if (has) renderDiff(); else { const dv=$('#diffView'); if (dv) dv.textContent=''; }
  };

  const renderDiff = () => {
    const pre = $('#diffView');
    if (!pre) return;
    const lines = (lastDiff || '').split('\n');
    const html = lines.map(line => {
      const esc = escapeHTML(line);
      if (line.startsWith('+++ ') || line.startsWith('--- ')) return `<span class="file">${esc}</span>`;
      if (line.startsWith('@@')) return `<span class="hunk">${esc}</span>`;
      if (line.startsWith('+') && !line.startsWith('+++')) return `<span class="add">${esc}</span>`;
      if (line.startsWith('-') && !line.startsWith('---')) return `<span class="del">${esc}</span>`;
      return `<span class="ctx">${esc}</span>`;
    }).join('\n');
    pre.innerHTML = html;
  };

  document.addEventListener('DOMContentLoaded', boot);
})();
