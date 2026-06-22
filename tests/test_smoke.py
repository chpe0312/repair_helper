"""M0-Smoke: Echtes Board lädt name-agnostisch und hat plausible Struktur.

Die exakten Ground-Truth-Zahlen prüft M1 (tests/test_boardview.py). Hier nur:
die Pipeline steht, das echte .brd parst, der Graph ist nicht leer.
"""

from __future__ import annotations


def test_board_loads_name_agnostic(board):
    assert board.parts, "Board hat keine Parts geladen"
    assert board.net_count > 0, "Board hat keine Netze"


def test_fuzzy_resolve_same_file(library):
    assert library.resolve("A1708") == library.resolve("820-00875")
