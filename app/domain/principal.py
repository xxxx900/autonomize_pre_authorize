"""The authenticated caller."""

from app.domain.base import Frozen
from app.domain.enums import Role


class Principal(Frozen):
    """Who is calling and with which role."""

    actor: str
    role: Role
