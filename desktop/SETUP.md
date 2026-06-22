# Weg A — Claude Desktop als Orchestrator (Setup)

Claude Desktop **ist** hier der Orchestrator: es verbindet L1 (Boardview) und L3
(State) als lokale **stdio**-MCP-Server (Connectors), und die Diagnose-Disziplin
steckt im **Project-Prompt**. Kein eigener Python-Orchestrator, keine API-Kosten.

## 1. Voraussetzungen
- venv eingerichtet und Deps installiert (siehe Repo-`README.md`):
  ```bash
  py -m venv .venv
  .venv/Scripts/python.exe -m pip install -r requirements.txt
  ```
- `bash scripts/test.sh` ist grün.

## 2. Connector-Config eintragen
Vorlage: [`desktop/claude_desktop_config.json`](claude_desktop_config.json).
Inhalt in die Claude-Desktop-Konfig übernehmen (Settings → Developer → Edit Config,
bzw. Datei `claude_desktop_config.json` im Claude-Konfigverzeichnis) und Claude
Desktop neu starten.

### WARUM absolute Pfade + venv-Python (nicht bloß `python`)
> Claude Desktop startet die MCP-Server als **eigene Subprozesse** — NICHT aus
> deiner aktivierten Shell und i. d. R. mit einem anderen Arbeitsverzeichnis und
> `PATH`. Ein bloßes `"python"` würde daher (a) evtl. einen falschen/fehlenden
> Interpreter treffen und (b) `fastmcp` nicht finden, weil es nur in der venv
> installiert ist. Ebenso sind relative Pfade (`boardview_mcp.py`, `boards`,
> `state.sqlite`) gegen ein unbekanntes CWD nutzlos. Deshalb:
>
> - `command` = **absoluter** Pfad auf den **venv**-Interpreter
>   `…\.venv\Scripts\python.exe` (garantiert `fastmcp` + gepinnte Deps),
> - `args` = **absolute** Pfade auf das Server-Skript und das `boards/`-Verzeichnis,
> - `env.BOARDREPAIR_DB` = **absoluter** Pfad auf die SQLite-Datei (sonst landet der
>   State je nach CWD an wechselnden Orten).
>
> Wenn du das Repo verschiebst/klonst: alle vier Pfade in der JSON anpassen
> (Repo-Root, Skripte, `boards/`, `state.sqlite`).

Die beiden Server in der Vorlage:
- **`boardview-mcp`** (L1): `boardview_mcp.py <boards-dir> --board A1708` — stdio.
- **`boardrepair-state`** (L3): `store/server.py`, DB-Pfad via `BOARDREPAIR_DB`.

## 3. Project mit dem Disziplin-Prompt anlegen
1. In Claude Desktop ein **Project** erstellen (z. B. „Board-Repair A1708").
2. Den **gesamten** Inhalt von
   [`prompts/diagnosis_system_prompt.md`](../prompts/diagnosis_system_prompt.md)
   als **Project Instructions** einfügen. Dieser Prompt trägt §2 (Reliability-
   Gradient) und §4 (Diagnose-Disziplin) und den operativen Tool-Ablauf.
3. Sicherstellen, dass beide Connectors im Project aktiv sind.

## 4. Smoke-Check in Claude Desktop
Nach Neustart sollten in einem neuen Chat die Tools beider Server sichtbar sein.
Frage z. B.: *„Liste die Boards und gib board_info für A1708."* → erwartet
`parts=2838, testpoints=1354, pins=11833, nets=2329`.

## 5. Manueller Bench-Durchlauf (Checkliste)
Ein grüner automatischer Test beweist nur die **Mechanik**, nicht dass das Modell
die Disziplin an echter Hardware einhält (CLAUDE.md §7). Diese Schleife wird an der
Bench mit echtem Hirn validiert:

- [ ] **Start:** Symptom nennen → Assistent ruft `select_board` →
      `list_known_failures(A1708)` → `start_session(...)` und nennt die `session_id`.
- [ ] **Strompfad zuerst:** Assistent beginnt an der Quelle (z. B. `PPBUS_G3H`),
      nicht mit zufälligen Bauteil-Hypothesen.
- [ ] **Eine Messung/Runde:** genau EINE Messanweisung mit Punkt aus einem
      L1-Tool (Designator/Pin/Netz + Soll), dann **Warten** auf deinen Messwert.
- [ ] **Grounding:** jeder genannte Netzname/Designator stammt nachweislich aus
      einem L1-Tool-Call (kein geratener Name).
- [ ] **Logging:** nach deiner Antwort `log_step` mit `evidence`
      (measured/injected/assumed), `confidence` %, `net`, `designator`, Soll/Ist,
      Befund, Hypothese.
- [ ] **Verifikation:** verdächtige Messwerte (z. B. 0 Ω) werden hinterfragt, nicht
      blind geglaubt; vor „Bauteil tauschen" zerstörungsfreie Bestätigung genannt.
- [ ] **Abschluss:** `update_session(status=resolved|abandoned, outcome=…)`; bei
      bestätigter Ursache optional `add_known_failure(... source='distilled',
      source_session_id=<session_id>)`.
- [ ] **Oszilloskop:** falls eines nötig wäre, sagt der Assistent das ausdrücklich.
