from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .routers import auth, meetings, ops, review
from .services import ServiceError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    from . import scheduler
    from .db import SessionLocal
    from .seed import migrate, seed

    migrate()
    with SessionLocal() as db:
        seed(db)
    if settings.scheduler_enabled:
        scheduler.start()
    yield
    scheduler.stop()


def create_app(run_lifespan: bool = True) -> FastAPI:
    app = FastAPI(
        title="Meeting-to-Execution Agent API",
        version="1.0.0",
        description="Transcript ingestion, decision memory, conflict detection, approval-gated task publishing, reminders and digests.",
        lifespan=lifespan if run_lifespan else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(ServiceError)
    async def _service_error(_: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(p) for p in first.get("loc", [])[1:]) or "request"
        return JSONResponse(status_code=422, content={"detail": f"Invalid {field}: {first.get('msg', 'invalid value')}", "errors": exc.errors()})

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/api/health")
    def health():
        return {"ok": True}

    for r in (auth.router, meetings.router, review.router, ops.router):
        app.include_router(r)
    return app


app = create_app()
