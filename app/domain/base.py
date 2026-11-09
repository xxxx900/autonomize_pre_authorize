"""Shared base class for immutable domain models."""

from pydantic import BaseModel, ConfigDict


class Frozen(BaseModel):
    """A pydantic model whose instances cannot change after construction."""

    model_config = ConfigDict(frozen=True)
