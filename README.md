# Board-Repair Diagnose-Assistent

Lokaler, **agentischer** Diagnose-Assistent für Board-Level-Repair an Apple-
Logicboards. Er führt eine **langsame, schrittweise, fundierte** Fehlersuche statt
einer One-Shot-„Diagnose": pro Runde genau **eine** Messanweisung mit exaktem
Messpunkt und Soll-Wert, dann wird auf den realen Messwert gewartet.

Erste Zielplattform: **MacBook Pro 13" A1708 / 820-00875**.

> Vollständige Spec und das verbindliche Build-Protokoll: **[CLAUDE.md](CLAUDE.md)**.

---

## Warum das so gebaut ist

Bei Board-Repair sind halluzinierte Netznamen oder Pin-Zuordnungen teuer (man misst
am falschen Punkt, tauscht das falsche Bauteil). Deshalb steht über allem ein
**Reliability-Gradient**: jede Aussage trägt eine Vertrauensstufe, und der Code
erzwingt, woher ein Fakt kommen darf.

| Quelle                | Vertrauen           | Regel |
|-----------------------|---------------------|-------|
| **Boardview** (L1)    | belegt              | EINZIGE Quelle für Netz-/Pin-/Koordinaten-Fakten |
| Schematic via VLM (L2)| Vermutung-to-verify | Werte/Topologie; Netz-Identität gegen L1 prüfen |
| Web (Datenblatt)      | Kontext             | nur als Hinweis, Quelle nennen |
| LLM-Gedächtnis        | NICHT trauen        | nie für Connectivity/Netznamen |

→ **Netznamen werden nie geraten.** Jeder Designator/Netzname in einer Messanweisung
muss vorher über ein L1-Tool aus der echten Boardview-Datei stammen.

Eine Boardview-Datei *ist* bereits die Netzliste eines Boards (Parts, Pins, Netze,
Koordinaten, Testpunkte). Sie ist strukturiert — also braucht es **kein
Embedding/RAG**, sondern deterministische Abfrage-Tools. Die Datei ist die Wahrheit,
**keine Datenbank** dazwischen.

---

## Architektur

Zwei austauschbare Orchestrierungs-Wege über **denselben Kern** (L1 + L3 + Prompt):

```
                 ┌─────────────────────────────────────────┐
   Weg A         │  Claude Desktop  (Orchestrator)          │   Weg B (später, M4)
   (nutzbar) ───►│  Project-Prompt = Diagnose-Disziplin     │◄─── Python-CLI + LLMClient
                 └───────────────┬─────────────┬───────────┘
                                 │             │
                  stdio-MCP ┌────▼────┐   ┌────▼─────────┐ stdio-MCP
                            │   L1    │   │     L3       │
                            │Boardview│   │ State (SQLite)│
                            └────┬────┘   └──────┬───────┘
                                 │               │
                   boards/*.brd ─┘               └─ store/state.sqlite
                   (Ground Truth)                   (Sessions/Steps/Failures)
```

- **L1 — Boardview (Ground Truth, deterministisch):** [`boardview_mcp.py`](boardview_mcp.py).
  FastMCP-Server (stdio), lädt obfuskiertes OpenBoardView-`.brd` nativ in einen
  In-Memory-Graph, Multi-Board über eine `BoardLibrary`. Keine DB.
- **L3 — Wissen + Sitzungszustand:** [`store/`](store/) — eigener FastMCP-Server
  mit SQLite. `sessions`, `steps`, `known_failures` als Tools, damit **beide Wege**
  denselben Speicher teilen. Reine SQLite-Schicht ([`db.py`](store/db.py),
  FastMCP-frei → unit-testbar) + dünne MCP-Hülle ([`server.py`](store/server.py)).
- **Disziplin-Prompt:** [`prompts/diagnosis_system_prompt.md`](prompts/diagnosis_system_prompt.md)
  — die Diagnose-Regeln einmal geschrieben, von beiden Wegen genutzt.
