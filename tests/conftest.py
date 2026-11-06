from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def resources_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "resources"
