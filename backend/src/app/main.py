"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger, new_request_id
from app.core.ratelimit import limiter

logger = get_logger("app")

configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Fail fast when production is configured unsafely; dev/test keep the
    # friendly warning behaviour.
    if settings.is_production:
        settings.ensure_production_safe()
    else:
        for problem in settings.validate_runtime():
            logger.warning("config.problem", problem=problem)
    # Ensure upload storage exists.
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    if settings.seed_on_startup:
        _run_startup_seed()
    yield


def _run_startup_seed() -> None:
    """Idempotent synthetic-data seed for local development (SEED_ON_STARTUP=true)."""
    from app.core.config import settings as cfg

    if cfg.environment == "production":
        logger.warning("seed.refused", reason="production")
        return
    from app.db.session import SessionLocal
    from app.seed import seed

    logger.info("seed.start")
    with SessionLocal() as db:
        summary = seed(db=db)
        db.commit()
    logger.info("seed.done", summary=summary)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "Privacy-first Student Placement Navigation Platform. "
        "Eligibility is deterministic and institution-confirmed; AI output is advisory only."
    ),
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


_FIXED_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


def security_headers(*, strict_transport: bool) -> dict[str, str]:
    """Response headers applied to every request. HSTS is only sent when the
    deployment runs over TLS (production), so local plain-HTTP dev is not
    accidentally pinned."""
    headers = dict(_FIXED_SECURITY_HEADERS)
    if strict_transport:
        headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return headers


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = new_request_id()
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    for name, value in security_headers(strict_transport=settings.is_production).items():
        response.headers.setdefault(name, value)
    return response


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code, **exc.extra},
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Rate limit exceeded. Please slow down.", "code": "rate_limited"},
    )


@app.get("/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "institution": settings.institution.code,
    }


app.include_router(api_router, prefix=settings.api_prefix)