- **L2 — Schematic / Weg B — Standalone:** geplant (M4/M5), noch nicht gebaut.

---

## L1 — Boardview-Tools (Ground Truth)

Boards werden **name-agnostisch** über Fuzzy-Resolve angesprochen: `A1708` oder
`820-00875` treffen dieselbe Datei, unabhängig von der genauen Schreibweise.
`board_id` = Dateiname ohne Endung.

| Tool                 | Frage, die es beantwortet |
|----------------------|---------------------------|
| `list_boards`        | Welche Boards liegen im Verzeichnis? |
| `select_board`       | Aktives Board für Folgeabfragen setzen |
| `board_info`         | Metadaten: Parts, Testpunkte, Pins, Netze |
| `get_net`            | Alle Pins/Parts/Testpunkte auf einem Netz |
| `get_part`           | Alle Pins eines Bauteils inkl. Netz + Koordinate |
| `connections_of`     | Was hängt an einem Bauteil? (je Netz die anderen Parts) |
| `shared_nets`        | Sind zwei Bauteile direkt verbunden? |
| `find_testpoints`    | Erreichbare Testpunkte/Nails auf einem Netz |
| `nearest_parts`      | Physisch nächstgelegene Bauteile (Mikroskop-Mapping) |
| `search`             | Fuzzy-Suche über Netz- und Bauteilnamen |

**Verifizierte Baseline (A1708 / 820-00875):** `parts=2838, testpoints=1354,
pins=11833, nets=2329`. Diese Werte sind das Regressions-Netz (siehe
[`tests/test_boardview.py`](tests/test_boardview.py)).

**Dateiformate:** `.json` (Intermediate-Schema, im Modul-Docstring) und obfuskiertes
OpenBoardView-`.brd` werden nativ geladen. `.fz`/andere Binärformate werden bewusst
**nicht** geraten — lieber kein Parser als ein halb-richtiger.

---

## L3 — State-Tools (Sitzungen & Wissen)

| Tool                    | Zweck |
|-------------------------|-------|
| `start_session`         | Neue Diagnose-Sitzung für ein Board (Status `open`) |
| `get_session`           | Sitzung inkl. aller Schritte holen |
| `list_sessions`         | Sitzungshistorie, optional nach `board_id` |
| `update_session`        | Status / Outcome setzen |
| `log_step`              | Messschritt protokollieren |
| `add_known_failure`     | Bekanntes Fehlerbild eintragen |
| `get_known_failure`     | Fehlerbild per ID |
| `list_known_failures`   | Fehlerbilder, optional nach `board_id` |
| `update_known_failure`  | Fehlerbild aktualisieren |
| `delete_known_failure`  | Fehlerbild löschen |

Datenmodell-Kniffe, die die Disziplin erzwingen:
- **`steps.evidence`** = `measured | injected | assumed` — trennt GEMESSEN von
  VERMUTET (0 Ω auf einer Cap-Bank-Rail ist meist ein Artefakt, kein echter Short).
- **`steps.net` / `steps.designator`** als eigene Spalten → jeder Schritt ist gegen
  L1 nachprüfbar.
- **`steps.confidence`** in % (0–100).
- **`known_failures.source`** = `distilled` (aus einer bestätigten Sitzung) | `manual`.
- Enums sind **doppelt** abgesichert: Python-Validierung **und** SQLite-CHECK-Constraints.

---

## Setup

