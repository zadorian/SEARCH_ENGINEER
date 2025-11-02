# TrailBlazer / TrailScript Operational Guide

## Overview
- **TrailScript schema** (`trailblazer/schema.py`) captures flow metadata, parameters, steps, transcripts, safety flags, and artifacts.
- **Recorder** (`trailblazer/recorder.py`) launches Playwright Chromium, injects event listeners, captures screenshots and raw events, runs deterministic validation, and emits a TrailScript document.
- **Builder** (`trailblazer/builder.py`) converts low-level events into TrailScript steps with anchors, assertions, and transcript stubs.
- **Persistence** (`trailblazer/storage.py`) stores TrailScripts under `trail_scripts/<flow_id>/<version>/` with zipped screenshots and metadata.
- **Playback** (`trailblazer/player.py`) replays flows via Playwright (with Gemini hooks ready), enforces assertions, captures extracts, and writes per-run artifacts + cost estimates.
- **CLI utilities** (`trailblazer/cli.py`, `run_pipeline.py`) expose recording, playback, management, and reporting commands.
- **Reports** (`trailblazer/reports.py`) list historic runs and load their summaries.
- **Tests** live in `tests/test_trailblazer_*.py` and cover schema, storage, builder, player, and reporting helpers.

## Prerequisites
- Python 3.12+
- `pip install -r requirements.txt`
- Playwright with Chromium:
  - `pip install playwright`
  - `playwright install chromium`
- Gemini Computer Use service (Node) available for real playback (`gemini_fetcher.py`). Until credentials/service are configured, playback runs in deterministic (no-Gemini) mode.
- Clean browser profile when recording (avoid stored cookies, auto-logins).

## Recording a Flow
1. Run `python run_pipeline.py record <flow_id> <version> "<description>" <start_url> <allow_domain...> [param:type ...]`
   - Example: `python run_pipeline.py record hu_opten_search 1.0.0 "HU Opten company search" https://www.opten.hu opten.hu company_name:string`.
2. Interact with the page; TrailBlazer records clicks, typing, scrolls, and screenshots.
3. Press **Enter** in the terminal to stop recording.
4. Deterministic validation replay runs automatically. Failures are surfaced as warnings.
5. Flow persists into SQLite (via `FlowManager`) and TrailScript JSON + zipped screenshots land in `trail_scripts/`.

## Playback
```
python run_pipeline.py play <flow_id> [version] \
  --param name=value \
  [--max-retries N] [--dry-run] [--log-dir PATH]
```
- Creates a unique folder under `trail_runs/<name>/<version>/<timestamp>/`.
- Captures before/after screenshots per step, enforces assertions, extracts state, and estimates token/cost usage.
- Outputs `run_summary.json`, `playback_results.json`, screenshot JPEGs, and seeded prompt history.
- `--dry-run` skips DOM mutations to validate selectors/assertions only.
- When Gemini service is connected, `_apply_action` + prompt generation is already wired for Computer Use calls (see **Outstanding Integration**).

## Reporting & Inspection
- `python run_pipeline.py trailscript list` — list registered TrailScripts.
- `python run_pipeline.py trailscript show <flow_id> [version]` — view stored schema.
- `python run_pipeline.py trailscript diff <flow_id> <vA> <vB>` — unified diff of TrailScripts.
- `python run_pipeline.py trailscript runs <flow_id> <version>` — list recorded run IDs (newest first).
- `python run_pipeline.py trailscript summary <flow_id> <version> [--run-id RUN]` — load `run_summary.json` for a specific or latest run.
- `python run_pipeline.py play ... --chaos` — optional chaos jitter to simulate timing variation during playback.
- `python run_pipeline.py chaos <flow_id> [version] --runs N` — execute multiple chaos-mode replays and aggregate resilience metrics.
- `python run_pipeline.py metrics [--json summary.json]` — summarize `logs/trail_metrics.jsonl` (success/failure counts, chaos runs, token/cost totals, top failures) and optionally dump a JSON report for CI/nightly pipelines.

## Artifacts
- `trail_scripts/<flow>/<version>/script.json` — authoritative TrailScript definition.
- `trail_scripts/<flow>/<version>/screenshots.zip` — JPEG archive (deduplicated by hash).
- `trail_scripts/<flow>/<version>/events.jsonl` — raw recorder events (optional).
- `trail_runs/<flow>/<version>/<run>/run_summary.json` — aggregate metrics (duration, retries, tokens, cost, per-step status).
- `trail_runs/<flow>/<version>/<run>/playback_results.json` — flattened per-step results.
- `trail_runs/<flow>/<version>/<run>/screenshots/*` — before/after action captures.
- `trail_runs/<flow>/<version>/<run>/prompt_seed.json` — seeded transcript turns injected into Gemini prompt history.

