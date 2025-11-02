#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from flask import Flask, send_from_directory, jsonify, request

BASE_DIR = Path(__file__).resolve().parent
ROOT = BASE_DIR.parent
OUTPUT_DIR = ROOT / 'output'
OUTPUT_DIR.mkdir(exist_ok=True)
CHAT_FILE = OUTPUT_DIR / 'wikiman_chat.json'

DEFAULT_GRAPH = ROOT / 'wikiman_graph_web' / 'graph_data.json'
DEFAULT_PROJECT = ROOT / 'project_dry_b6081f8f.json'

app = Flask(__name__, static_folder=str(BASE_DIR))

# Ensure project root is importable
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Optional imports for generation hooks
try:
    from wikiman_graph_visualizer import WikiManGraphVisualizer
except Exception:
    WikiManGraphVisualizer = None

try:
    from wikiman_narrative_tracker import WikiManNarrativeTracker
except Exception:
    WikiManNarrativeTracker = None
try:
    from wikiman_graph_db import WikiManGraphDB
except Exception:
    WikiManGraphDB = None

# Full WikiMan chat/editor
try:
    from wikiman_agent import MW as WM_MW, LLM as WM_LLM, env_cfg as WM_env_cfg, split_sections as WM_split_sections, replace_section as WM_replace_section, HOUSE_STYLE_SYSTEM as WM_HOUSE_STYLE_SYSTEM
    import re as _re
    WM_SECTION_RE = _re.compile(r"^(?P<eq>=+)\\s*(?P<name>[^=]+?)\\s*(?P=eq)\\s*$", _re.MULTILINE)
except Exception:
    WM_MW = None
    WM_LLM = None
    WM_env_cfg = None
    WM_split_sections = None
    WM_replace_section = None
    WM_HOUSE_STYLE_SYSTEM = None
    WM_SECTION_RE = None

# In-memory WikiMan sessions by project name
WIKIMAN_SESS = {}


def _list_projects_items():
    """Return list of project narratives with minimal info."""
    if WikiManGraphDB is None:
        return []
    db = WikiManGraphDB()
    rows = db.search_nodes('', node_type='project_narrative', limit=200)
    items = []
    for r in rows:
        about = json.loads(r.get('about') or '{}') if isinstance(r.get('about'), str) else (r.get('about') or {})
        template = json.loads(r.get('template_data') or '{}') if isinstance(r.get('template_data'), str) else (r.get('template_data') or {})
        items.append({
            'node_id': r.get('node_id'),
            'name': r.get('name') or r.get('value'),
            'value': r.get('value'),
            'last_updated': r.get('last_updated'),
            'total_notes': about.get('total_notes') or len((template.get('narrative_entries') or [])),
            'status': (about.get('status') or 'active')
        })
    # Hide deleted by default
    return [it for it in items if it.get('status') != 'deleted']


@app.get('/api/health')
def health():
    return jsonify({'ok': True})


@app.get('/api/chat')
def chat_get():
    if CHAT_FILE.exists():
        try:
            with CHAT_FILE.open('r', encoding='utf-8') as f:
                items = json.load(f)
        except Exception:
            items = []
    else:
        items = []
    return jsonify({'items': items})


@app.post('/api/chat/save')
def chat_save():
    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    if not isinstance(items, list):
        return jsonify({'error': 'items must be a list'}), 400
    with CHAT_FILE.open('w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return jsonify({'ok': True})


@app.get('/api/graph')
def graph_get():
    # Allow override via env var WIKIMAN_GRAPH
    path = Path(os.environ.get('WIKIMAN_GRAPH', DEFAULT_GRAPH))
    if not path.exists():
        return jsonify({'error': f'graph file not found: {path}'}), 404
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)


@app.get('/api/project')
def project_get():
    # Allow override via env var WIKIMAN_PROJECT
    path = Path(os.environ.get('WIKIMAN_PROJECT', DEFAULT_PROJECT))
    if not path.exists():
        return jsonify({'error': f'project file not found: {path}'}), 404
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    return jsonify(data)


