"""What the worksheet may offer a nurse: the request forms on disk and the summary models."""

from app.domain.base import Frozen


class SummaryModels(Frozen):
    """The default summary model and every model a caller may pick instead."""

    default: str
    choices: list[str]


class Catalog(Frozen):
    """What GET /catalog returns, to fill the worksheet's two dropdowns."""

    request_ids: list[str]
    summary_models: SummaryModels