## Safety & Validation
- Automatic assertions: url_contains, page_has_text, element_exists, min_items, custom_js.
- Safety flags (`require_confirmation`) pause playback for manual approval (custom callback injectable).
- State propagation via `extracts`/`requires` ensures downstream steps receive necessary parameters.
- Recorder triggers deterministic Playwright validation after capture; playback supports `--dry-run` to re-check selectors before hitting Gemini.
- `meta.allowed_actions` and `meta.excluded_actions` enforce per-flow action policies (TrailScriptPlayer blocks disallowed operations before execution).

## Observability & Costing
- Per-step token estimates (simple heuristic) accumulate into a cost projection (default $0.001 / 1K tokens).
- Structured run summary includes total tokens, cost, retries, and step-level failures.
- Each playback appends a JSON line to `logs/trail_metrics.jsonl` (tokens, cost, success/failure counts, LLM action usage, chaos flag) for ingestion into dashboards—plug this into your observability pipeline or ship upstream as needed.
- `python scripts/export_metrics_summary.py --output metrics-summary.json` generates a standalone JSON report from the metrics log for CI/nightly ingestion.
- See `docs/metrics_pipeline.md` for a step-by-step guide to schedule chaos runs, aggregate metrics, and push dashboards/alerts.

## Analyst Console
- `python webapp/app.py` launches a Flask console (default http://127.0.0.1:5055).
- Navigate to `/trailblazer` to browse flows, inspect metadata, run playback/chaos batches, refresh metrics, update policies, and publish versions—all backed by the MCP handlers.
- Filters allow quick narrowing by country/source; JSON responses (summaries, extracts, metrics) are rendered inline for analyst review.
- Kick off new recordings directly from the console: provide metadata/start URL, optionally publish on completion, and monitor job status (the server streams progress via `trailblazer_record_flow`/`trailblazer_record_status`).

## Gemini Integration
- Configure the Node Computer Use service in `gemini_node_service/` with a valid `GEMINI_API_KEY`, then run it (`npm install && npm start`) or allow `GeminiFetcher(auto_start=True)` to launch it.
- Playback automatically spawns a `GeminiPlanner` when `use_gemini=True`: it calls the service for per-step action suggestions (`llm_actions`, parsed into structured `llm_actions_parsed` with match flags), executes supported actions (navigate, click, hover, type, scroll, wait, drag, key combos, form fill, screenshot capture) and records which suggestion actually ran (`llm_action_applied`).
- Remaining primitives/backlog are tracked in `docs/trailblazer_gemini_backlog.md`.
- Without a running service or when `use_gemini=False`, playback continues deterministically (no network calls).
- Advanced usage: extend `GeminiPlanner` to push local outcomes back to the service or to stream multi-turn confirmations.

## Outstanding Integration Tasks
- Wire real Gemini Computer Use execution: send prompts + inline screenshots via `GeminiFetcher`, handle `function_call` responses, and drive Playwright actions via returned instructions.
- Expand retry matrix for common failures (ElementNotFound, Timeout, SafetyRejected) with targeted recovery (scroll, refresh, re-query).
- Add chaos/integration tests against static Playwright fixtures & sandboxed Gemini.
- Implement cost/log aggregation dashboards (e.g., ship run summaries to `logs/performance.log` or external observability).
- Complete user-facing docs for analysts (recording best practices, parameter tagging, safety approvals).
- Optional: Chrome extension recorder (Phase 3), Streamlit/CLI editor (Phase 4), diff visualizer (Phase 6), chaos testing harness (Phase 7), dashboards (Phase 8), roadmap items (Phase 9).

## Troubleshooting
- **Playwright not installed**: run install commands above; ensure `playwright install chromium`.
- **Validation failures**: inspect `trail_runs/.../playback_results.json` and run `--dry-run` to debug selectors.
- **Missing screenshots**: verify `trail_scripts/.../screenshots.zip`; `trailblazer/cli.py summary` prints stored paths.
- **Gemini unavailable**: playback falls back to deterministic mode; no external calls are made.
- **Permission issues**: ensure working directory allows writing to `trail_scripts/` and `trail_runs/`.

## Quick Smoke Test
```
pytest tests/test_trailblazer_schema.py \
       tests/test_trailblazer_storage.py \
       tests/test_trailblazer_builder.py \
       tests/test_trailblazer_player.py \
       tests/test_trailblazer_player_gemini.py \
       tests/test_trailblazer_reports.py \
       tests/test_trailblazer_chaos.py
```
All tests must pass before shipping updates to TrailBlazer.