@app.post('/api/refresh/graph')
def refresh_graph():
    if WikiManGraphVisualizer is None:
        return jsonify({'error': 'Graph generator unavailable'}), 500
    port = int(os.environ.get('GRAPH_PORT', '0')) or 0
    vis = WikiManGraphVisualizer(port=port)
    vis.generate_html_files()
    # Load fresh data to report
    if DEFAULT_GRAPH.exists():
        with DEFAULT_GRAPH.open('r', encoding='utf-8') as f:
            data = json.load(f)
        stats = data.get('stats') or {'total_nodes': len(data.get('nodes', [])), 'total_edges': len(data.get('edges', []))}
    else:
        stats = {'total_nodes': 0, 'total_edges': 0}
    return jsonify({'ok': True, 'stats': stats, 'graph_path': str(DEFAULT_GRAPH)})


@app.post('/api/project/export')
def project_export():
    if WikiManNarrativeTracker is None:
        return jsonify({'error': 'Narrative tracker unavailable'}), 500
    payload = request.get_json(silent=True) or {}
    project_name = payload.get('project_name') or 'Portal Session'
    out_path = OUTPUT_DIR / f'project_{project_name.lower().replace(" ", "_")}.json'
    tracker = WikiManNarrativeTracker()
    tracker.switch_project(project_name)
    data = tracker.export_narrative(str(out_path))
    return jsonify({'ok': True, 'project_path': str(out_path), 'export': data})


@app.post('/api/project/commit_chat')
def project_commit_chat():
    if WikiManNarrativeTracker is None:
        return jsonify({'error': 'Narrative tracker unavailable'}), 500
    payload = request.get_json(silent=True) or {}
    project_name = payload.get('project_name') or 'Portal Session'
    items = payload.get('items') or []
    if not isinstance(items, list):
        return jsonify({'error': 'items must be a list'}), 400
    tracker = WikiManNarrativeTracker()
    tracker.switch_project(project_name)
    added = 0
    for it in items:
        txt = str(it.get('text') or '').strip()
        if not txt:
            continue
        typ = (it.get('type') or 'note').strip()
        ctx = f'portal_{typ}'
        tracker.add_note(txt, context=ctx)
        added += 1
    out_path = OUTPUT_DIR / f'project_{project_name.lower().replace(" ", "_")}.json'
    export = tracker.export_narrative(str(out_path))
    # Optionally refresh graph
    if WikiManGraphVisualizer is not None:
        vis = WikiManGraphVisualizer()
        vis.generate_html_files()
    return jsonify({'ok': True, 'added': added, 'project_path': str(out_path), 'export': export})


@app.get('/api/projects')
def list_projects():
    if WikiManGraphDB is None:
        return jsonify({'error': 'Graph DB unavailable'}), 500
    return jsonify({'items': _list_projects_items()})


@app.post('/api/project/switch')
def project_switch():
    if WikiManNarrativeTracker is None:
        return jsonify({'error': 'Narrative tracker unavailable'}), 500
    payload = request.get_json(silent=True) or {}
    name = (payload.get('project_name') or '').strip()
    if not name:
        return jsonify({'error': 'project_name is required'}), 400
    tracker = WikiManNarrativeTracker()
    tracker.switch_project(name)
    out_path = OUTPUT_DIR / f'project_{name.lower().replace(" ", "_")}.json'
    export = tracker.export_narrative(str(out_path))
    return jsonify({'ok': True, 'project_path': str(out_path), 'export': export})


@app.post('/api/project/archive')
def project_archive():
    if WikiManGraphDB is None:
        return jsonify({'error': 'Graph DB unavailable'}), 500
    payload = request.get_json(silent=True) or {}
    name = (payload.get('project_name') or '').strip()
    if not name:
        return jsonify({'error': 'project_name is required'}), 400
    db = WikiManGraphDB()
    rows = db.search_nodes(name, node_type='project_narrative', limit=1)
    if not rows:
        return jsonify({'error': 'project not found'}), 404
    node_id = rows[0]['node_id']
    node = db.get_node(node_id=node_id)
    node['about'] = node.get('about', {})
    node['about']['status'] = 'archived'
    node['about']['archived_at'] = __import__('datetime').datetime.utcnow().isoformat() + 'Z'
    db.save_entity(node, merge=True)
    projects = _list_projects_items()
    return jsonify({'ok': True, 'projects': projects})


