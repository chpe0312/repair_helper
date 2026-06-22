"""Gemeinsame pytest-Fixtures.

Lädt das echte Board **name-agnostisch** über die BoardLibrary aus dem
`boards/`-Verzeichnis. KEIN hartkodierter Dateipfad — der echte Dateiname
enthält Leerzeichen; Fuzzy-Resolve ('A1708' / '820-00875') trifft die Datei
unabhängig von der genauen Schreibweise.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
BOARDS_DIR = REPO_ROOT / "boards"

# boardview_mcp.py liegt im Repo-Root.
sys.path.insert(0, str(REPO_ROOT))

from boardview_mcp import BoardLibrary  # noqa: E402


@pytest.fixture(scope="session")
def boards_dir() -> Path:
    return BOARDS_DIR


@pytest.fixture(scope="session")
def library(boards_dir: Path) -> BoardLibrary:
    """BoardLibrary über das echte boards/-Verzeichnis."""
    lib = BoardLibrary(boards_dir)
    if not lib.ids():
        pytest.skip(f"Keine .brd/.json in {boards_dir} gefunden.")
    return lib


@pytest.fixture(scope="session")
def board(library: BoardLibrary):
    """Das echte A1708-Board, name-agnostisch via Fuzzy-Resolve geladen."""
    return library.get("A1708")
