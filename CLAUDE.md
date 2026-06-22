# Projekt-Brief & autonome Build-Spec — Board-Repair Diagnose-Assistent

> **An Claude Code:** Lies dieses Dokument VOLLSTÄNDIG, bevor du irgendetwas tust.
> Es ist verbindlich. Du entwickelst, testest und verifizierst dieses Projekt
> autonom nach dem Build-Protokoll (§5–§8). Dieses Dokument ersetzt frühere
> CLAUDE.md-Entwürfe.

---

## 1. Mission
Ein **lokaler, agentischer** Diagnose-Assistent für Board-Level-Repair an Apple-
Logicboards. Er führt eine **langsame, schrittweise, fundierte** Fehlersuche und
verbindet vier Quellen: Boardview-Netzliste (lokal), Schematic-PDF (lokal),
Web-Recherche, eigene Repair-Notes (lokal). Kein One-Shot-"Diagnose".
Erste Zielplattform: **MacBook Pro 13" A1708 / 820-00875**.

## 2. Reliability-Gradient — NICHT VERHANDELBAR
Jede Aussage des fertigen Assistenten hat eine Vertrauensstufe, die im Output
sichtbar bleiben muss. Der gesamte Code muss das erzwingen:

| Quelle              | Vertrauen           | Regel im Code |
|---------------------|---------------------|---------------|
| Boardview-MCP-Tool  | belegt              | EINZIGE Quelle für Netz-/Pin-/Koordinaten-Fakten |
| Schematic via VLM   | Vermutung-to-verify | Werte/Topologie; Netz-Identität gegen MCP prüfen |
| Web (Datenblatt)    | Kontext             | als Hinweis kennzeichnen, Quelle nennen |
| LLM-Gedächtnis      | NICHT trauen        | nie für Connectivity/Netznamen |

→ **Netznamen werden NIE geraten.** Jeder Designator/Netzname, den der Assistent
in einer Messanweisung nennt, muss vorher über das Boardview-Tool existieren.

## 3. Architektur (Zielform)
- **L1 — Boardview (Ground Truth, deterministisch). EXISTIERT:** `boardview_mcp.py`
  (FastMCP-Server, lädt obfuskiertes `.brd` nativ, In-Memory-Graph, Multi-Board
  via Library). Tools: `list_boards, select_board, board_info, get_net, get_part,
  connections_of, shared_nets, find_testpoints, nearest_parts, search`.
  **Keine DB** — die Datei ist die Wahrheit.
- **L3 — Wissen + Sitzungszustand. Eigener MCP-Server (SQLite):** `sessions`,
  `steps` (Messpunkt, Soll, Ist, Befund, Hypothese, Konfidenz), `known_failures`
  (board-spezifisch, mit `board_id`) — als MCP-Tools, damit ihn **beide Deployments
  teilen**. SQLite reicht — kein Postgres.
- **L2 — Schematic (Werte/Reglertopologie/Sequencing). SPÄTER (M5, optional):**
  PDF-Seiten rendern → ColQwen-Retrieval → VLM liest die Seite. Output IMMER
  "to-verify", Netz-Identität gegen L1 prüfen.
- **L4 — Orchestrierung. ZWEI austauschbare Wege über DENSELBEN Kern (L1+L3):**
  - **Weg A — Claude Desktop (zuerst, einfach):** Claude Desktop *ist* der
    Orchestrator; es verbindet L1+L3 als Connectors, die Diagnose-Disziplin steckt
    im Project-Prompt. Kein Python-Orchestrator/CLI nötig, keine API-Kosten (Abo).
  - **Weg B — Standalone-App (später):** Python-Orchestrator + `LLMClient`
    (lokales Qwen ODER API) + CLI, der **denselben** L1+L3 und **dasselbe**
    Disziplin-Prompt nutzt.
  - Die Diagnose-Disziplin (§4) wird **einmal** als Prompt-Datei geschrieben
    (`prompts/diagnosis_system_prompt.md`) und von beiden Wegen geladen.

## 4. Diagnose-Disziplin (der fertige Assistent muss das zur Laufzeit erzwingen)
1. **Strompfad zuerst**, Quelle → Verbraucher; erste Station mit falschem Wert =
   Fehlerort. Keine Bauteil-Hypothesen abklappern.
2. **Pro Schritt EINE Messanweisung** mit exaktem Messpunkt (Designator/Pin/Netz
   via L1-Tool) + erwartetem Soll-Wert, dann auf das Ergebnis des Users WARTEN.
3. **Messwerte verifizieren, nicht glauben** (0 Ω auf Cap-Bank-Rail = meist
   Artefakt; echter Short nur via Voltage-Injection).
4. **Symptom vs. Ursache trennen**: erste fehlende Stufe der Sequenz = Wurzel.
5. **Konfidenz in %** angeben und begründen, wenn nach Sicherheit gefragt.
6. **Vor jedem "Bauteil tauschen"** die zerstörungsfreie Bestätigung nennen.
7. **Kein Oszilloskop** vorhanden → sagen, wenn eins nötig wäre.

