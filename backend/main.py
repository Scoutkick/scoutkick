import logging
import os
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from backend.src.api.router import api_router
from backend.src.api.data import router as data_router, pipeline_status
from backend.src.api.deps import get_db_path
from backend.src.storage import create_storage

logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host or "127.0.0.1"


limiter = Limiter(key_func=_get_client_ip, default_limits=["200/minute", "10/second"])


def _check_db_has_data() -> bool:
    try:
        storage = create_storage("2025")
        return len(storage.load_all_seasons_meta()) > 0
    except Exception as exc:
        logger.warning("DB check failed: %s", exc)
        return False


def _get_seasons_in_db() -> list[str]:
    try:
        storage = create_storage("2025")
        return [m["season"] for m in storage.load_all_seasons_meta()]
    except Exception as exc:
        logger.warning("Failed to load seasons: %s", exc)
        return []


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = get_db_path()
    has_data = _check_db_has_data()
    if not has_data:
        logger.warning(
            "DB is empty (%s). Run 'python backend/run_all_seasons.py' to populate.", db_path,
        )
    else:
        logger.info("DB has existing data — serving. (%s)", db_path)
    yield


app = FastAPI(title="scoutkick EPA API", version="0.1.0", lifespan=lifespan)

# GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS — use specific origins if CORS_ORIGINS is set, otherwise wildcard
cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    logger.info("%s %s %d (%.0fms)", request.method, request.url.path, response.status_code, duration)
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    response.headers["Vary"] = "Origin"
    return response


@app.middleware("http")
async def add_cache_control(request: Request, call_next):
    response = await call_next(request)
    if request.method == "GET" and response.status_code < 400:
        if not response.headers.get("Cache-Control"):
            response.headers["Cache-Control"] = "public, max-age=60, s-maxage=300"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(api_router)
app.include_router(data_router)


@app.get("/")
@limiter.exempt
def root():
    return {
        "name": "scoutkick",
        "version": "0.1.0",
        "docs": "/docs",
        "pipeline": pipeline_status,
    }


@app.get("/v1/pipeline")
@limiter.exempt
def get_pipeline_status():
    return pipeline_status


@app.get("/v1/health")
@limiter.exempt
def health():
    has_data = _check_db_has_data()
    seasons_in_db = _get_seasons_in_db()
    return {
        "status": "ok" if has_data else "degraded",
        "db_has_data": has_data,
        "seasons": seasons_in_db,
        "pipeline": pipeline_status["state"],
        "pipeline_running": pipeline_status["state"] == "running",
    }
