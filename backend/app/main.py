import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import jobs, models, notify  # noqa: F401  # models: ensure metadata has tables
from .database import get_db
from .error_tracking import init_error_tracking
from .logging_config import configure_logging, request_logging_middleware
from .routers import admin, auth, email_verification, organizations, password_reset, profile, student, student_import, waitlist

configure_logging()
init_error_tracking()  # before the app exists, so Sentry hooks into FastAPI
notify.warn_if_not_sending()



@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start the background jobs (e.g. finalizing abandoned attempts) with the API."""
    task = asyncio.create_task(jobs.run_forever()) if jobs.jobs_enabled() else None
    yield
    if task:
        task.cancel()


# The database schema is managed by Alembic migrations: run `alembic upgrade head`.
app = FastAPI(lifespan=lifespan)

# Comma-separated list of frontend origins allowed to call the API
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)
# Added last so it runs outermost: every request, including CORS preflights, is logged
app.middleware("http")(request_logging_middleware)


@app.get("/health", tags=["Health"])
def health(db: Session = Depends(get_db)):
    """Liveness and database check for uptime monitors and container health checks."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "error", "database": "unreachable"})
    return {"status": "ok", "database": "ok"}


# Include routers AFTER middleware is configured
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(password_reset.router)
app.include_router(email_verification.router)
app.include_router(organizations.router)
app.include_router(student_import.router)
app.include_router(student.router)
app.include_router(waitlist.router)
app.include_router(profile.router)