## 5. Wie du das baust (autonomes Build-Protokoll)
- **Du hast eine Shell und darfst Code ausführen. NUTZE das.** Jede Erfolgsmeldung
  muss durch echten Command-Output belegt sein. Nichts wird als fertig markiert,
  ohne die Akzeptanzchecks tatsächlich laufen zu lassen und das Ergebnis zu zeigen.
- **Arbeite in Milestones (§6) der Reihe nach.** Nach jedem Milestone: volle
  Test-Suite + Akzeptanzchecks laufen lassen. Bei Rot: fixen, BEVOR es weitergeht.
  Niemals einen Milestone überspringen oder vorziehen. **Stopp nach jedem für OK.**
- **Test-getrieben:** Tests gehören zu jedem Modul. Framework: `pytest`.
- **Umgebung deterministisch:** venv, gepinnte Deps in `requirements.txt`, ein
  `scripts/test.sh`, das Lint + Tests + Selftest fährt.
- **Fortschritt dokumentieren:** `PROGRESS.md` (Checkliste, laufend) und am Ende
  `VERIFICATION.md` (jeder Definition-of-Done-Punkt mit Command + Ergebnis).
- **Versionierung:** ein Commit pro abgeschlossenem, grünem Milestone.
- **`boardview_mcp.py` ist getestetes Fundament** — erweitern via Tests, NICHT
  blind umschreiben. Die Baseline-Assertions (§6, M1) sind dein Regressions-Netz.

## 6. Milestones & Akzeptanzkriterien
Strategie: zuerst der **gemeinsame Kern** (L1 + L3 + Disziplin-Prompt) → damit ist
**Weg A (Claude Desktop) sofort nutzbar**. **Weg B (Standalone-App)** kommt später
additiv und fasst den Kern nicht an. Am Ende sind beide implementiert + austauschbar.

**M0 — Scaffold & grüne Pipeline.**
Repo-Struktur (§10), venv, `requirements.txt`, `scripts/test.sh`, `pytest`-Setup.
*Akzeptanz:* `pytest` läuft; `python boardview_mcp.py --selftest` läuft fehlerfrei;
der echte `.brd` lädt.

**M1 — Boardview-MCP (L1) härten + Test-Suite gegen das echte Board.**
`tests/test_boardview.py` mit Ground-Truth-Assertions gegen
`boards/MacBook_Pro_13_A1708_820-00875_.brd`. **Verifizierte Baseline (exakt):**
- `board_info`: parts=2838, testpoints=1354, pins=11833, nets=2329
- `get_part("U7800")`: side=top, pin_count=168
- `get_net("PPBUS_G3H")`: part_count=35, pin_count=38, testpoints=2
- `shared_nets("U7800","L5001")`: connected=False
- Fuzzy: `resolve("A1708")` und `resolve("820-00875")` → dieselbe Datei
- Negativ: `get_net(board="A9999")` → KeyError mit Liste verfügbarer Boards
*Akzeptanz:* alle grün. **Bei Abweichung STOPP + Ist-Werte zeigen, NICHT den Parser
anpassen** (Werte stammen aus genau dieser Datei; bei anderem File Baseline neu erzeugen).

**M2 — L3 State-MCP-Server + Disziplin-Prompt (gemeinsamer Kern).**
`store/` als eigenständiger FastMCP-Server: Tools für `sessions`/`steps`
(start_session, log_step, get_session) und `known_failures` (CRUD + Abfrage nach
`board_id`), SQLite-Backend. Dazu `prompts/diagnosis_system_prompt.md` mit der
Disziplin aus §4 — **einmal** geschrieben, von beiden Wegen genutzt.
*Akzeptanz:* Unit-Tests aller L3-Tools (CRUD, board_id-Filter, Persistenz über
Neustart); L3-Server startet und beantwortet einen Tool-Call nachweislich.

**M3 — Weg A nutzbar machen (Claude Desktop).**
`README.md` + `desktop/` mit (a) Connector-Konfig-Beispiel für L1+L3 als lokale
stdio-Server, (b) Anleitung, das Project mit `diagnosis_system_prompt.md` als
Instructions anzulegen. Kein zusätzlicher Code — Claude Desktop ist der Orchestrator.
*Akzeptanz:* beide MCP-Server (L1, L3) starten und beantworten je einen Tool-Call;
Setup-Doku vollständig; ein **manueller** Bench-Durchlauf ist als Checkliste
beschrieben (nicht automatisierbar — §7). **Hier ist der Desktop-Weg fertig.**

**M4 — Weg B: Standalone-App (LATER, optional, fasst den Kern nicht an).**
`agent/` (orchestrator.py, llm_client.py, guards.py) + `cli/`, nutzt **denselben**
L1+L3 und **dasselbe** Prompt.
- `LLMClient`-Interface; Impls: real (Anthropic-API ODER lokaler OpenAI-komp. vLLM,
  hinter Config, Default unkonfiguriert) + `ScriptedLLM` für Tests.
