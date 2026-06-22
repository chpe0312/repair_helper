"""M1 — Ground-Truth-Baseline gegen das echte Board.

Diese Assertions sind das Regressions-Netz für `boardview_mcp.py` (L1). Sie laufen
in JEDEM pytest-Lauf mit. Werte stammen aus genau dieser .brd-Datei
(MacBook Pro 13 A1708 / 820-00875). Bei Abweichung NICHT den Parser anpassen,
sondern Ursache klären (CLAUDE.md §6 M1).

Board wird name-agnostisch über die `board`/`library`-Fixtures geladen
(siehe conftest.py) — kein hartkodierter Dateipfad.
"""

from __future__ import annotations

import pytest

from boardview_mcp import (
    _info_payload,
    net_report,
    part_report,
    shared_report,
)


def test_board_info_baseline(board):
    info = _info_payload(board)
    assert info["parts"] == 2838
    assert info["testpoints"] == 1354
    assert info["pins"] == 11833
    assert info["nets"] == 2329


def test_get_part_u7800(board):
    rep = part_report(board, "U7800")
    assert rep["side"] == "top"
    assert rep["pin_count"] == 168


def test_get_net_ppbus_g3h(board):
    rep = net_report(board, "PPBUS_G3H")
    assert rep["part_count"] == 35
    assert rep["pin_count"] == 38
    assert len(rep["testpoints"]) == 2


def test_shared_nets_u7800_l5001_not_connected(board):
    rep = shared_report(board, "U7800", "L5001")
    assert rep["connected"] is False
    assert rep["shared_nets"] == []


def test_fuzzy_resolve_same_file(library):
    assert library.resolve("A1708") == library.resolve("820-00875")


def test_unknown_board_raises_with_listing(library):
    with pytest.raises(KeyError) as exc:
        library.get("A9999")
    msg = str(exc.value)
    # Fehlermeldung muss die verfügbaren Boards auflisten.
    assert "A9999" in msg
    for bid in library.ids():
        assert bid in msg
