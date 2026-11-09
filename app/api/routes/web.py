"""The two browser pages and their shared static files.

`/` is the nurse worksheet and `/audit/view` the admin audit table. Both are static pages
that need no token to load; each calls the JSON API with the token the person types in.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"

router = APIRouter()


@router.get("/", include_in_schema=False)
def worksheet() -> FileResponse:
    """Serve the nurse worksheet. It calls the evidence API with the token the nurse enters."""
    return FileResponse(WEB_DIR / "index.html")


@router.get("/audit/view", include_in_schema=False)
def audit_view() -> FileResponse:
    """Serve the audit table. It calls GET /audit with the admin token the person enters."""
    return FileResponse(WEB_DIR / "audit.html")


def mount_static(app: FastAPI) -> None:
    """Serve the CSS and JavaScript both pages share at /static."""
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
