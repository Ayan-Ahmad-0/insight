import json, logging, sys, time, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import errors
from .config import settings
from .db import pool
from .routers import events, meta, metrics

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")
log = logging.getLogger("insight")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=20)
    yield
    pool.close()


app = FastAPI(
    title="Insight API",
    version="1.0.0",
    description="Multi-tenant usage analytics. The organisation is always taken from the "
                "caller's token and can never be supplied in a request.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
)
errors.install(app)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = uuid.uuid4().hex[:12]     # always server-generated
    request.state.org_id = None
    start, status = time.perf_counter(), 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request.state.request_id
        return response
    finally:
        log.info(json.dumps({
            "request_id": request.state.request_id,
            "org_id": request.state.org_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "ms": round((time.perf_counter() - start) * 1000),
        }))


app.include_router(meta.router)
app.include_router(metrics.router)
app.include_router(events.router)