- **Grounding by construction:** Messanweisungen werden aus dem L1-Tool-Output
  **getemplatet** (Netzname + Koordinate wörtlich aus `find_testpoints`/`get_net`),
  damit Fakten NICHT aus dem Modell stammen. `validate_instruction` ist nur das
  **Sicherheitsnetz**, NICHT der Hauptmechanismus (keine Regex-getriebene
  Faktengewinnung).
- "Eine Messung, dann warten"-Gating; L3-Logging pro Schritt; Konfidenz in %.
*Akzeptanz (mit ScriptedLLM, Web gemockt):* genau eine Messanweisung pro Runde;
jeder Schritt nach L3 geschrieben; kein Netzname im Output ohne L1-Deckung;
E2E-Trockenlauf der CLI grün. **Danach kann der User zwischen Weg A und B wählen.**

**M5 — Schematic-Layer (L2). LATER, optional, NICHT vor M0–M4 grün.**
PDF-Render → ColQwen-Index → VLM-Read, hinter Feature-Flag, Output strikt
"to-verify", Netz gegen L1 geprüft. Blockiert nichts Vorheriges.

## 7. Test-Strategie
- **Unit:** Parser/Decode (`.brd`), Graph-Aufbau, jedes L1-Tool, `validate_instruction`,
  L3-Tools/DB.
- **Integration:** MCP-Server (L1, L3) über In-Memory-Client (FastMCP) oder
  Subprozess ansprechen und Tool-Antworten prüfen.
- **End-to-End (Trockenlauf, nur Weg B):** volle Diagnose-Schleife mit `ScriptedLLM`.
  **Web-Search in Tests mocken — keine Live-Calls, kein Live-Modell.**
- **Regression:** die M1-Baseline-Assertions laufen in jedem Testlauf mit.
- **Grenze:** ein grüner E2E-Trockenlauf beweist die *Mechanik* (Gating, Logging,
  Guard, DB), NICHT dass das echte Modell die Disziplin einhält oder den Strompfad
  korrekt verfolgt. Das wird **manuell an der Bench** mit echtem Hirn validiert.

## 8. Definition of Done (in VERIFICATION.md mit Commands belegen)
**Kern + Weg A (nach M3 — Desktop-Weg fertig & einsetzbar):**
- `pytest` grün; `scripts/test.sh` grün.
- `boardview_mcp.py --selftest` grün; M1-Baseline-Assertions grün.
- L1- UND L3-MCP-Server starten und beantworten je einen Tool-Call nachweislich.
- `prompts/diagnosis_system_prompt.md` + Desktop-Setup-Doku vorhanden.
- `README.md`, `PROGRESS.md`, `VERIFICATION.md` vorhanden; keine TODO-/Stub-Stellen.

**Zusätzlich Weg B (nach M4 — Standalone fertig):**
- CLI-E2E-Trockenlauf (ScriptedLLM, Web gemockt) grün.
- Kein Pfad gibt Netz-/Pin-Fakten aus, die nicht über L1 kamen (Fakten getemplatet).

## 9. Do NOT
- Tests faken, überspringen oder "done" ohne ausgeführten Beleg melden.
- `boardview_mcp.py` blind umschreiben (erweitern via Tests).
- Dem LLM Netz-/Pin-Fakten glauben; Netznamen raten lassen.
- Text-Chunk-RAG über das Schematic-PDF (zerstört Topologie).
- Weg B (M4) oder Schematic (M5) anfangen, bevor der Kern (M0–M3) grün ist.
- Over-Engineering: kein Postgres/Redis/k8s, kein Cloud-Deployment.
- Den Server öffentlich exponieren (lokal, stdio).
- Live-Modell oder Live-Web in Tests aufrufen (ScriptedLLM + Mocks).

## 10. Tech-Stack & Repo-Layout
Python ≥ 3.10 · FastMCP 3.x · pytest · SQLite (stdlib) · (M5: colpali-engine +
Qdrant/FAISS, vLLM/Qwen optional). Transport stdio.
```
.
├── CLAUDE.md  README.md  PROGRESS.md  VERIFICATION.md
├── requirements.txt   scripts/test.sh
├── boardview_mcp.py          # L1 (vorhanden, Fundament)
├── boards/                   # .brd-Dateien (vom User)
├── store/                    # L3: eigener MCP-Server + SQLite (M2)
├── prompts/                  # diagnosis_system_prompt.md (M2, von beiden genutzt)
├── desktop/                  # Weg A: Connector-Config + Setup-Doku (M3)
├── agent/  cli/              # Weg B: Standalone (M4, später)
├── schematics/               # PDFs (M5, später)
└── tests/
```

## 11. Vorhandene Assets
- `boardview_mcp.py` — L1, fertig & an echtem Board getestet (Fundament).
- `boards/MacBook_Pro_13_A1708_820-00875_.brd` — Zielplattform (vom User gelegt).
- Schematic-PDF (820-00875) — für M5, kommt später.
