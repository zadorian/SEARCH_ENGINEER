"""
TORPEDO path helpers.

TORPEDO lives under `SEARCH_ENGINEER/BACKEND/modules/TORPEDO`, but the shared IO
Matrix data (sources, codes, etc.) lives under `INPUT_OUTPUT/matrix`.

Many TORPEDO components need to locate:
- IO Matrix directory (prefer `INPUT_OUTPUT/matrix`, fallback to `input_output/matrix`)
- Source files (e.g., `sources/news.json`, `sources/corporate_registries.json`)
- Environment file (`.env`)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """
    Best-effort repository root resolution.

    Prefers the nearest parent that contains `INPUT_OUTPUT/matrix`.
    Falls back to `/data` if present.
    """
    here = Path(__file__).resolve()
    # Check canonical location first
    if Path("/data/SEARCH_ENGINEER/BACKEND/modules/input_output/matrix").exists():
        return Path("/data/SEARCH_ENGINEER/BACKEND/modules")
    for parent in [here] + list(here.parents):
        if (parent / "input_output" / "matrix").exists():
            return parent
    return here.parents[0]


@lru_cache(maxsize=1)
def env_file() -> Optional[Path]:
    """
    Resolve a `.env` file location.

    Order:
    1) ENV_FILE env var
    2) `<repo_root>/.env`
    3) `<repo_root>/SEARCH_ENGINEER/.env`
    4) first `.env` found when walking up from this file
    """
    override = os.getenv("ENV_FILE")
    if override:
        p = Path(override).expanduser()
        return p if p.exists() else None

    root = repo_root()
    candidates = [
        root / ".env",
        root / "SEARCH_ENGINEER" / ".env",
    ]
    for p in candidates:
        if p.exists():
            return p

    here = Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        p = parent / ".env"
        if p.exists():
            return p

    return None


@lru_cache(maxsize=1)
def io_matrix_dir() -> Path:
    """
    Resolve IO Matrix directory.

    Order:
    1) IO_MATRIX_DIR env var
    2) `<repo_root>/INPUT_OUTPUT/matrix` (preferred single source of truth)
    3) `<repo_root>/SEARCH_ENGINEER/input_output/matrix` (legacy)
    4) nearest parent match for `INPUT_OUTPUT/matrix` or `input_output/matrix`
    """
    override = os.getenv("IO_MATRIX_DIR")
    if override:
        p = Path(override).expanduser()
        if p.exists():
            return p

    root = repo_root()
    preferred = root / "INPUT_OUTPUT" / "matrix"
    if preferred.exists():
        return preferred

    legacy = root / "SEARCH_ENGINEER" / "input_output" / "matrix"
    if legacy.exists():
        return legacy

    here = Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        for rel in ("INPUT_OUTPUT/matrix", "input_output/matrix"):
            p = parent / rel
            if p.exists():
                return p

    return preferred


def io_sources_dir() -> Path:
    return io_matrix_dir() / "sources"


def news_sources_path() -> Path:
    return io_sources_dir() / "news.json"


def corporate_registries_sources_path() -> Path:
    return io_sources_dir() / "corporate_registries.json"

