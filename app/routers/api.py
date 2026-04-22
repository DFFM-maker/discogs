"""JSON API endpoints for HTMX and async operations."""
import threading
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.deps import get_current_user
from app.models.user import User
from app.services.scanner_service import scan_all, get_scan_state
from app.services.claude_adapter import parse_query, _is_available as claude_ok
from app.workers.scheduler import get_next_run, is_running
from pydantic import BaseModel

router = APIRouter(prefix="/api")
templates = Jinja2Templates(directory="app/templates")


@router.post("/scan/trigger")
def trigger_scan(user: User = Depends(get_current_user)):
    """Manually trigger a scan in background thread."""
    state = get_scan_state()
    if state["running"]:
        return JSONResponse({"status": "already_running"})
    thread = threading.Thread(target=scan_all, daemon=True)
    thread.start()
    return JSONResponse({"status": "started"})


@router.get("/scan/status", response_class=HTMLResponse)
def scan_status(request: Request, user: User = Depends(get_current_user)):
    """Return updated scan pill partial for HTMX polling."""
    state = get_scan_state()
    next_run = get_next_run()
    ctx = {
        "request": request,
        "scan_running": state["running"],
        "last_scan_at": state.get("last_run_at"),
        "next_run": next_run,
        "worker_ok": is_running(),
    }
    return templates.TemplateResponse("_partials/scan_pill.html", ctx)


class AIParseBody(BaseModel):
    query: str


@router.post("/wishlist/ai-parse")
def ai_parse(body: AIParseBody, user: User = Depends(get_current_user)):
    """Parse natural language query into structured filters."""
    if not claude_ok():
        return JSONResponse({"error": "Claude not available"}, status_code=503)
    result = parse_query(body.query)
    if not result:
        return JSONResponse({"error": "Parse failed"}, status_code=422)
    return JSONResponse(result)