@app.post('/api/project/delete')
def project_delete():
    if WikiManGraphDB is None:
        return jsonify({'error': 'Graph DB unavailable'}), 500
    payload = request.get_json(silent=True) or {}
    name = (payload.get('project_name') or '').strip()
    if not name:
        return jsonify({'error': 'project_name is required'}), 400
    db = WikiManGraphDB()
    rows = db.search_nodes(name, node_type='project_narrative', limit=1)
    if not rows:
        return jsonify({'error': 'project not found'}), 404
    node_id = rows[0]['node_id']
    node = db.get_node(node_id=node_id)
    node['about'] = node.get('about', {})
    node['about']['status'] = 'deleted'
    node['about']['deleted_at'] = __import__('datetime').datetime.utcnow().isoformat() + 'Z'
    db.save_entity(node, merge=True)
    projects = _list_projects_items()
    return jsonify({'ok': True, 'projects': projects})


@app.post('/api/project/restore')
def project_restore():
    if WikiManGraphDB is None:
        return jsonify({'error': 'Graph DB unavailable'}), 500
    payload = request.get_json(silent=True) or {}
    name = (payload.get('project_name') or '').strip()
    if not name:
        return jsonify({'error': 'project_name is required'}), 400
    db = WikiManGraphDB()
    rows = db.search_nodes(name, node_type='project_narrative', limit=1)
    if not rows:
        return jsonify({'error': 'project not found'}), 404
    node_id = rows[0]['node_id']
    node = db.get_node(node_id=node_id)
    node['about'] = node.get('about', {})
    node['about']['status'] = 'active'
    node['about'].pop('archived_at', None)
    node['about'].pop('deleted_at', None)
    db.save_entity(node, merge=True)
    projects = _list_projects_items()
    return jsonify({'ok': True, 'projects': projects})


# REMOVED - Old assistant endpoint, replaced by full WikiMan chat at /api/wikiman/chat
# The WikiMan chat endpoint below handles all interactions with the real WikiMan agent


def _wm_list_section_names(wtxt: str):
    names = []
    if WM_SECTION_RE is None:
        return names
    for m in WM_SECTION_RE.finditer(wtxt):
        names.append(m.group('name').strip())
    return names