Python ≥ 3.10. Windows nutzt `py` + `.venv\Scripts\`.

```bash
py -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# POSIX: .venv/bin/python -m pip install -r requirements.txt
```

Boards in `boards/` ablegen (`.brd` / `.json`). Die A1708-Boardview liegt bereits dort.

## Tests

```bash
bash scripts/test.sh                                  # L1-Selftest + pytest (inkl. M1-Baseline)
.venv/Scripts/python.exe -m pytest -q                 # nur pytest
.venv/Scripts/python.exe -m pytest tests/test_boardview.py -q   # eine Datei
.venv/Scripts/python.exe boardview_mcp.py --selftest  # L1-Selftest (Demo-Library, ohne Dateien)
```

Tests laufen **ohne** Live-Modell und **ohne** Live-Web: die MCP-Server werden über
FastMCPs In-Memory-Client angesprochen, L3 setzt seinen DB-Pfad via `configure(path)`.

## Server lokal starten (stdio)

```bash
# L1 — Boardview über das boards/-Verzeichnis, A1708 vorgewählt
.venv/Scripts/python.exe boardview_mcp.py boards --board A1708

# L1 als HTTP-Server (optional)
.venv/Scripts/python.exe boardview_mcp.py boards --http --port 8000

# L3 — State-Server; DB-Pfad via Env-Var (Default: store/state.sqlite)
BOARDREPAIR_DB=store/state.sqlite .venv/Scripts/python.exe store/server.py
```

---

## Weg A — Claude Desktop (einsatzbereit)

Claude Desktop **ist** hier der Orchestrator: es verbindet L1 + L3 als lokale
stdio-Connectors, die Diagnose-Disziplin steckt im Project-Prompt. Kein zusätzlicher
Code, keine API-Kosten.

1. Connector-Config aus [`desktop/claude_desktop_config.json`](desktop/claude_desktop_config.json)
   übernehmen (**absolute** venv-/Skript-/`boards`-/SQLite-Pfade — Begründung in der
   Setup-Doku) und Claude Desktop neu starten.
2. Ein **Project** anlegen und den gesamten Inhalt von
   [`prompts/diagnosis_system_prompt.md`](prompts/diagnosis_system_prompt.md) als
   **Project Instructions** einfügen.
3. Smoke-Check: *„Liste die Boards und gib `board_info` für A1708."* → erwartet die
   Baseline oben.

Vollständige Anleitung inkl. **manueller Bench-Checkliste**:
**[`desktop/SETUP.md`](desktop/SETUP.md)**.

---

## Projekt-Layout

```
boardview_mcp.py          # L1 — Boardview-MCP (Ground Truth)
boards/                   # .brd/.json (Zielplattform liegt hier)
store/                    # L3 — db.py (SQLite-Schicht) + server.py (MCP) + state.sqlite
prompts/                  # diagnosis_system_prompt.md (von beiden Wegen genutzt)
desktop/                  # Weg A: Connector-Config + SETUP.md
agent/  cli/              # Weg B — Standalone (M4, später)
schematics/               # PDFs (M5, später)
tests/                    # pytest: L1-Baseline, L1/L3-MCP-Integration, Store-Units
scripts/test.sh           # deterministischer Testlauf
CLAUDE.md PROGRESS.md VERIFICATION.md
```

## Status

| Milestone | Inhalt | Stand |
|-----------|--------|-------|
| M0 | Scaffold & grüne Pipeline | ✅ |
| M1 | L1 gehärtet + Ground-Truth-Baseline-Tests | ✅ |
| M2 | L3 State-MCP + Disziplin-Prompt | ✅ |
| M3 | Weg A (Claude Desktop) nutzbar | ✅ |
| M4 | Weg B — Standalone-App (Python-Orchestrator + CLI) | geplant |
| M5 | L2 — Schematic-Layer (PDF → VLM, „to-verify") | geplant |

Fortschritt im Detail: [PROGRESS.md](PROGRESS.md) · Definition-of-Done mit belegten
Commands: [VERIFICATION.md](VERIFICATION.md).

## Hinweise

- **Lokal & privat:** die Server laufen über stdio, nicht öffentlich exponiert.
- **State-DB** (`store/state.sqlite`) ist über `.gitignore` ausgeschlossen — keine
  Session-Daten im Repo.
- `boardview_mcp.py` ist getestetes Fundament — **erweitern via Tests**, nicht blind
  umschreiben; die M1-Baseline ist das Regressions-Netz.
```
