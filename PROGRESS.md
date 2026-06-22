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
- [x] `store/db.py` reine SQLite-Schicht + `store/server.py` FastMCP-Server
  - sessions: board_id, status (open|resolved|abandoned), outcome, symptom
  - steps: evidence (measured|injected|assumed), confidence %, net + designator (eigene Spalten)
  - known_failures: source (distilled|manual), source_session_id (FK)
- [x] `prompts/diagnosis_system_prompt.md` (§4 wörtlich + §2 Reliability-Gradient als Regeln)
- [x] Unit-Tests (CRUD, board_id-Filter, Enum-/Range-Guards, CHECK-Constraints, Persistenz über Neustart)
- [x] In-Memory-FastMCP-Client: Server beantwortet Tool-Calls nachweislich (25 passed)

## M3 — Weg A (Claude Desktop)
- [ ] `desktop/` Connector-Config + Setup-Doku; `README.md` vollständig
- [ ] beide MCP-Server starten + beantworten je einen Tool-Call
- [ ] `VERIFICATION.md` (Kern + Weg A)

## M4 — Weg B Standalone (LATER, nur auf Freigabe)
## M5 — Schematic L2 (LATER, nur auf Freigabe)
