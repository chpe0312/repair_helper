# Board-Repair Diagnose-Assistent

Lokaler, agentischer Diagnose-Assistent für Board-Level-Repair an Apple-
Logicboards (erste Zielplattform: MacBook Pro 13" A1708 / 820-00875). Vollständige
Spec und Build-Protokoll: siehe [CLAUDE.md](CLAUDE.md).

## Status
- **L1 — Boardview (Ground Truth):** `boardview_mcp.py` (FastMCP, stdio). Vorhanden.
- **L3 — State:** `store/server.py` (FastMCP, SQLite) — sessions/steps/known_failures.
- **Disziplin-Prompt:** `prompts/diagnosis_system_prompt.md` (von beiden Wegen genutzt).
- **Weg A (Claude Desktop):** nutzbar — siehe [`desktop/SETUP.md`](desktop/SETUP.md).
- **M4 (Weg B Standalone) / M5 (Schematic):** später.

## Setup
```bash
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# POSIX: .venv/bin/python -m pip install -r requirements.txt
```

## Tests
```bash
bash scripts/test.sh          # Selftest (L1) + pytest (inkl. M1-Baseline)
```

## Server lokal starten (stdio)
```bash
.venv/Scripts/python.exe boardview_mcp.py boards --board A1708          # L1
BOARDREPAIR_DB=store/state.sqlite .venv/Scripts/python.exe store/server.py  # L3
```

Boards liegen in `boards/` (`.brd`/`.json`). Boards werden **name-agnostisch**
über Fuzzy-Resolve angesprochen (`A1708`, `820-00875`).

## Weg A — Claude Desktop
Connector-Config-Vorlage und Anleitung: [`desktop/SETUP.md`](desktop/SETUP.md).
Diagnose-Disziplin als Project-Instructions:
[`prompts/diagnosis_system_prompt.md`](prompts/diagnosis_system_prompt.md).
