# Repository Guidelines

## Project Structure & Module Organization

- `backend/` runs the Node/Express API (`server.js`, `database.js`, `embeddings.js`) with SQLite files kept beside the code; treat `web-tracker.db*` as disposable local state.
- `backend/scripts/health-check.js` powers the `npm run check` probe; update it whenever new health surfaces are added.
- `extension/` contains the Chrome extension UI: background/service worker code, content overlays, dashboards (`search.html` + `search.js`), and design assets in `icons/` and `search-engine-02.css`.
- Shared assets live directly in each module; there is no global `src/`, so keep backend and extension concerns isolated.

## Build, Test, and Development Commands

- `cd backend && npm install` is required once; use `npm run dev` for hot reload (reads `PORT` from `.env`, default 5001).
- `npm run start` launches the server without file watching and is what the launcher script wraps in production-like scenarios.
- `npm run check` executes the health probe against the running backend; run it before handing off work.
- Load the extension via `chrome://extensions` → “Load unpacked” → `extension/`; refreshing the extension is the fastest way to test UI changes.

## Coding Style & Naming Conventions

- JavaScript is ES module-based with 2-space indentation, trailing semicolons, and `const`/`let` over `var`; match existing camelCase for functions and snake_case only for persisted fields.
- Frontend code must follow the Search_Engineer.02 design system: uppercase labels, pill buttons, no inline styles, and the restricted color palette (`#000000`, `#ffffff`, `#00b341`, `#d31919`, `#0066ff`).
- Keep filenames kebab-case in the extension (`entity-overlay.js`, `dark-mode.css`) and descriptive camelCase exports in the backend.

## Testing Guidelines

- There is no automated test suite yet; rely on `npm run check` plus manual verification.
- When testing manually, start the backend, confirm the `/health` endpoint, then reload the extension and exercise tracking, entity extraction, and overlay toggles (`Cmd/Ctrl+Shift+E`).
- Document manual scenarios in your PR so others can replay them; include any relevant console output when diagnosing issues.

## Commit & Pull Request Guidelines

- Git history currently shows a single short summary (`first commit`); follow that brevity but adopt Conventional Commit prefixes (`feat:`, `fix:`, `chore:`) in the imperative mood.
- PRs should include: concise description of the change, before/after screenshots or screencasts for UI updates, notes on manual tests performed, and links to related issues or tickets.
- Keep changes scoped (backend vs. extension) and note any migrations or data backfills required.

## Environment & Security

- Copy `backend/.env.example` to `.env` and provide `FIRECRAWL_API_KEY`, `OPENAI_API_KEY`, and `PORT=5001`; the launcher sanitizes these values but never commits `.env`.
- Treat `web-tracker.db*` as local scratch: purge or reset it before sharing bundles, and do not check it into PRs.
- If you add new secrets or config, extend the launcher messaging and document expected keys here.
