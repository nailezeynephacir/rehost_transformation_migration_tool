import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import AppError, InvalidUploadError
from app.engine.application import apply_transformations
from app.services import run_service
from app.services.archive_service import safe_extract_zip, validate_upload_size

logger = logging.getLogger(__name__)


async def start_application(new_original: UploadFile, transformations: UploadFile) -> str:
    if not new_original.filename or not new_original.filename.lower().endswith(".zip"):
        raise InvalidUploadError("The 'new_original' upload must be a .zip file.")

    if not transformations.filename or not transformations.filename.lower().endswith(".json"):
        raise InvalidUploadError("The 'transformations' upload must be a .json file.")

    run_id = run_service.create_run(operation="apply")
    run_dir = run_service.get_run_dir(run_id)

    new_original_bytes = await new_original.read()
    validate_upload_size(new_original_bytes, new_original.filename)
    (run_dir / "new_original.zip").write_bytes(new_original_bytes)

    # Not a zip, so no extraction-related risk, but still worth checking
    # against the same upload-size limit - nothing stops someone uploading
    # an arbitrarily large JSON file otherwise.
    transformations_bytes = await transformations.read()
    validate_upload_size(transformations_bytes, transformations.filename)
    (run_dir / "rehost_transformations.json").write_bytes(transformations_bytes)

    asyncio.create_task(_process_application(run_id, run_dir))

    return run_id


async def _process_application(run_id: str, run_dir) -> None:
    run_service.mark_running(run_id)

    try:
        new_original_dir = run_dir / "new_original"
        safe_extract_zip(run_dir / "new_original.zip", new_original_dir)

        output_dir = run_dir / "generated_rehost"

        engine_result = apply_transformations(
            new_original_dir=new_original_dir,
            transformations_file=run_dir / "rehost_transformations.json",
            output_dir=output_dir,
            report_path=run_dir / "application_report.txt",
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
                "generated_snippet": item.generated_snippet,
            }
            for item in engine_result.results
        ]

        summary = {
            "applied": engine_result.summary.applied,
            "skipped": engine_result.summary.skipped,
            "already_applied": engine_result.summary.already_applied,
        }

        # Bundle the whole generated project into one zip too, in addition
        # to the individual per-file artifacts below - individual files for
        # grabbing one thing quickly, the zip for actually taking the whole
        # result to build with. shutil.make_archive appends ".zip" itself.
        shutil.make_archive(str(run_dir / "generated_rehost"), "zip", root_dir=str(output_dir))

        # Each generated file becomes its own artifact, listed with its
        # relative path as the name - this is the schema doc's answer to
        # the "third pane" gap, reusing the same list-then-fetch mechanism
        # rather than a separate endpoint.
        artifacts = [
            {"name": "application_report.txt", "type": "application_report"},
            {"name": "generated_rehost.zip", "type": "generated_project_zip"},
        ] + [
            {"name": f"generated_rehost/{relative_path}", "type": "generated_file"}
            for relative_path in engine_result.generated_files
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
        logger.exception("Application run %s failed unexpectedly.", run_id)
        run_service.mark_failed(run_id, "An unexpected error occurred.")