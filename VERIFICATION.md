# VERIFICATION — Kern + Weg A (CLAUDE.md §8)

Jeder Definition-of-Done-Punkt mit **ausgeführtem Command + Ergebnis**. Stand: nach
M3 (Desktop-Weg fertig & einsetzbar). Interpreter: `.venv/Scripts/python.exe`
(Python 3.13.1), fastmcp 3.4.2, pytest 9.1.1.

> Hinweis Reproduktion: Das Board wird **name-agnostisch** geladen
> (`BoardLibrary("boards").get("A1708")`); der echte Dateiname enthält Leerzeichen.

---

## DoD 1 — `pytest` grün; `scripts/test.sh` grün

```
$ bash scripts/test.sh
== L1 Selftest ==
OK: boardview_mcp.py --selftest
== pytest ==
..........................                                               [100%]
26 passed in 0.44s
```
**OK** — Selftest + 26 Tests grün.

## DoD 2 — `boardview_mcp.py --selftest` grün; M1-Baseline-Assertions grün

```
$ .venv/Scripts/python.exe boardview_mcp.py --selftest ; echo exit=$?
exit=0

$ .venv/Scripts/python.exe -m pytest tests/test_boardview.py -q
......                                                                   [100%]
6 passed in 0.14s
```
**OK** — Baseline exakt getroffen (`board_info` 2838/1354/11833/2329,
`get_part(U7800)` top/168, `get_net(PPBUS_G3H)` 35/38/2,
`shared_nets(U7800,L5001)` nicht verbunden, Fuzzy A1708==820-00875, unbekanntes
Board → KeyError mit Listing). `boardview_mcp.py` unverändert.

## DoD 3 — L1- UND L3-MCP-Server starten und beantworten je einen Tool-Call

**Tool-Call nachweislich (In-Memory-FastMCP-Client):**
```
$ .venv/Scripts/python.exe -m pytest tests/test_boardview_mcp.py tests/test_store_mcp.py -q
..                                                                       [100%]
2 passed in 0.25s
```
- L1: `board_info` → parts=2838; `get_net("PPBUS_G3H")` → part_count=35.
- L3: `start_session` → `log_step` (evidence/confidence/net/designator) →
  `get_session` (1 Step) → `add_known_failure` → `list_known_failures`.

**Stdio-Start nachweislich (Subprozess, stdin offen):**
```
### L1 stdio boot
L1 running (pid 467) — wartet auf stdin
INFO Library: 1 Boards ['MacBook Pro 13 A1708 820-00875 '], aktiv=...
### L3 stdio boot
L3 running (pid 472) — wartet auf stdin
|                                FastMCP 3.4.2                                |
```
**OK** — beide Server starten als stdio-Server und beantworten Tool-Calls.

## DoD 4 — `prompts/diagnosis_system_prompt.md` + Desktop-Setup-Doku vorhanden

```
$ ls prompts/diagnosis_system_prompt.md desktop/SETUP.md desktop/claude_desktop_config.json
desktop/SETUP.md
desktop/claude_desktop_config.json
prompts/diagnosis_system_prompt.md
```
- `prompts/diagnosis_system_prompt.md`: §2 Reliability-Gradient als Regeln, §4
  wörtlich, **operativer Tool-Ablauf** (Start / Mess-Schleife / Abschluss).
- `desktop/claude_desktop_config.json`: **absolute** venv-Python- und Skript-/
  boards-/SQLite-Pfade (Begründung in `desktop/SETUP.md`).
- `desktop/SETUP.md`: Connector-Eintrag, Project-Anlage mit Disziplin-Prompt,
  manuelle Bench-Checkliste.

## DoD 5 — `README.md`, `PROGRESS.md`, `VERIFICATION.md` vorhanden; keine TODO-/Stub-Stellen

```
$ ls README.md PROGRESS.md VERIFICATION.md
PROGRESS.md
README.md
VERIFICATION.md
```
Keine TODO/FIXME/Stub in ausgelieferten Pfaden (`store/`, `prompts/`, `desktop/`,
`tests/`). Das einzige `raise NotImplementedError` in `boardview_mcp.py` ist der
**bewusste Guard** gegen unbekannte Dateiformate (CLAUDE.md §9: nicht raten), kein
unfertiger Pfad.

---

## Reliability-Gradient (§2) — Code-seitig

- L1 (`boardview_mcp.py`) ist die **einzige** Quelle für Netz-/Pin-/Koordinaten-
  Fakten; Werte kommen deterministisch aus der `.brd`, nicht aus einem Modell.
- L3 trennt **evidence** (measured | injected | assumed) und **source**
  (distilled | manual), damit Gemessenes/Bestätigtes von Vermutetem/Geratenem
  unterscheidbar bleibt.
- Weg A: das Modell (Claude Desktop) erhält Fakten **nur** über L1-Tool-Calls; der
  Prompt verbietet das Raten von Netznamen explizit.

## Grenze der automatischen Verifikation (§7)

Ein grüner Trockenlauf beweist die **Mechanik** (Tooling, Gating, Logging, DB),
NICHT, dass das echte Modell die Diagnose-Disziplin an realer Hardware einhält.
Das wird **manuell an der Bench** validiert — Checkliste in `desktop/SETUP.md` §5.
