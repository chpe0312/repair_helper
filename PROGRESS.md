# PROGRESS — Board-Repair Diagnose-Assistent

Laufende Milestone-Checkliste. Jeder Haken ist durch ausgeführten Command-Output
belegt (Details in VERIFICATION.md ab M3).

## M0 — Scaffold & grüne Pipeline
- [x] Repo-Layout (§10) angelegt: `store/ prompts/ desktop/ agent/ cli/ tests/ scripts/ schematics/`
- [x] venv `.venv` + gepinnte `requirements.txt` (fastmcp==3.4.2, pytest==9.1.1)
- [x] `scripts/test.sh` (Selftest + pytest)
- [x] `tests/conftest.py` lädt echte `.brd` **name-agnostisch** (BoardLibrary("boards").get("A1708"))
- [x] `py boardview_mcp.py --selftest` läuft fehlerfrei
- [x] echte `.brd` lädt; `pytest` grün (Smoke)

## M1 — L1 härten + Baseline-Tests
- [x] `tests/test_boardview.py` mit exakten Ground-Truth-Assertions
- [x] alle grün — Baseline exakt getroffen, Parser unangetastet (8 passed)

## M2 — L3 State-MCP-Server + Disziplin-Prompt
- [ ] `store/` FastMCP-Server: sessions(+board_id)/steps/known_failures (SQLite)
- [ ] `prompts/diagnosis_system_prompt.md`
- [ ] Unit-Tests (CRUD, board_id-Filter, Persistenz über Neustart); Tool-Call nachweislich

## M3 — Weg A (Claude Desktop)
- [ ] `desktop/` Connector-Config + Setup-Doku; `README.md` vollständig
- [ ] beide MCP-Server starten + beantworten je einen Tool-Call
- [ ] `VERIFICATION.md` (Kern + Weg A)

## M4 — Weg B Standalone (LATER, nur auf Freigabe)
## M5 — Schematic L2 (LATER, nur auf Freigabe)
