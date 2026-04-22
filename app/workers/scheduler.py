import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.config import get_settings
from app.services.scanner_service import scan_all

log = logging.getLogger(__name__)
settings = get_settings()

_scheduler: BackgroundScheduler | None = None


def _run_scan():
    log.info("Scheduled scan triggered")
    try:
        result = scan_all()
        log.info("Scheduled scan done: %s", result)
    except Exception as exc:
        log.exception("Scheduled scan exception: %s", exc)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.add_job(
        _run_scan,
        trigger=IntervalTrigger(minutes=settings.scan_interval_minutes),
        id="scan_all",
        name="Discogs marketplace scan",
        replace_existing=True,
        misfire_grace_time=60,
    )
    _scheduler.start()
    log.info("Scheduler started: interval=%dmin", settings.scan_interval_minutes)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        log.info("Scheduler stopped")


def get_next_run() -> str | None:
    if not _scheduler:
        return None
    job = _scheduler.get_job("scan_all")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


def is_running() -> bool:
    return bool(_scheduler and _scheduler.running)
