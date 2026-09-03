from __future__ import annotations

import copy
from pathlib import Path

import pytest

from rq3.config import Config, load_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Whatever config.yaml currently points at — never a hardcoded filename,
# so switching export does not leave the tests on the previous one.
REAL_EXPORT = load_config().resolve_path("dataset.input_file")


@pytest.fixture
def cfg() -> Config:
    """The real config.yaml — tests run against production settings."""
    return load_config()


@pytest.fixture
def cfg_factory():
    """Build a Config with specific overrides, keeping the real file's shape."""
    base = load_config()

    def make(**overrides: object) -> Config:
        raw = copy.deepcopy(base.raw)
        for dotted, value in overrides.items():
            node = raw
            parts = dotted.split(".")
            for p in parts[:-1]:
                node = node[p]
            node[parts[-1]] = value
        return Config(raw=raw, path=base.path)

    return make


@pytest.fixture
def real_export() -> Path:
    if not REAL_EXPORT.exists():
        pytest.skip(f"real export not present at {REAL_EXPORT}")
    return REAL_EXPORT
