"""PatchPilot FastAPI Application Entry Point."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx
import hashlib
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from .api import patches, projects, repair
from .core.config import get_settings
from .database import check_db_health, engine, init_db
from .services.meta_client import MetaAPIError, MetaClient, set_shared_http_client
from .models.project import Project
from .models.verification_run import VerificationRun

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("patchpilot")

meta_client = MetaClient()
_meta_status_cache = {"expires": 0.0, "value": None}
_public_request_times = defaultdict(deque)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle handler."""
    logger.info("Initializing PatchPilot database...")
    init_db()
    settings = get_settings()
    shared_client = httpx.AsyncClient(timeout=httpx.Timeout(
        settings.META_API_TIMEOUT, connect=min(10.0, settings.META_API_TIMEOUT)))
    set_shared_http_client(shared_client)
    logger.info(
        "PatchPilot running in %s mode (DEMO_MODE=%s, Model=%s)",
        settings.APP_ENV,
        settings.DEMO_MODE,
        settings.META_MODEL_ID,
    )
    yield
    set_shared_http_client(None)
    await shared_client.aclose()
    logger.info("PatchPilot shutting down...")


app = FastAPI(
    title="PatchPilot API",
    description="Self-Verifying AI Software Engineering Agent API powered by Meta AI (dev.meta.ai Muse Spark)",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in get_settings().ALLOWED_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    settings = get_settings()
    if settings.APP_MODE == "public_demo":
        if request.url.path.endswith("/upload") and request.method == "POST":
            return JSONResponse(status_code=403, content={"error_code": "UPLOAD_DISABLED",
                "message": "Repository uploads are disabled on the public demo."})
        try:
            if int(request.headers.get("content-length", "0")) > 1024 * 1024:
                return JSONResponse(status_code=413, content={"error_code": "REQUEST_TOO_LARGE",
                    "message": "Request body exceeds the public demo limit."})
        except ValueError:
            return JSONResponse(status_code=400, content={"error_code": "INVALID_CONTENT_LENGTH",
                "message": "Invalid request size."})
        protected = (request.url.path.endswith(("/repair-plan", "/patches/generate",
            "/generate-tests", "/repair-loop", "/providers/meta/test")) and request.method == "POST")
        if protected:
            if not settings.PUBLIC_DEMO_ENABLED:
                return JSONResponse(status_code=503, content={"error_code": "PUBLIC_DEMO_DISABLED",
                    "message": "Public Meta-powered actions are temporarily disabled."})
            address = request.client.host if request.client else "unknown"
            key = hashlib.sha256(address.encode("utf-8")).hexdigest()
            now = time.monotonic()
            attempts = _public_request_times[key]
            while attempts and now - attempts[0] >= 3600:
                attempts.popleft()
            if len(attempts) >= 12:
                return JSONResponse(status_code=429, headers={"Retry-After": "3600"},
                    content={"error_code": "RATE_LIMITED", "message": "Public AI request limit reached."})
            attempts.append(now)
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if get_settings().APP_MODE == "public_demo":
        response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(MetaAPIError)
async def meta_error_handler(_request: Request, exc: MetaAPIError):
    status = {"NOT_CONFIGURED": 503, "AUTHENTICATION_FAILED": 401, "RATE_LIMITED": 429,
              "MODEL_NOT_FOUND": 400, "PROVIDER_UNAVAILABLE": 502, "MALFORMED_RESPONSE": 502,
              "DEMO_MODE": 503, "PUBLIC_DEMO_DISABLED": 503,
              "PUBLIC_DAILY_CAP_EXHAUSTED": 429}.get(exc.provider_status, 502)
    return JSONResponse(status_code=status, content={"error_code": exc.provider_status,
        "message": "Meta provider request failed.", "provider_status": exc.provider_status})

# Include API routers
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(patches.router, prefix="/api", tags=["patches"])
app.include_router(repair.router, prefix="/api", tags=["repairs"])


@app.get("/api/health", tags=["health"])
async def health_check():
    """Application health check including database status and verifiable Meta provider state."""
    settings = get_settings()
    db_health = check_db_health()
    meta_status = await get_cached_meta_status()

    overall_status = "ok"
    if db_health.get("status") != "ok":
        overall_status = "degraded"

    return {
        "status": overall_status,
        "app_env": settings.APP_ENV,
        "app_mode": settings.APP_MODE,
        "demo_mode": settings.DEMO_MODE,
        "meta_provider": meta_status,
        "database": db_health,
        "sandbox": {
            "isolation_type": "unavailable",
            "docker_available": False,
            "isolation_level": "NONE; repository execution is disabled",
            "execution_status": "EXECUTION_UNAVAILABLE",
        },
    }


@app.get("/api/health/meta", tags=["health"])
async def check_meta_connectivity():
    """Return cached Meta configuration state without spending tokens."""
    return await get_cached_meta_status()


async def get_cached_meta_status():
    import time
    if _meta_status_cache["value"] is None or time.monotonic() >= _meta_status_cache["expires"]:
        settings = get_settings()
        state = "DEMO_MODE" if settings.DEMO_MODE else ("NOT_CONFIGURED" if not settings.effective_api_key else "CONFIGURED_UNVERIFIED")
        _meta_status_cache.update(expires=time.monotonic() + 60, value={"status": state,
            "connected": False, "provider": "demo" if settings.DEMO_MODE else "meta_ai",
            "model_id": None,
            "provider_capabilities": {"structured_output": True, "tool_calling": True,
                "responses_api_reasoning_continuity": True, "image_input": True,
                "streaming": "not_recorded"},
            "message": "Cached provider configuration status; use the test endpoint for a live request."})
    return _meta_status_cache["value"]


@app.post("/api/providers/meta/test", tags=["providers"])
async def test_meta_provider():
    """Make one explicit minimal provider request."""
    return await meta_client.check_provider_health()


@app.get("/api/providers/meta/status", tags=["providers"])
async def meta_provider_status():
    return await get_cached_meta_status()


@app.get("/api/public/config", tags=["public"])
async def public_config():
    settings = get_settings()
    calls_today = 0
    if settings.APP_MODE == "public_demo":
        try:
            with engine.connect() as connection:
                calls_today = connection.execute(text(
                    "SELECT calls FROM public_meta_daily_usage WHERE usage_day=:day"),
                    {"day": datetime.now(timezone.utc).date().isoformat()}).scalar() or 0
        except Exception:
            calls_today = 0
    return {"mode": settings.APP_MODE,
        "provider_status": (await get_cached_meta_status()).get("status"),
        "execution_backend": settings.EXECUTION_BACKEND,
        "upload_enabled": settings.ENABLE_UPLOAD and settings.APP_MODE != "public_demo",
        "daily_meta_call_cap": settings.PUBLIC_DAILY_META_CALL_CAP,
        "daily_meta_calls_remaining": max(0, settings.PUBLIC_DAILY_META_CALL_CAP - calls_today),
        "max_attempts": settings.PUBLIC_MAX_ATTEMPTS,
        "max_tokens_per_call": settings.PUBLIC_MAX_TOKENS_PER_CALL,
        "demo_enabled": settings.PUBLIC_DEMO_ENABLED}


@app.get("/api/public/stats", tags=["public"])
def public_stats():
    """Expose aggregate counts from recorded database rows only."""
    # Use the ORM for portable, read-only aggregate queries.
    from .database import SessionLocal
    with SessionLocal() as session:
        run_count = session.query(VerificationRun).count()
        verified_count = session.query(VerificationRun).filter(
            VerificationRun.verification_status == "VERIFIED_AGAINST_DEFINED_TESTS"
        ).count()
        project_count = session.query(Project).count()
    return {"projects": project_count, "runs": run_count, "verified_runs": verified_count}


@app.get("/api/evaluation/results", tags=["evaluation"])
def get_evaluation_results():
    """Return reproducible benchmark evaluation results comparing baseline, single-pass, and closed loop."""
    results_path = Path(__file__).resolve().parent.parent.parent / "training" / "evaluation" / "evaluation_results.json"
    if results_path.exists():
        with open(results_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "Evaluation results not generated yet. Run python training/evaluation/evaluate_agent.py."}
