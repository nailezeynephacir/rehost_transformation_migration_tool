import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.services import run_service

logger = logging.getLogger(__name__)

# How often the cleanup sweep runs - not how long a run is kept for
# (that's settings.RUN_RETENTION_HOURS). Kept shorter than the retention
# window so expired runs don't linger long past their actual cutoff.
CLEANUP_INTERVAL_SECONDS = 60 * 60  # 1 hour


async def _run_cleanup_loop() -> None:
    while True:
        try:
            deleted = run_service.cleanup_expired_runs()
            if deleted:
                logger.info("Cleanup removed %d expired run(s).", deleted)
        except Exception:
            # A failed sweep shouldn't take the server down - log it and
            # try again on the next interval.
            logger.exception("Run cleanup sweep failed.")
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    cleanup_task = asyncio.create_task(_run_cleanup_loop())
    yield
    cleanup_task.cancel()


app = FastAPI(title="Rehost Transformation Migration Tool API", lifespan=lifespan)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)