@app.post('/api/wikiman/chat')
def wikiman_chat():
    if WM_MW is None or WM_LLM is None or WM_env_cfg is None:
        missing = []
        if WM_MW is None: missing.append('MW (MediaWiki client)')
        if WM_LLM is None: missing.append('LLM (language model)')
        if WM_env_cfg is None: missing.append('env_cfg (config)')
        return jsonify({
            'reply': f'WikiMan components missing: {", ".join(missing)}. Check wikiman_agent.py imports.',
            'error': 'Components not available'
        })
    payload = request.get_json(silent=True) or {}
    text = (payload.get('text') or '').strip()
    project_name = (payload.get('project_name') or 'Portal Session').strip()
    planner_model = os.environ.get('WIKIMAN_PLANNER_MODEL') or (
        ('openai:gpt-4o-mini' if os.environ.get('OPENAI_API_KEY') else None)
        or ('google:gemini-1.5-flash' if os.environ.get('GOOGLE_API_KEY') else None)
        or ('anthropic:claude-3-haiku' if os.environ.get('ANTHROPIC_API_KEY') else None)
        or 'openai:gpt-4o-mini'
    )
    editor_model = os.environ.get('WIKIMAN_EDITOR_MODEL', 'anthropic:claude-4.1')
    cfg = WM_env_cfg()

    sess = WIKIMAN_SESS.setdefault(project_name, {
        'page': None, 'section': None, 'before': None, 'after': None, 'diff': None, 'model': editor_model
    })

    def plan_from_nl(cmd: str) -> dict:
        sys_prompt = (
            "You are a command planner for WikiMan, a MediaWiki editor. Convert any user utterance into a JSON plan.\n"
            "Valid actions: pull, set_section, rewrite, preview, upload, list_sections, set_model, help, quit.\n"
            "Fields: action (string), page (string, optional), section (string, optional), instructions (string, optional), model (string, optional).\n"
            "Never include explanations—return ONLY minified JSON."
        )
        ctx = { 'current_page': sess.get('page'), 'current_section': sess.get('section') }
        user_prompt = "Context: " + json.dumps(ctx) + "\nUtterance: " + cmd.strip()
        try:
            out = WM_LLM(planner_model).generate(system=sys_prompt, user=user_prompt).strip()
            start = out.find('{'); end = out.rfind('}')
            if start != -1 and end != -1 and end > start:
                out = out[start:end+1]
            plan = json.loads(out)
            if isinstance(plan, dict) and plan.get('action'):
                return {k: str(v) for k, v in plan.items() if isinstance(v, (str, int, float))}
        except Exception:
            pass
        low = cmd.strip().lower()
        if low in ('help','/help'): return {'action':'help'}
        if low in ('exit','quit'): return {'action':'quit'}
        if low.startswith('pull ') or low.startswith('open ') or low.startswith('load '):
            title = cmd.split(' ',1)[1].strip(); return {'action':'pull','page':title}
        if low.startswith('section ') or low.startswith('set section '):
            sec = cmd.split(' ',1)[1].strip(); return {'action':'set_section','section':sec}
        if low.startswith('model '):
            return {'action':'set_model','model': cmd.split(' ',1)[1].strip()}
        if low in ('preview','show diff'): return {'action':'preview'}
        if low in ('upload','save'): return {'action':'upload'}
        if low in ('show sections','list sections'): return {'action':'list_sections'}
        return {'action':'rewrite','instructions': cmd}

    if not text:
        return jsonify({'reply': 'Say: pull <Page>, section <Heading>, then rewrite <instructions>.'})
    
    # Handle greetings specially
    lower = text.lower().strip()
    if lower in ['hi', 'hello', 'hey', 'yo', 'sup', 'hiya'] or any(lower.startswith(x) for x in ['hi ', 'hello ', 'hey ']):
        return jsonify({'reply': "Hi! I'm WikiMan, your MediaWiki editor. Try:\n• pull <Page> - load a wiki page\n• section <Name> - select a section\n• rewrite <instructions> - edit the section\n• preview - see changes\n• upload - save to wiki"})

    intent = plan_from_nl(text)
    a = intent.get('action')
    try:
        if a == 'help':
            return jsonify({'reply': 'Commands: pull <Page>, section <Heading>, rewrite <instructions>, preview, upload, show sections, model <provider:model>'})
        if a == 'quit':
            return jsonify({'reply': 'Session persists; nothing to quit.'})
        if a == 'set_model':
            sess['model'] = intent['model']
            return jsonify({'reply': f"Model set to {sess['model']}"})
        if a == 'pull':
            page = intent['page']
            mw = WM_MW(cfg['base'], cfg['user'], cfg['password']); mw.login()
            txt = mw.get_page_wikitext(page)
            sess.update({'page': page, 'before': txt, 'after': None, 'diff': None})
            secs = _wm_list_section_names(txt)
            return jsonify({'reply': f"Loaded '{page}'. Sections: {', '.join(secs[:20])}{' ...' if len(secs)>20 else ''}", 'page': page})
        if a == 'set_section':
            sess['section'] = intent['section']
            return jsonify({'reply': f"Section set to '{sess['section']}'", 'section': sess['section']})
        if a in ('rewrite','preview'):
            if not sess.get('page'):
                return jsonify({'reply': 'Pull a page first: pull <Page>'}), 200
            if not sess.get('section'):
                return jsonify({'reply': 'Set a section first: section <Heading>'}), 200
            instr = intent.get('instructions','')
            mw = WM_MW(cfg['base'], cfg['user'], cfg['password']); mw.login()
            original = sess.get('before') or mw.get_page_wikitext(sess['page'])
            sections = WM_split_sections(original)
            body, _ = sections.get(sess['section'], ('', (len(original), len(original))))
            editor = WM_LLM(sess.get('model') or editor_model)
            user_prompt = (
                f"Page: {sess['page']}\nSection: {sess['section']}\n\nCurrent section body (wikitext):\n{body}\n\n"
                f"Rewrite instructions:\n{instr}\n\nReturn ONLY the rewritten section body in valid wikitext."
            )
            rewritten = editor.generate(system=WM_HOUSE_STYLE_SYSTEM, user=user_prompt)
            new_text = WM_replace_section(original, sess['section'], rewritten)
            import difflib
            diff = "\n".join(difflib.unified_diff(original.splitlines(), new_text.splitlines(), fromfile='before', tofile='after', lineterm=''))
            sess.update({'after': new_text, 'diff': diff})
            if a == 'preview':
                short = "\n".join(diff.splitlines()[:60])
                return jsonify({'reply': f"Preview ready. Diff (first 60 lines):\n{short}", 'diff': diff, 'before': original, 'after': new_text})
            else:
                short = (instr[:120] + '...') if len(instr) > 120 else instr
                return jsonify({'reply': f"Rewritten in memory (not uploaded). Use 'preview' to inspect or 'upload' to apply.\nInstructions: {short}", 'diff': diff, 'before': original, 'after': new_text})
        if a == 'upload':
            if not sess.get('page') or not sess.get('after'):
                return jsonify({'reply': 'Nothing to upload. Run rewrite/preview first.'}), 200
            mw = WM_MW(cfg['base'], cfg['user'], cfg['password']); mw.login()
            mw.edit_page_wikitext(sess['page'], sess['after'], summary=f"WIKIMAN: rewrite {sess.get('section') or ''}".strip())
            return jsonify({'reply': f"Uploaded changes to {sess['page']} ({sess.get('section') or 'full'})"})
        if a == 'list_sections':
            if not sess.get('before'):
                return jsonify({'reply': 'Pull a page first: pull <Page>'}), 200
            secs = _wm_list_section_names(sess['before'])
            return jsonify({'reply': 'Sections:\n' + "\n".join(f"- {s}" for s in secs)})
        return jsonify({'reply': 'Unhandled action'})
    except Exception as e:
        return jsonify({'reply': f"Error: {e}"}), 200


