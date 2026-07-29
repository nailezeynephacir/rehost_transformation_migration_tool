from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # How long a run's folder stays on disk before cleanup is expected to remove it.
    RUN_RETENTION_HOURS: int = 24

    # Guards against oversized uploads before they ever hit disk.
    MAX_UPLOAD_SIZE_MB: int = 200

    # Guards against zip bombs: total size once extracted, not just the
    # compressed upload size. Checked in archive_service.py during extraction.
    MAX_EXTRACTED_SIZE_MB: int = 500

    # Guards against zip bombs shaped as many tiny files rather than one huge one.
    MAX_ARCHIVE_FILE_COUNT: int = 5000

    # Where every run's isolated working folder lives.
    RUNS_DIR: Path = Path(__file__).resolve().parent.parent.parent / "runtime" / "runs"

    # Origins allowed to call this API from a browser (the Vue dev server, for now).
    CORS_ALLOWED_ORIGINS: list[str] = ["http://localhost:5173"]

    class Config:
        env_prefix = "REHOST_"


settings = Settings()