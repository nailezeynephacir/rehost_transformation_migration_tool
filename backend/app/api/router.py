from fastapi import APIRouter

from app.api.routes import application, artifacts, extraction, health, runs

api_router = APIRouter()
api_router.include_router(health.router)

api_router.include_router(extraction.router)
api_router.include_router(application.router)
api_router.include_router(runs.router)
api_router.include_router(artifacts.router)