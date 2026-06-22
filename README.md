# Board-Repair Diagnose-Assistent

Lokaler, agentischer Diagnose-Assistent für Board-Level-Repair an Apple-
Logicboards (erste Zielplattform: MacBook Pro 13" A1708 / 820-00875). Vollständige
Spec und Build-Protokoll: siehe [CLAUDE.md](CLAUDE.md).

## Status
- **L1 — Boardview (Ground Truth):** `boardview_mcp.py` (FastMCP, stdio). Vorhanden.
- **M0–M3 (gemeinsamer Kern + Weg A / Claude Desktop):** in Arbeit.
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

## L1-Server lokal starten
```bash
.venv/Scripts/python.exe boardview_mcp.py boards --board A1708   # stdio
```

Boards liegen in `boards/` (`.brd`/`.json`). Boards werden **name-agnostisch**
über Fuzzy-Resolve angesprochen (`A1708`, `820-00875`).
