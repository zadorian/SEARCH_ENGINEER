"""TrailBlazer integration helpers for the WIKIMAN MCP server."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import threading
import tempfile

from flow_manager import FlowManager, FlowManagerError, FlowNotFoundError
from gemini_fetcher import GeminiFetcher
from scripts.export_metrics_summary import aggregate, load_entries
from trailblazer.player import TrailScriptPlayer, TrailRunSummary
from trailblazer.recorder import record_trailscript
from trailblazer.schema import TrailScript, TrailScriptParam
from trailblazer.storage import list_trailscripts, load_trailscript, save_trailscript

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

FLOW_MANAGER_FACTORY = FlowManager
FETCHER_FACTORY = GeminiFetcher

DEFAULT_LOGS_ROOT = Path("trail_runs")
DEFAULT_METRICS_PATH = Path("logs") / "trail_metrics.jsonl"
DEFAULT_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)

_RECORD_JOBS: Dict[str, TrailBlazerJob] = {}
_RECORD_LOCK = threading.Lock()


def _stop_signal_path(flow_id: str) -> Path:
    return Path(tempfile.gettempdir()) / f"wikiman-recording-stop-{flow_id}.signal"


def _record_store(job: TrailBlazerJob) -> TrailBlazerJob:
    with _RECORD_LOCK:
        _RECORD_JOBS[job.job_id] = job
    return job


@dataclass
class TrailBlazerJob:
    """Represents a long-running TrailBlazer job triggered via MCP."""

    job_id: str
    status: str
    message: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


def list_flows(*, country: Optional[str] = None, source: Optional[str] = None) -> Iterable[Dict[str, Any]]:
    """List TrailScript flows available for replay."""

    results: List[Dict[str, Any]] = []
    fm = _safe_flow_manager()

    for flow_id, version in list_trailscripts():
        try:
            script = load_trailscript(flow_id, version)
        except FileNotFoundError:
            logger.warning("TrailScript missing for %s %s", flow_id, version)
            continue

        if country and not _matches_country(country, flow_id, script):
            continue
        if source and not _matches_source(source, flow_id, script, fm):
            continue

        payload = {
            "flow_id": flow_id,
            "version": version,
            "name": script.meta.name,
            "description": script.meta.description,
            "timestamp": script.meta.timestamp,
            "allow_domains": script.meta.allow_domains,
            "allowed_actions": script.meta.allowed_actions,
            "excluded_actions": script.meta.excluded_actions,
            "params": {key: param.__dict__ for key, param in script.params.items()},
            "steps": len(script.steps),
            "has_transcript": script.transcript is not None,
        }

        if fm:
            try:
                flow_record = fm.get_flow(flow_id)
            except FlowNotFoundError:
                flow_record = None
            if flow_record:
                payload.update(
                    {
                        "published": True,
                        "success_rate": flow_record.success_rate,
                        "execution_count": flow_record.execution_count,
                        "last_used": flow_record.last_used,
                        "source_type": flow_record.source_type,
                        "country_code": flow_record.country_code,
                    }
                )
            else:
                payload["published"] = False
        else:
            payload["published"] = False

        results.append(payload)

    return sorted(results, key=lambda item: (item["flow_id"], item["version"]))


def show_flow(flow_id: str, version: Optional[str] = None) -> Dict[str, Any]:
    """Return full TrailScript definition (meta, params, steps, transcript)."""

    script = load_trailscript(flow_id, version)
    payload = script.to_dict()
    payload["flow_id"] = flow_id
    payload["version"] = script.meta.version
    payload["artifacts"] = {
        "screenshots_dir": script.artifacts.screenshots_dir,
        "raw_event_log": script.artifacts.raw_event_log,
    }
    return payload


def record_flow(payload: Dict[str, Any], *, wait: bool = False) -> TrailBlazerJob:
    """Start a TrailBlazer recording job (asynchronous by default)."""

    job_id = f"record_{uuid.uuid4().hex[:8]}"
    flow_id = payload.get("flow_id")
    stop_signal = _stop_signal_path(flow_id) if flow_id else None
    job_payload: Dict[str, Any] = {}
    if flow_id:
        job_payload["flow_id"] = flow_id
    if stop_signal:
        job_payload["stop_signal"] = str(stop_signal)

    job = TrailBlazerJob(job_id=job_id, status="running", message="Recording started", payload=job_payload)
    _record_store(job)

    def worker() -> None:
        try:
            result = _record_flow_sync(payload, job_id)
            _record_store(result)
        except Exception as exc:  # pragma: no cover - defensive
            _record_store(TrailBlazerJob(job_id=job_id, status="error", message=str(exc)))

    thread = threading.Thread(target=worker, name=f"TrailBlazerRecorder-{job_id}", daemon=True)
    thread.start()

    if wait:
        thread.join()
        final = get_record_job(job_id)
        assert final is not None
        return final
    return job


def get_record_job(job_id: str) -> Optional[TrailBlazerJob]:
    """Fetch a previously started recording job."""

    with _RECORD_LOCK:
        return _RECORD_JOBS.get(job_id)


def stop_recording(job_id: str) -> TrailBlazerJob:
    """Request termination of a running recording job."""

    job = get_record_job(job_id)
    if not job:
        raise ValueError(f"Recording job not found: {job_id}")

    if job.status != "running":
        return job

    stop_signal_str = (job.payload or {}).get("stop_signal") if job.payload else None
    if not stop_signal_str:
        raise ValueError("Stop signal path unavailable for this job")

    stop_signal = Path(stop_signal_str)
    stop_signal.parent.mkdir(parents=True, exist_ok=True)
    stop_signal.touch()

    updated = TrailBlazerJob(
        job_id=job.job_id,
        status=job.status,
        message="Stop requested",
        payload=job.payload,
    )
    return _record_store(updated)


def _record_flow_sync(payload: Dict[str, Any], job_id: str) -> TrailBlazerJob:
    """Blocking recording logic shared by async worker and tests."""

    if "script" in payload:
        script_dict = payload["script"]
        if not isinstance(script_dict, dict):
            raise ValueError("payload['script'] must be a dictionary")
        script = TrailScript.from_dict(script_dict)
        flow_id = payload.get("flow_id") or script.meta.name
        if not flow_id:
            raise ValueError("flow_id is required when importing a TrailScript")

        save_trailscript(flow_id, script)

        if payload.get("publish", False):
            _ensure_flow_registered(flow_id, script, payload)

        message = f"Imported TrailScript {flow_id} ({script.meta.version})"
        return TrailBlazerJob(
            job_id=job_id,
            status="completed",
            message=message,
            payload={
                "flow_id": flow_id,
                "version": script.meta.version,
                "steps": len(script.steps),
            },
        )

    required_fields = ["flow_id", "version", "description", "start_url", "allow_domains"]
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise ValueError(f"Missing required fields for recording: {', '.join(missing)}")

    params = _build_params_from_payload(payload.get("params", {}))
    headless = bool(payload.get("headless", False))

    stop_signal = _stop_signal_path(payload["flow_id"])
    payload.setdefault("stop_signal", str(stop_signal))

    script, screenshot_dir, raw_log = record_trailscript(
        flow_name=payload["flow_id"],
        version=payload["version"],
        description=payload["description"],
        allow_domains=list(payload["allow_domains"]),
        start_url=payload["start_url"],
        params=params,
        headless=headless,
        stop_signal_path=stop_signal,
    )

    save_trailscript(payload["flow_id"], script, screenshots_dir=screenshot_dir, raw_event_log=raw_log)

    if payload.get("publish", False):
        _ensure_flow_registered(payload["flow_id"], script, payload)

    return TrailBlazerJob(
        job_id=job_id,
        status="completed",
        message="Recording finished",
        payload={
            "flow_id": payload["flow_id"],
            "version": script.meta.version,
            "screenshots_dir": str(screenshot_dir),
            "raw_event_log": str(raw_log),
            "stop_signal": str(stop_signal),
        },
    )


def play_flow(
    flow_id: str,
    version: Optional[str],
    params: Optional[Dict[str, Any]],
    *,
    chaos: bool = False,
    dry_run: bool = False,
    use_gemini: bool = False,
) -> Dict[str, Any]:
    """Execute a TrailScript replay and return extracts, summary, and artifacts."""

    script = load_trailscript(flow_id, version)
    fm = _ensure_flow_registered(flow_id, script)

    fetcher = FETCHER_FACTORY()
    player = TrailScriptPlayer(
        fetcher,
        logs_root=DEFAULT_LOGS_ROOT,
        chaos_mode=chaos,
        use_gemini=use_gemini,
        metrics_path=DEFAULT_METRICS_PATH,
    )

    param_values = {k: str(v) for k, v in (params or {}).items()}
    summary = player.play(script, param_values=param_values, dry_run=dry_run)
    summary_dict = summary.to_dict()

    _record_execution(fm, flow_id, summary, param_values)

    extracts = _collect_extracts(summary)
    return {
        "summary": summary_dict,
        "extracts": extracts,
        "chaos_mode": chaos,
        "dry_run": dry_run,
    }


def chaos_run(
    flow_id: str,
    version: Optional[str],
    runs: int,
    params: Optional[Dict[str, Any]],
    *,
    dry_run: bool = False,
    use_gemini: bool = False,
) -> TrailBlazerJob:
    """Launch a chaos replay batch job."""

    if runs < 1:
        raise ValueError("runs must be >= 1")

    script = load_trailscript(flow_id, version)
    fm = _ensure_flow_registered(flow_id, script)

    fetcher = FETCHER_FACTORY()
    player = TrailScriptPlayer(
        fetcher,
        logs_root=DEFAULT_LOGS_ROOT,
        chaos_mode=True,
        use_gemini=use_gemini,
        metrics_path=DEFAULT_METRICS_PATH,
    )

    param_values = {k: str(v) for k, v in (params or {}).items()}
    summaries: List[TrailRunSummary] = []
    for _ in range(runs):
        summary = player.play(script, param_values=param_values, dry_run=dry_run)
        summaries.append(summary)
        _record_execution(fm, flow_id, summary, param_values)

    payload = _summaries_to_payload(summaries)
    job_id = f"chaos_{uuid.uuid4().hex[:8]}"
    return TrailBlazerJob(job_id=job_id, status="completed", payload=payload)


def metrics_summary(limit: int = 50, since: Optional[str] = None, *, path: Optional[Path] = None) -> Dict[str, Any]:
    """Aggregate TrailBlazer metrics for dashboards."""

    metrics_path = path or DEFAULT_METRICS_PATH
    entries = load_entries(metrics_path, since, limit)
    summary = aggregate(entries)
    summary["generated_at"] = datetime.utcnow().isoformat() + "Z"
    summary["path"] = str(metrics_path)
    return summary


def update_policy(
    flow_id: str,
    allowed_actions: Optional[Iterable[str]] = None,
    excluded_actions: Optional[Iterable[str]] = None,
    *,
    version: Optional[str] = None,
    new_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Update TrailScript action policies and persist a new version."""

    script = load_trailscript(flow_id, version)

    if allowed_actions is not None:
        script.meta.allowed_actions = list(allowed_actions)
    if excluded_actions is not None:
        script.meta.excluded_actions = list(excluded_actions)
    if new_version:
        script.meta.version = new_version

    save_trailscript(flow_id, script)
    _ensure_flow_registered(flow_id, script)

    return {
        "flow_id": flow_id,
        "version": script.meta.version,
        "allowed_actions": script.meta.allowed_actions,
        "excluded_actions": script.meta.excluded_actions,
    }


