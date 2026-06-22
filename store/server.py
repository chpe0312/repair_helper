#!/usr/bin/env python3
"""L3 State-MCP-Server — Sitzungen, Schritte, bekannte Fehlerbilder (SQLite).

Eigenständiger FastMCP-Server (stdio), der die reine SQLite-Schicht
(`store/db.py`) als MCP-Tools exponiert. So teilen sich **beide Deployments**
(Weg A — Claude Desktop, Weg B — Standalone) denselben Sitzungs-/Wissensspeicher.

Start
-----
    python store/server.py                       # Default-DB: store/state.sqlite
    BOARDREPAIR_DB=/pfad/state.sqlite python store/server.py

DB-Pfad: Umgebungsvariable ``BOARDREPAIR_DB`` (sonst ``store/state.sqlite``).
Tests setzen den Pfad via ``configure(path)`` und sprechen den Server über den
In-Memory-FastMCP-Client an — kein Subprozess, kein Live-Modell.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Callable, Optional

from fastmcp import FastMCP

# Paket-robust: läuft sowohl als `python store/server.py` als auch als Import.
try:
    from store import db
except ImportError:  # direkter Skriptstart ohne Repo-Root im Pfad
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from store import db

mcp = FastMCP("boardrepair-state")

_DEFAULT_DB = Path(__file__).resolve().parent / "state.sqlite"
_CONN: Optional[sqlite3.Connection] = None
_LOCK = threading.Lock()


def _db_path() -> str:
    return os.environ.get("BOARDREPAIR_DB", str(_DEFAULT_DB))


def configure(path: str) -> None:
    """DB (neu) verbinden — für Tests/expliziten Setup. Schließt alte Verbindung."""
    global _CONN
    with _LOCK:
        if _CONN is not None:
            _CONN.close()
        _CONN = db.connect(path)


def conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        _CONN = db.connect(_db_path())
    return _CONN


def _run(fn: Callable, *args, **kwargs):
    """DB-Funktion threadsicher ausführen (FastMCP ruft Tools im Threadpool)."""
    with _LOCK:
        return fn(conn(), *args, **kwargs)


# --------------------------------------------------------------------------- #
# sessions                                                                     #
# --------------------------------------------------------------------------- #


@mcp.tool
def start_session(board_id: str, symptom: Optional[str] = None) -> dict:
    """Neue Diagnose-Sitzung für ein Board anlegen (Status 'open')."""
    return _run(db.start_session, board_id, symptom)


@mcp.tool
def get_session(session_id: int) -> dict:
    """Sitzung inkl. aller protokollierten Schritte holen."""
    return _run(db.get_session, session_id, with_steps=True)


@mcp.tool
def list_sessions(board_id: Optional[str] = None) -> list[dict]:
    """Sitzungshistorie, optional nach board_id gefiltert."""
    return _run(db.list_sessions, board_id)


@mcp.tool
def update_session(
    session_id: int,
    status: Optional[str] = None,
    outcome: Optional[str] = None,
) -> dict:
    """Status (open|resolved|abandoned) und/oder Outcome einer Sitzung setzen."""
    return _run(db.update_session, session_id, status=status, outcome=outcome)


# --------------------------------------------------------------------------- #
# steps                                                                        #
# --------------------------------------------------------------------------- #


@mcp.tool
def log_step(
    session_id: int,
    measurement_point: str,
    evidence: str,
    expected: Optional[str] = None,
    actual: Optional[str] = None,
    finding: Optional[str] = None,
    hypothesis: Optional[str] = None,
    confidence: Optional[int] = None,
    net: Optional[str] = None,
    designator: Optional[str] = None,
) -> dict:
    """Messschritt protokollieren. evidence: measured|injected|assumed (Pflicht).

    net/designator als eigene Felder (gegen L1 auswertbar); confidence in % (0..100).
    """
    return _run(
        db.log_step,
        session_id,
        measurement_point,
        evidence,
        expected=expected,
        actual=actual,
        finding=finding,
        hypothesis=hypothesis,
        confidence=confidence,
        net=net,
        designator=designator,
    )


# --------------------------------------------------------------------------- #
# known_failures                                                               #
# --------------------------------------------------------------------------- #


@mcp.tool
def add_known_failure(
    board_id: str,
    symptom: str,
    cause: Optional[str] = None,
    fix: Optional[str] = None,
    source: str = "manual",
    source_session_id: Optional[int] = None,
) -> dict:
    """Bekanntes Fehlerbild eintragen. source: distilled|manual (Herkunft)."""
    return _run(
        db.add_known_failure,
        board_id,
        symptom,
        cause=cause,
        fix=fix,
        source=source,
        source_session_id=source_session_id,
    )


@mcp.tool
def get_known_failure(kf_id: int) -> dict:
    """Ein bekanntes Fehlerbild per ID holen."""
    return _run(db.get_known_failure, kf_id)


@mcp.tool
def list_known_failures(board_id: Optional[str] = None) -> list[dict]:
    """Bekannte Fehlerbilder, optional nach board_id gefiltert."""
    return _run(db.list_known_failures, board_id)


@mcp.tool
def update_known_failure(
    kf_id: int,
    symptom: Optional[str] = None,
    cause: Optional[str] = None,
    fix: Optional[str] = None,
    source: Optional[str] = None,
) -> dict:
    """Felder eines bekannten Fehlerbilds aktualisieren."""
    return _run(
        db.update_known_failure,
        kf_id,
        symptom=symptom,
        cause=cause,
        fix=fix,
        source=source,
    )


@mcp.tool
def delete_known_failure(kf_id: int) -> dict:
    """Ein bekanntes Fehlerbild löschen."""
    return _run(db.delete_known_failure, kf_id)


def main() -> None:
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
