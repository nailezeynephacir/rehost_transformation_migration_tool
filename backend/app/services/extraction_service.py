import asyncio
import logging
from pathlib import Path
from typing import List

from fastapi import UploadFile

from app.core.exceptions import AppError, InvalidUploadError
from app.engine.extraction import extract_transformations
from app.services import run_service
from app.services.archive_service import safe_extract_zip, validate_upload_size

logger = logging.getLogger(__name__)


async def start_extraction(original: UploadFile, rehost: UploadFile, target_macros: List[str]) -> str:
    if not target_macros:
        raise InvalidUploadError("At least one target macro is required.")

    for upload, label in ((original, "original"), (rehost, "rehost")):
        if not upload.filename or not upload.filename.lower().endswith(".zip"):
            raise InvalidUploadError(f"The '{label}' upload must be a .zip file.")

    run_id = run_service.create_run(operation="extract", target_macros=target_macros)
    run_dir = run_service.get_run_dir(run_id)

    # Real upload bytes are actually saved - this part isn't mocked, since
    # it's the part the engine conversion doesn't change at all. Size is
    # validated against the compressed upload here, before anything is
    # written; safe_extract_zip validates the *extracted* size separately
    # once the file is actually opened as a zip.
    original_bytes = await original.read()
    validate_upload_size(original_bytes, original.filename)
    (run_dir / "original.zip").write_bytes(original_bytes)

    rehost_bytes = await rehost.read()
    validate_upload_size(rehost_bytes, rehost.filename)
    (run_dir / "rehost.zip").write_bytes(rehost_bytes)

    # Fire-and-forget: the request returns immediately with run_id, this
    # keeps running independently. asyncio.create_task rather than
    # BackgroundTasks specifically so polling GET /runs/{run_id} can
    # observe "running" before "completed" - proving the async contract
    # shape actually works, not just returning "completed" instantly.
    asyncio.create_task(_process_extraction(run_id, run_dir, target_macros))

    return run_id


async def _process_extraction(run_id: str, run_dir, target_macros: List[str]) -> None:
    run_service.mark_running(run_id)

    try:
        original_dir = run_dir / "original"
        rehost_dir = run_dir / "rehost"

        safe_extract_zip(run_dir / "original.zip", original_dir)
        safe_extract_zip(run_dir / "rehost.zip", rehost_dir)

        engine_result = extract_transformations(
            original_dir=original_dir,
            rehost_dir=rehost_dir,
            transformations_path=run_dir / "rehost_transformations.json",
            report_path=run_dir / "extraction_report.txt",
            target_macros=set(target_macros),
        )

        results = [
            {
                "transformation_id": item.transformation_id,
                "file": item.file,
                "scope": item.scope,
                "function_name": item.function_name,
                "status": item.status,
                "matched_macro": item.matched_macro,
                "opening_line": item.opening_line,
                "reason": item.reason,
                "original_snippet": item.original_snippet,
                "rehost_snippet": item.rehost_snippet,
                # Extraction never produces the applied output, only application does.
                "generated_snippet": None,
            }
            for item in engine_result.results
        ]

        summary = {
            "applied": engine_result.summary.applied,
            "skipped": engine_result.summary.skipped,
            "already_applied": engine_result.summary.already_applied,
        }

        artifacts = [
            {"name": "extraction_report.txt", "type": "extraction_report"},
            {"name": "rehost_transformations.json", "type": "transformation_json"},
        ]

        run_service.mark_completed(run_id, summary=summary, results=results, artifacts=artifacts)

    except AppError as error:
        # AppError's message is already designed to be safe to show a user
        # (see core/exceptions.py), so it can go straight into the run's
        # stored error field.
        run_service.mark_failed(run_id, str(error))

    except Exception:
        # Unlike AppError, an arbitrary exception's message may contain file
        # paths or other internals - keep the same generic wording the
        # exception handlers in core/exceptions.py use for this case, and
        # rely on the server-side log for the actual diagnosable detail.
        logger.exception("Extraction run %s failed unexpectedly.", run_id)
        run_service.mark_failed(run_id, "An unexpected error occurred.")