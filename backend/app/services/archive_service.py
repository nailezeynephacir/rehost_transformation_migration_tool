import zipfile
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import InvalidUploadError

BYTES_PER_MB = 1024 * 1024


def validate_upload_size(content: bytes, filename: str) -> None:
    # Checked against the COMPRESSED upload itself, before it's even
    # written to disk - the cheap, first-line check. This alone doesn't
    # catch a zip bomb (a tiny compressed file can still expand to
    # gigabytes) - that's what safe_extract_zip's checks below are for.
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * BYTES_PER_MB
    if len(content) > max_bytes:
        raise InvalidUploadError(
            f"'{filename}' is {len(content) / BYTES_PER_MB:.1f} MB, "
            f"which exceeds the {settings.MAX_UPLOAD_SIZE_MB} MB upload limit."
        )


def safe_extract_zip(zip_path: Path, destination: Path) -> None:
    # These are user-uploaded archives, so treat every member as untrusted
    # in two separate ways:
    #  - zip-slip: a member path that resolves outside `destination`
    #  - zip bomb: a small compressed file that expands to something huge,
    #    either as one enormous file or as an enormous number of tiny ones
    # All checks run against the archive's own metadata BEFORE anything is
    # extracted, so a rejected upload never writes a single byte to disk.
    destination.mkdir(parents=True, exist_ok=True)
    destination_resolved = destination.resolve()

    with zipfile.ZipFile(zip_path) as archive:
        members = archive.infolist()

        if len(members) > settings.MAX_ARCHIVE_FILE_COUNT:
            raise InvalidUploadError(
                f"'{zip_path.name}' contains {len(members)} entries, "
                f"which exceeds the {settings.MAX_ARCHIVE_FILE_COUNT} file limit."
            )

        total_uncompressed_size = sum(member.file_size for member in members)
        max_extracted_bytes = settings.MAX_EXTRACTED_SIZE_MB * BYTES_PER_MB
        if total_uncompressed_size > max_extracted_bytes:
            raise InvalidUploadError(
                f"'{zip_path.name}' would expand to "
                f"{total_uncompressed_size / BYTES_PER_MB:.1f} MB, which exceeds "
                f"the {settings.MAX_EXTRACTED_SIZE_MB} MB extracted-size limit."
            )

        for member in members:
            member_path = (destination / member.filename).resolve()

            try:
                member_path.relative_to(destination_resolved)
            except ValueError:
                raise InvalidUploadError(
                    f"The archive '{zip_path.name}' contains an entry that "
                    f"escapes its extraction directory: {member.filename}"
                )

        archive.extractall(destination)