"""GET /catalog: the request ids and summary models the worksheet offers."""

from fastapi import APIRouter, Request

from app.api.auditing import audit_call
from app.api.dependencies import CatalogCaller, ServicesDep
from app.domain.catalog import Catalog, SummaryModels
from app.domain.enums import AuditAction, Outcome
from app.loaders.request_file import list_request_ids

router = APIRouter()


@router.get("/catalog", response_model=Catalog)
def get_catalog(request: Request, principal: CatalogCaller, services: ServicesDep) -> Catalog:
    """List the request forms on disk and the allowed summary models, default first."""
    summarizer = services.summarizer
    catalog = Catalog(
        request_ids=list_request_ids(services.settings.request_dirs),
        summary_models=SummaryModels(default=summarizer.model, choices=list(summarizer.models)),
    )
    audit_call(services.audit, principal, request, AuditAction.CATALOG_READ, None, Outcome.OK, 200)
    return catalog