def publish_flow(
    flow_id: str,
    version: Optional[str],
    *,
    country_code: Optional[str] = None,
    source_type: str = "trailblazer",
) -> Dict[str, Any]:
    """Promote a validated TrailScript version for orchestrator use."""

    script = load_trailscript(flow_id, version)
    fm = _ensure_flow_registered(flow_id, script, payload={"country_code": country_code, "source_type": source_type})

    return {
        "flow_id": flow_id,
        "version": script.meta.version,
        "country_code": fm.get_flow(flow_id).country_code if fm else country_code,
        "source_type": source_type,
        "published": True,
    }


def _matches_country(country: str, flow_id: str, script: TrailScript) -> bool:
    token = country.lower()
    if token in flow_id.lower():
        return True
    if token in script.meta.name.lower():
        return True
    return any(token in domain.lower() for domain in script.meta.allow_domains)


def _matches_source(source: str, flow_id: str, script: TrailScript, fm: Optional[FlowManager]) -> bool:
    token = source.lower()
    if token in flow_id.lower():
        return True
    if token in script.meta.description.lower():
        return True
    if fm:
        try:
            flow = fm.get_flow(flow_id)
            return token in flow.source_type.lower()
        except FlowNotFoundError:
            return False
    return False


def _build_params_from_payload(payload: Dict[str, Any]) -> Dict[str, TrailScriptParam]:
    params: Dict[str, TrailScriptParam] = {}
    for name, definition in payload.items():
        if isinstance(definition, TrailScriptParam):
            params[name] = definition
        elif isinstance(definition, dict):
            params[name] = TrailScriptParam(**definition)
        elif isinstance(definition, str):
            params[name] = TrailScriptParam(type=definition)
        else:
            raise ValueError(f"Unsupported param definition for '{name}': {definition!r}")
    return params


