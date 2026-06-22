"""L3 — Wissen + Sitzungszustand (reine SQLite-Schicht, ohne MCP).

Diese Schicht ist absichtlich frei von FastMCP-Abhängigkeiten, damit sie direkt
unit-testbar ist. Der MCP-Server (`store/server.py`) ist nur eine dünne Hülle
darum.

Tabellen
--------
- ``sessions``        : eine Diagnose-Sitzung pro Board (board_id, status, outcome).
- ``steps``           : Messschritte einer Sitzung. ``evidence`` trennt GEMESSEN
                        von VERMUTET; ``net``/``designator`` sind eigene Spalten,
                        damit Schritte gegen L1 (Boardview) auswertbar sind.
- ``known_failures``  : bekannte Fehlerbilder pro Board. ``source`` trennt
                        bestätigte (``distilled`` aus einer Sitzung) von manuell
                        eingetragenen (``manual``) Mustern.

Enums werden doppelt abgesichert: Python-Validierung (klare Fehlermeldung) UND
SQLite-CHECK-Constraints (DB bleibt auch bei direktem Zugriff konsistent).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union

# --------------------------------------------------------------------------- #
# Enums                                                                        #
# --------------------------------------------------------------------------- #

SESSION_STATUS = ("open", "resolved", "abandoned")
EVIDENCE = ("measured", "injected", "assumed")
KF_SOURCE = ("distilled", "manual")


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id    TEXT    NOT NULL,
    symptom     TEXT,
    status      TEXT    NOT NULL DEFAULT 'open'
                CHECK (status IN ('open','resolved','abandoned')),
    outcome     TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS steps (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         INTEGER NOT NULL
                       REFERENCES sessions(id) ON DELETE CASCADE,
    step_no            INTEGER NOT NULL,
    measurement_point  TEXT    NOT NULL,
    net                TEXT,
    designator         TEXT,
    expected           TEXT,
    actual             TEXT,
    finding            TEXT,
    hypothesis         TEXT,
    evidence           TEXT    NOT NULL
                       CHECK (evidence IN ('measured','injected','assumed')),
    confidence         INTEGER
                       CHECK (confidence IS NULL OR (confidence BETWEEN 0 AND 100)),
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS known_failures (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    board_id           TEXT    NOT NULL,
    symptom            TEXT    NOT NULL,
    cause              TEXT,
    fix                TEXT,
    source             TEXT    NOT NULL DEFAULT 'manual'
                       CHECK (source IN ('distilled','manual')),
    source_session_id  INTEGER REFERENCES sessions(id) ON DELETE SET NULL,
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_steps_session   ON steps(session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_board  ON sessions(board_id);
CREATE INDEX IF NOT EXISTS idx_kf_board        ON known_failures(board_id);
"""


# --------------------------------------------------------------------------- #
# Connection / Setup                                                           #
# --------------------------------------------------------------------------- #


def connect(path: Union[str, Path]) -> sqlite3.Connection:
    """Verbindung öffnen, Foreign-Keys aktivieren, Schema sicherstellen.

    ``path=":memory:"`` ist für flüchtige Tests erlaubt; ein Dateipfad gibt
    Persistenz über Neustart (s. Test).
    """
    # check_same_thread=False: der FastMCP-Server ruft Tools im Threadpool auf;
    # Zugriffe werden serverseitig per Lock serialisiert (store/server.py).
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def _row(r: Optional[sqlite3.Row]) -> Optional[dict]:
    return dict(r) if r is not None else None


# --------------------------------------------------------------------------- #
# sessions                                                                     #
# --------------------------------------------------------------------------- #


def start_session(
    conn: sqlite3.Connection, board_id: str, symptom: Optional[str] = None
) -> dict:
    """Neue Sitzung für ein Board anlegen (Status 'open')."""
    cur = conn.execute(
        "INSERT INTO sessions (board_id, symptom) VALUES (?, ?)",
        (board_id, symptom),
    )
    conn.commit()
    return get_session(conn, int(cur.lastrowid), with_steps=False)


def get_session(
    conn: sqlite3.Connection, session_id: int, with_steps: bool = True
) -> dict:
    row = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"Sitzung {session_id} nicht gefunden")
    out = _row(row)
    if with_steps:
        out["steps"] = list_steps(conn, session_id)
    return out


def list_sessions(
    conn: sqlite3.Connection, board_id: Optional[str] = None
) -> list[dict]:
    """Sitzungen, optional nach Board gefiltert (Historie pro Board)."""
    if board_id is None:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sessions WHERE board_id = ? ORDER BY id", (board_id,)
        ).fetchall()
    return [_row(r) for r in rows]


def update_session(
    conn: sqlite3.Connection,
    session_id: int,
    status: Optional[str] = None,
    outcome: Optional[str] = None,
) -> dict:
    """Status (open|resolved|abandoned) und/oder freies Outcome setzen."""
    get_session(conn, session_id, with_steps=False)  # existiert? sonst KeyError
    if status is not None:
        _require_enum(status, SESSION_STATUS, "status")
        conn.execute(
            "UPDATE sessions SET status = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (status, session_id),
        )
    if outcome is not None:
        conn.execute(
            "UPDATE sessions SET outcome = ?, updated_at = datetime('now') "
            "WHERE id = ?",
            (outcome, session_id),
        )
    conn.commit()
    return get_session(conn, session_id, with_steps=False)


