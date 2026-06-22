"""M2 — Unit-Tests der reinen L3-SQLite-Schicht (store/db.py).

Deckt CRUD, board_id-Filter, Enum-/Range-Validierung, FK-Verhalten und
Persistenz über Neustart ab.
"""

from __future__ import annotations

import sqlite3

import pytest

from store import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "state.sqlite")
    yield c
    c.close()


# ---- sessions ------------------------------------------------------------- #


def test_start_and_get_session(conn):
    s = db.start_session(conn, "A1708", symptom="kein Power")
    assert s["board_id"] == "A1708"
    assert s["status"] == "open"
    assert s["symptom"] == "kein Power"
    full = db.get_session(conn, s["id"])
    assert full["steps"] == []


def test_get_unknown_session_raises(conn):
    with pytest.raises(KeyError):
        db.get_session(conn, 999)


def test_update_session_status_and_outcome(conn):
    s = db.start_session(conn, "A1708")
    upd = db.update_session(conn, s["id"], status="resolved", outcome="U7800 getauscht")
    assert upd["status"] == "resolved"
    assert upd["outcome"] == "U7800 getauscht"


def test_update_session_rejects_bad_status(conn):
    s = db.start_session(conn, "A1708")
    with pytest.raises(ValueError):
        db.update_session(conn, s["id"], status="kaputt")


def test_list_sessions_board_id_filter(conn):
    db.start_session(conn, "A1708")
    db.start_session(conn, "A1708")
    db.start_session(conn, "A1989")
    assert len(db.list_sessions(conn)) == 3
    assert len(db.list_sessions(conn, "A1708")) == 2
    assert len(db.list_sessions(conn, "A1989")) == 1
    assert db.list_sessions(conn, "NOPE") == []


# ---- steps ---------------------------------------------------------------- #


def test_log_step_increments_step_no_and_stores_fields(conn):
    s = db.start_session(conn, "A1708")
    st1 = db.log_step(
        conn,
        s["id"],
        measurement_point="PPBUS_G3H @ TP",
        evidence="measured",
        expected="8.6 V",
        actual="8.6 V",
        net="PPBUS_G3H",
        designator="U7800",
        confidence=90,
    )
    st2 = db.log_step(
        conn, s["id"], measurement_point="PP3V3_S5", evidence="assumed"
    )
    assert st1["step_no"] == 1
    assert st2["step_no"] == 2
    assert st1["net"] == "PPBUS_G3H"
    assert st1["designator"] == "U7800"
    assert st1["evidence"] == "measured"
    assert st1["confidence"] == 90
    full = db.get_session(conn, s["id"])
    assert [x["step_no"] for x in full["steps"]] == [1, 2]


def test_log_step_rejects_bad_evidence(conn):
    s = db.start_session(conn, "A1708")
    with pytest.raises(ValueError):
        db.log_step(conn, s["id"], measurement_point="x", evidence="guessed")


def test_log_step_rejects_out_of_range_confidence(conn):
    s = db.start_session(conn, "A1708")
    with pytest.raises(ValueError):
        db.log_step(
            conn, s["id"], measurement_point="x", evidence="measured", confidence=150
        )


def test_log_step_unknown_session_raises(conn):
    with pytest.raises(KeyError):
        db.log_step(conn, 12345, measurement_point="x", evidence="measured")


# ---- known_failures ------------------------------------------------------- #


def test_known_failure_crud(conn):
    kf = db.add_known_failure(
        conn, "A1708", symptom="kein PP3V3_S5", cause="U7800 PMU", fix="reball/replace"
    )
    assert kf["source"] == "manual"
    got = db.get_known_failure(conn, kf["id"])
    assert got["symptom"] == "kein PP3V3_S5"
    upd = db.update_known_failure(conn, kf["id"], fix="U7800 ersetzen")
    assert upd["fix"] == "U7800 ersetzen"
    res = db.delete_known_failure(conn, kf["id"])
    assert res == {"deleted": kf["id"]}
    with pytest.raises(KeyError):
        db.get_known_failure(conn, kf["id"])


def test_known_failure_board_id_filter(conn):
    db.add_known_failure(conn, "A1708", symptom="a")
    db.add_known_failure(conn, "A1708", symptom="b")
    db.add_known_failure(conn, "A1989", symptom="c")
    assert len(db.list_known_failures(conn, "A1708")) == 2
    assert len(db.list_known_failures(conn, "A1989")) == 1
    assert len(db.list_known_failures(conn)) == 3


def test_known_failure_rejects_bad_source(conn):
    with pytest.raises(ValueError):
        db.add_known_failure(conn, "A1708", symptom="x", source="invented")


def test_known_failure_source_session_provenance(conn):
    s = db.start_session(conn, "A1708")
    kf = db.add_known_failure(
        conn,
        "A1708",
        symptom="bestätigtes Muster",
        source="distilled",
        source_session_id=s["id"],
    )
    assert kf["source"] == "distilled"
    assert kf["source_session_id"] == s["id"]


def test_known_failure_bad_source_session_raises(conn):
    with pytest.raises(KeyError):
        db.add_known_failure(
            conn, "A1708", symptom="x", source="distilled", source_session_id=999
        )


# ---- Constraints / Persistenz --------------------------------------------- #


def test_check_constraint_blocks_direct_bad_insert(conn):
    """DB-CHECK schützt auch bei direktem SQL-Zugriff (nicht nur Python-Guard)."""
    s = db.start_session(conn, "A1708")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO steps (session_id, step_no, measurement_point, evidence) "
            "VALUES (?,?,?,?)",
            (s["id"], 1, "x", "bogus"),
        )


def test_persistence_across_restart(tmp_path):
    path = tmp_path / "persist.sqlite"
    c1 = db.connect(path)
    s = db.start_session(c1, "A1708", symptom="kein Power")
    db.log_step(c1, s["id"], measurement_point="PPBUS_G3H", evidence="measured")
    db.add_known_failure(c1, "A1708", symptom="kein PP3V3_S5", source="manual")
    c1.close()

    c2 = db.connect(path)  # "Neustart": neue Verbindung auf dieselbe Datei
    again = db.get_session(c2, s["id"])
    assert again["symptom"] == "kein Power"
    assert len(again["steps"]) == 1
    assert len(db.list_known_failures(c2, "A1708")) == 1
    c2.close()
