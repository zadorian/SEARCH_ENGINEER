# WIKIMAN Portal

A static, dependency-free web UI that merges:
- Communication (chat/notes/decisions/tasks)
- Project system overview (stats + relationships)
- Graph visualization (via vis-network)

## Run

- Option A: Open `index.html` directly in your browser.
- Option B: Serve the folder for reliable fetch paths:
  - `cd wikiman_portal`
  - `python3 -m http.server 8000`
  - Visit `http://localhost:8000/`

- Option C: Use the Flask server (adds chat persistence and API):
  - `python3 wikiman_portal/server.py`
  - Visit `http://127.0.0.1:5056/`
  - Set env vars to override defaults:
    - `WIKIMAN_GRAPH=path/to/graph_data.json`
    - `WIKIMAN_PROJECT=path/to/project.json`

By default, it attempts to load:
- Graph: `../wikiman_graph_web/graph_data.json`
- Project: `../project_dry_b6081f8f.json`

If those aren’t reachable, use the “Load Project JSON” button to select a file manually. The graph source path can be changed in `index.html` under `window.WIKIMAN_DEFAULTS`.

## Notes

- Chat data is stored in `localStorage` and can be exported as JSON.
- Clicking a graph node adds a “Focused node” note to chat.
- Clicking a relationship value in Project will focus the corresponding node in the graph (best-effort string match).
- No backend required; you can integrate an API later if desired.

### Add Note with Source URL (server mode)

- In the Chat pane, use the Optional Source URL field and click “Add + Attach”.
- This creates a narrative note via the API and attaches the URL as a reference; Project and Graph auto-refresh.

## With Flask server

- Buttons enabled: Refresh Graph, Export Project, Commit Chat → Project.
- Commit uses `wikiman_narrative_tracker` to add your chat items as narrative notes (context set from item type), then exports a project JSON into `output/`.
- Refresh Graph uses `wikiman_graph_visualizer` to regenerate `wikiman_graph_web/graph_data.json` so the portal graph reflects latest data.
- Project Switcher: top-bar dropdown lists existing `project_narrative` entries. Selecting one loads that narrative export and reloads the graph.
- New Project: enter a name and optional description, click “New Project” to create a fresh narrative, auto-select it, and regenerate the graph.
- Archive/Delete: use the Archive or Delete buttons (soft-delete) to mark a project as archived/deleted. Deleted projects are hidden from the list by default; archived ones show “(archived)”.
- Undo: click “Undo” to restore a deleted/archived project back to active. It uses the project name in the input field even if it’s not currently visible in the dropdown.