# --------------------------------------------------------------------------- #
# steps                                                                        #
# --------------------------------------------------------------------------- #


def log_step(
    conn: sqlite3.Connection,
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
    """Einen Messschritt protokollieren.

    ``evidence`` ist PFLICHT und trennt gemessen/injiziert/vermutet explizit.
    ``net``/``designator`` sind eigene (nullable) Spalten für L1-Auswertbarkeit.
    ``step_no`` wird je Sitzung fortlaufend vergeben.
    """
    get_session(conn, session_id, with_steps=False)  # existiert? sonst KeyError
    _require_enum(evidence, EVIDENCE, "evidence")
    if confidence is not None and not (0 <= confidence <= 100):
        raise ValueError(f"confidence muss 0..100 sein, war {confidence}")
    nxt = conn.execute(
        "SELECT COALESCE(MAX(step_no), 0) + 1 FROM steps WHERE session_id = ?",
        (session_id,),
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO steps (session_id, step_no, measurement_point, net, "
        "designator, expected, actual, finding, hypothesis, evidence, "
        "confidence) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            session_id,
            nxt,
            measurement_point,
            net,
            designator,
            expected,
            actual,
            finding,
            hypothesis,
            evidence,
            confidence,
        ),
    )
    conn.execute(
        "UPDATE sessions SET updated_at = datetime('now') WHERE id = ?",
        (session_id,),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM steps WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _row(row)


def list_steps(conn: sqlite3.Connection, session_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM steps WHERE session_id = ? ORDER BY step_no", (session_id,)
    ).fetchall()
    return [_row(r) for r in rows]


# --------------------------------------------------------------------------- #
# known_failures                                                               #
# --------------------------------------------------------------------------- #


def add_known_failure(
    conn: sqlite3.Connection,
    board_id: str,
    symptom: str,
    cause: Optional[str] = None,
    fix: Optional[str] = None,
    source: str = "manual",
    source_session_id: Optional[int] = None,
) -> dict:
    """Bekanntes Fehlerbild eintragen.

    ``source``: 'distilled' (aus bestätigter Sitzung) vs. 'manual' (eingetragen) —
    damit bestätigte Muster von geratenen unterscheidbar bleiben.
    """
    _require_enum(source, KF_SOURCE, "source")
    if source_session_id is not None:
        get_session(conn, source_session_id, with_steps=False)  # FK-Vorprüfung
    cur = conn.execute(
        "INSERT INTO known_failures (board_id, symptom, cause, fix, source, "
        "source_session_id) VALUES (?,?,?,?,?,?)",
        (board_id, symptom, cause, fix, source, source_session_id),
    )
    conn.commit()
    return get_known_failure(conn, int(cur.lastrowid))


def get_known_failure(conn: sqlite3.Connection, kf_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM known_failures WHERE id = ?", (kf_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"known_failure {kf_id} nicht gefunden")
    return _row(row)


def list_known_failures(
    conn: sqlite3.Connection, board_id: Optional[str] = None
) -> list[dict]:
    """Fehlerbilder, optional nach Board gefiltert (board-spezifische Abfrage)."""
    if board_id is None:
        rows = conn.execute(
            "SELECT * FROM known_failures ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM known_failures WHERE board_id = ? ORDER BY id",
            (board_id,),
        ).fetchall()
    return [_row(r) for r in rows]


def update_known_failure(
    conn: sqlite3.Connection,
    kf_id: int,
    symptom: Optional[str] = None,
    cause: Optional[str] = None,
    fix: Optional[str] = None,
    source: Optional[str] = None,
) -> dict:
    get_known_failure(conn, kf_id)  # existiert? sonst KeyError
    fields: list[tuple[str, object]] = []
    if symptom is not None:
        fields.append(("symptom", symptom))
    if cause is not None:
        fields.append(("cause", cause))
    if fix is not None:
        fields.append(("fix", fix))
    if source is not None:
        _require_enum(source, KF_SOURCE, "source")
        fields.append(("source", source))
    if fields:
        sets = ", ".join(f"{name} = ?" for name, _ in fields)
        conn.execute(
            f"UPDATE known_failures SET {sets} WHERE id = ?",
            (*[v for _, v in fields], kf_id),
        )
        conn.commit()
    return get_known_failure(conn, kf_id)


def delete_known_failure(conn: sqlite3.Connection, kf_id: int) -> dict:
    get_known_failure(conn, kf_id)  # existiert? sonst KeyError
    conn.execute("DELETE FROM known_failures WHERE id = ?", (kf_id,))
    conn.commit()
    return {"deleted": kf_id}


def _require_enum(value: str, allowed: tuple[str, ...], field: str) -> None:
    if value not in allowed:
        raise ValueError(
            f"Ungültiger Wert für {field}: {value!r}. Erlaubt: {list(allowed)}"
        )
