"""Entry point: `uvicorn app.main:create_app --factory`."""

from app.api.factory import create_app

__all__ = ["create_app"]