def _ensure_flow_registered(flow_id: str, script: TrailScript, payload: Optional[Dict[str, Any]] = None) -> Optional[FlowManager]:
    """Register the TrailScript with FlowManager if possible."""

    fm = _safe_flow_manager()
    if not fm:
        return None

    country_code = (payload or {}).get("country_code")
    if not country_code:
        country_code = flow_id.split("_", 1)[0].lower() if "_" in flow_id else flow_id[:2].lower()

    source_type = (payload or {}).get("source_type") or "trailblazer"

    try:
        fm.get_flow(flow_id)
        fm.delete_flow(flow_id, delete_screenshots=False)
    except FlowNotFoundError:
        pass

    version_major = _major_version(script.meta.version)
    try:
        fm.save_flow(
            flow_id=flow_id,
            version=version_major,
            country_code=country_code,
            source_type=source_type,
            trailscript=script,
        )
    except FlowManagerError as exc:
        logger.error("Failed to register flow %s: %s", flow_id, exc)

    return fm


def _record_execution(fm: Optional[FlowManager], flow_id: str, summary: TrailRunSummary, params: Dict[str, str]) -> None:
    if not fm:
        return

    execution_id = f"exec_{uuid.uuid4().hex[:8]}"
    success = summary.failure_count == 0
    fm.record_execution(
        execution_id=execution_id,
        flow_id=flow_id,
        execution_time_ms=int(summary.duration_ms),
        success=success,
        input_params=params,
        output_data={
            "success_count": summary.success_count,
            "failure_count": summary.failure_count,
            "log_dir": str(summary.log_dir),
            "summary_path": str(summary.summary_path),
        },
    )


def _collect_extracts(summary: TrailRunSummary) -> Dict[str, Any]:
    extracts: Dict[str, Any] = {}
    for result in summary.results:
        if not result.extracts:
            continue
        for key, value in result.extracts.items():
            extracts[f"{result.step_id}:{key}"] = value
    return extracts


def _major_version(version: str) -> int:
    stripped = version.lower().lstrip("v")
    parts = stripped.split(".")
    try:
        return int(parts[0])
    except (ValueError, IndexError):
        return 1


def _summaries_to_payload(summaries: Iterable[TrailRunSummary]) -> Dict[str, Any]:
    items = [summary.to_dict() for summary in summaries]
    failures = sum(item["failure_count"] for item in items)
    success = sum(item["success_count"] for item in items)
    return {
        "runs": len(items),
        "success_total": success,
        "failure_total": failures,
        "summaries": items,
    }


def _safe_flow_manager() -> Optional[FlowManager]:
    try:
        return FLOW_MANAGER_FACTORY()
    except Exception as exc:
        logger.warning("FlowManager unavailable: %s", exc)
        return None
