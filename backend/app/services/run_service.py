import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.exceptions import ArtifactNotFoundError, RunNotFoundError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_run_dir(run_id: str) -> Path:
    return settings.RUNS_DIR / run_id


def _state_path(run_id: str) -> Path:
    return get_run_dir(run_id) / "run.json"


def _write_state(run_id: str, state: Dict[str, Any]) -> None:
    _state_path(run_id).write_text(json.dumps(state, indent=2))


def _read_state(run_id: str) -> Dict[str, Any]:
    # This is what makes state survive a server restart - the sibling
    # team's requirement from Friday. If run.json isn't there, the run
    # (from this server's point of view) doesn't exist.
    path = _state_path(run_id)
    if not path.exists():
        raise RunNotFoundError(run_id)
    return json.loads(path.read_text())


def create_run(operation: str, target_macros: Optional[List[str]] = None) -> str:
    run_id = uuid.uuid4().hex[:12]
    run_dir = get_run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=False)

    state = {
        "run_id": run_id,
        "operation": operation,
        "status": "queued",
        "created_at": _now(),
        "started_at": None,
        "completed_at": None,
        "error": None,
        "available_artifacts": [],
        "summary": None,
        "results": None,
        "target_macros": target_macros,
    }
    _write_state(run_id, state)
    return run_id


def mark_running(run_id: str) -> None:
    state = _read_state(run_id)
    state["status"] = "running"
    state["started_at"] = _now()
    _write_state(run_id, state)


def mark_completed(run_id: str, summary: Dict[str, int], results: List[Dict[str, Any]], artifacts: List[Dict[str, str]]) -> None:
    state = _read_state(run_id)
    state["status"] = "completed"
    state["completed_at"] = _now()
    state["summary"] = summary
    state["results"] = results
    state["available_artifacts"] = artifacts
    _write_state(run_id, state)


def mark_failed(run_id: str, error: str) -> None:
    state = _read_state(run_id)
    state["status"] = "failed"
    state["completed_at"] = _now()
    state["error"] = error
    _write_state(run_id, state)


def get_run_response(run_id: str) -> Dict[str, Any]:
    # Shapes this into exactly one of the three RunResponse variants,
    # depending on status - matches the schema doc's "shape changes
    # based on status" design.
    state = _read_state(run_id)

    if state["status"] in ("queued", "running"):
        return {
            "run_id": state["run_id"],
            "operation": state["operation"],
            "status": state["status"],
            "created_at": state["created_at"],
            "started_at": state["started_at"],
            "target_macros": state.get("target_macros"),
        }

    if state["status"] == "failed":
        return {
            "run_id": state["run_id"],
            "operation": state["operation"],
            "status": "failed",
            "error": state["error"],
        }

    return {
        "run_id": state["run_id"],
        "operation": state["operation"],
        "status": "completed",
        "completed_at": state["completed_at"],
        "target_macros": state.get("target_macros"),
        "summary": state["summary"],
        "results": state["results"],
        "artifacts": state["available_artifacts"],
    }


def list_artifacts(run_id: str) -> List[Dict[str, str]]:
    return _read_state(run_id)["available_artifacts"]


def get_artifact_path(run_id: str, artifact_name: str) -> Path:
    # Layer 1: the name must be one this run actually declared as an
    # artifact - rejects anything not explicitly on the allowlist,
    # including path-traversal attempts, before any path is even built.
    allowed_names = {artifact["name"] for artifact in list_artifacts(run_id)}
    if artifact_name not in allowed_names:
        raise ArtifactNotFoundError(run_id, artifact_name)

    run_dir = get_run_dir(run_id).resolve()
    resolved_path = (run_dir / artifact_name).resolve()

    # Layer 2: defense in depth, matching resolve_project_file() in the
    # real apply_transformations.py - confirm the resolved path never
    # actually leaves this run's own folder, even though layer 1 should
    # already make that impossible for anything we ourselves generated.
    try:
        resolved_path.relative_to(run_dir)
    except ValueError:
        raise ArtifactNotFoundError(run_id, artifact_name)

    return resolved_path