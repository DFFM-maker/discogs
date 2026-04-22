import logging
import logging.config

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.database import engine, Base
from app.routers import auth, dashboard, wishlist, results, settings as settings_router, api
from app.workers.scheduler import start_scheduler, stop_scheduler

settings = get_settings()

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)r}',
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "root": {"level": "INFO" if not settings.debug else "DEBUG", "handlers": ["console"]},
})

log = logging.getLogger(__name__)

app = FastAPI(
    title="LP Monitor",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url=None,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="lpm_session",
    max_age=7 * 24 * 3600,  # 7 days
    https_only=False,       # Set True behind HTTPS proxy
    same_site="lax",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(wishlist.router)
app.include_router(results.router)
app.include_router(settings_router.router)
app.include_router(api.router)


@app.on_event("startup")
def startup():
    # Create tables (idempotent; Alembic handles migrations in production)
    Base.metadata.create_all(bind=engine)
    log.info("Database tables ensured")
    start_scheduler()


@app.on_event("shutdown")
def shutdown():
    stop_scheduler()


@app.exception_handler(302)
async def redirect_handler(request: Request, exc):
    return RedirectResponse(url=exc.headers["Location"], status_code=302)
