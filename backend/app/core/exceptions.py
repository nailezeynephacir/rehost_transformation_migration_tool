from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Base for every error we raise on purpose, carrying the fields the
    standard error response needs. Route/service code should raise this
    (or a subclass) instead of returning ad-hoc error shapes."""

    def __init__(self, code: str, message: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class RunNotFoundError(AppError):
    def __init__(self, run_id: str):
        super().__init__(
            code="run_not_found",
            message=f"No run exists with id: {run_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ArtifactNotFoundError(AppError):
    def __init__(self, run_id: str, artifact_name: str):
        super().__init__(
            code="artifact_not_found",
            message=f"Run {run_id} has no artifact named: {artifact_name}",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidUploadError(AppError):
    def __init__(self, message: str):
        super().__init__(code="invalid_upload", message=message, status_code=status.HTTP_400_BAD_REQUEST)


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message))

    # Starlette's own base HTTPException - raised directly by Starlette's
    # routing for things we never wrote code for, like an unmatched route
    # (404). Registered against the BASE class deliberately: fastapi.HTTPException
    # is a subclass of this, and Starlette's routing raises the base class
    # itself, so a handler registered for the subclass would miss it.
    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body("http_error", str(exc.detail)),
        )

    # FastAPI's own request-validation errors (e.g. a missing required field)
    # get reshaped into the same standard error format, so a malformed
    # request doesn't look different from a deliberate AppError to the frontend.
    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("validation_error", str(exc.errors())),
        )

    # Last resort - anything unexpected still comes back in the standard
    # shape instead of a raw traceback leaking to the frontend.
    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("internal_error", "An unexpected error occurred."),
        )