@app.post('/api/wikiman/save_after')
def wikiman_save_after():
    payload = request.get_json(silent=True) or {}
    project_name = (payload.get('project_name') or 'Portal Session').strip()
    fname = (payload.get('filename') or '').strip()
    sess = WIKIMAN_SESS.get(project_name) or {}
    content = sess.get('after')
    if not content:
        return jsonify({'error': 'No rewritten content available'}), 400
    # Build default filename
    if not fname:
        page = (sess.get('page') or 'page').replace(' ', '_')
        section = (sess.get('section') or 'section').replace(' ', '_')
        from datetime import datetime
        fname = f"wikiman_after_{page}_{section}_{datetime.utcnow().isoformat().replace(':','-').split('.')[0]}.wikitext"
    out_path = OUTPUT_DIR / fname
    out_path.write_text(content, encoding='utf-8')
    return jsonify({'ok': True, 'path': str(out_path)})


@app.post('/api/project/new')
def project_new():
    if WikiManNarrativeTracker is None:
        return jsonify({'error': 'Narrative tracker unavailable'}), 500
    payload = request.get_json(silent=True) or {}
    name = (payload.get('project_name') or '').strip()
    desc = (payload.get('description') or '').strip() or None
    if not name:
        return jsonify({'error': 'project_name is required'}), 400
    tracker = WikiManNarrativeTracker()
    tracker.start_project(name, desc)
    out_path = OUTPUT_DIR / f'project_{name.lower().replace(" ", "_")}.json'
    export = tracker.export_narrative(str(out_path))
    if WikiManGraphVisualizer is not None:
        vis = WikiManGraphVisualizer()
        vis.generate_html_files()
    projects = _list_projects_items()
    return jsonify({'ok': True, 'project_path': str(out_path), 'export': export, 'projects': projects})


@app.post('/api/project/add_note')
def project_add_note():
    if WikiManNarrativeTracker is None:
        return jsonify({'error': 'Narrative tracker unavailable'}), 500
    payload = request.get_json(silent=True) or {}
    project_name = (payload.get('project_name') or 'Portal Session').strip()
    text = (payload.get('text') or '').strip()
    note_type = (payload.get('type') or 'note').strip()
    source_url = (payload.get('source_url') or '').strip() or None
    if not text:
        return jsonify({'error': 'text is required'}), 400
    tracker = WikiManNarrativeTracker()
    tracker.switch_project(project_name)
    note = tracker.add_note(text, context=f'portal_{note_type}', source_url=source_url)
    out_path = OUTPUT_DIR / f'project_{project_name.lower().replace(" ", "_")}.json'
    export = tracker.export_narrative(str(out_path))
    if WikiManGraphVisualizer is not None:
        vis = WikiManGraphVisualizer()
        vis.generate_html_files()
    return jsonify({'ok': True, 'note': note, 'project_path': str(out_path), 'export': export})


@app.get('/')
def root_index():
    return send_from_directory(app.static_folder, 'index.html')


@app.get('/<path:filename>')
def assets(filename):
    return send_from_directory(app.static_folder, filename)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 5056)), debug=True)
