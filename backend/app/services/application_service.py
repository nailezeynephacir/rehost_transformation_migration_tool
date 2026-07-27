import asyncio
import logging
import zipfile
from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import AppError, InvalidUploadError
from app.engine.application import apply_transformations
from app.services import run_service

logger = logging.getLogger(__name__)

MOCK_PROCESSING_DELAY_SECONDS = 4


async def start_application(new_original: UploadFile, transformations: UploadFile) -> str:
    if not new_original.filename or not new_original.filename.lower().endswith(".zip"):
        raise InvalidUploadError("The 'new_original' upload must be a .zip file.")

    if not transformations.filename or not transformations.filename.lower().endswith(".json"):
        raise InvalidUploadError("The 'transformations' upload must be a .json file.")

    run_id = run_service.create_run(operation="apply")
    run_dir = run_service.get_run_dir(run_id)

    (run_dir / "new_original.zip").write_bytes(await new_original.read())
    (run_dir / "rehost_transformations.json").write_bytes(await transformations.read())

    asyncio.create_task(_process_application(run_id, run_dir))

    return run_id


def _safe_extract_zip(zip_path: Path, destination: Path) -> None:
    # These are user-uploaded archives, so treat every member path as
    # untrusted: reject anything that would resolve outside `destination`
    # before extracting it (zip-slip), the same defense-in-depth pattern
    # used by run_service.get_artifact_path for downloads.
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_path = (destination / member.filename).resolve()

            try:
                member_path.relative_to(destination_resolved)
            except ValueError:
                raise InvalidUploadError(
                    f"The archive '{zip_path.name}' contains an entry that "
                    f"escapes its extraction directory: {member.filename}"
                )

        archive.extractall(destination)


async def _process_application(run_id: str, run_dir) -> None:
    run_service.mark_running(run_id)
    await asyncio.sleep(MOCK_PROCESSING_DELAY_SECONDS)

    try:
        new_original_dir = run_dir / "new_original"
        _safe_extract_zip(run_dir / "new_original.zip", new_original_dir)

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

        # Each generated file becomes its own artifact, listed with its
        # relative path as the name - this is the schema doc's answer to
        # the "third pane" gap, reusing the same list-then-fetch mechanism
        # rather than a separate endpoint.
        artifacts = [
            {"name": "application_report.txt", "type": "application_report"},
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
