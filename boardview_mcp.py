#!/usr/bin/env python3
"""
boardview_mcp.py — Deterministischer MCP-Server über Boardview-Netzlisten
=========================================================================

Idee
----
Eine Boardview-Datei IST bereits die Netzliste eines Logicboards (Parts, Pins,
Netze, Koordinaten, Testpunkte). Sie ist strukturiert -> man braucht KEIN
Embedding/RAG, um sie abzufragen, sondern deterministische Tools.

Dieser Server stellt einem LLM exakte Fakten als MCP-Tools bereit:
  - "Welche Pins/Parts liegen auf Netz PPBUS_G3H?"        -> get_net
  - "Alle Pins von U7800 mit Netz + Koordinate?"          -> get_part
  - "Was hängt alles an U7800?"                           -> connections_of
  - "Sind C6555 und U7800 auf demselben Netz?"            -> shared_nets
  - "Welcher Testpunkt erreicht PP3V3_S5?"                -> find_testpoints
  - "Was liegt physisch neben C6555?"                     -> nearest_parts

Effekt: das Modell kann Netznamen NICHT mehr raten. Ground truth = die Datei,
nicht das Modellgedächtnis. Genau die Halluzinations-Klasse, die bei
Board-Repair teuer wird, fällt damit weg.

Stack
-----
- FastMCP 3.x          (pip install fastmcp)   https://gofastmcp.com
- Python >= 3.10
- Transport: stdio (lokal, z.B. Claude Desktop) ODER http (z.B. Pod auf OCP)

Start
-----
    pip install fastmcp
    # 1) Selbsttest ohne Dateien (Demo-Library mit 2 Boards):
    python boardview_mcp.py --selftest
    # 2) Lokal als stdio-Server über ein VERZEICHNIS von Boardviews:
    python boardview_mcp.py /pfad/zu/boardviews --board A1708
    # 3) Als HTTP-Server (z.B. im Cluster):
    python boardview_mcp.py /pfad/zu/boardviews --http --host 0.0.0.0 --port 8000

Mehrere Boards: einfach weitere .brd/.json ins Verzeichnis legen. Tools nehmen
ein optionales board= (fuzzy, z.B. 'A1708'); select_board(...) setzt das aktive.

Ingest
------
Sicherer Weg ist das JSON-Intermediate (Schema unten). Binär-/Encrypted-Formate
(.fz, proprietäre .brd) werden hier BEWUSST nicht geparst — siehe load_board().

    {
      "name": "820-00875-01",
      "parts": [{"name": "U7800", "side": "top", "package": "BGA"}],
      "pins":  [{"part": "U7800", "pin": "A1", "net": "PPBUS_G3H",
                 "x": 123.0, "y": 456.0, "side": "top", "testpoint": false}],
      "nets":  ["PPBUS_G3H"]          // optional, wird sonst aus pins abgeleitet
    }
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

log = logging.getLogger("boardview_mcp")

# --------------------------------------------------------------------------- #
# Datenmodell (format-agnostisch)                                             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Pin:
    """Ein einzelner Pin/Pad bzw. Testpunkt auf dem Board."""

    part: str
    pin: str
    net: str
    x: float
    y: float
    side: str  # "top" | "bottom" | "unknown"
    testpoint: bool = False


@dataclass
class Part:
    """Ein Bauteil mit zugehörigen Pins."""

    name: str
    side: str = "unknown"
    package: Optional[str] = None
    is_testpoint: bool = False
    pins: list[Pin] = field(default_factory=list)

    @property
    def centroid(self) -> tuple[float, float]:
        """Geometrischer Mittelpunkt aus den Pin-Koordinaten (für 'nearest')."""
        if not self.pins:
            return (0.0, 0.0)
        n = len(self.pins)
        return (sum(p.x for p in self.pins) / n, sum(p.y for p in self.pins) / n)


class Board:
    """Indizierte In-Memory-Repräsentation eines Boardviews."""

    def __init__(self, name: str, pins: list[Pin]):
        self.name = name
        self.pins = pins
        self.parts: dict[str, Part] = {}
        self._nets: dict[str, list[Pin]] = {}
        self._build_indices()

    def _build_indices(self) -> None:
        for p in self.pins:
            part = self.parts.get(p.part)
            if part is None:
                part = Part(name=p.part, side=p.side)
                self.parts[p.part] = part
            part.pins.append(p)
            if part.side == "unknown" and p.side != "unknown":
                part.side = p.side
            self._nets.setdefault(p.net, []).append(p)
        # Reine Nail-/Testpunkt-"Parts" markieren, damit sie aus Bauteil-
        # Statistik und Nachbarschaftssuche herausfallen.
        for part in self.parts.values():
            part.is_testpoint = bool(part.pins) and all(p.testpoint for p in part.pins)

    # ---- Lookups: case-insensitiv mit exaktem Vorrang ----

    @staticmethod
    def _resolve(table: dict, key: str) -> Optional[str]:
        if key in table:
            return key
        lowered = {k.lower(): k for k in table}
        return lowered.get(key.lower())

    def net_pins(self, net: str) -> list[Pin]:
        real = self._resolve(self._nets, net)
        if real is None:
            raise KeyError(f"Netz '{net}' nicht gefunden")
        return self._nets[real]

    def part(self, designator: str) -> Part:
        real = self._resolve(self.parts, designator)
        if real is None:
            raise KeyError(f"Bauteil '{designator}' nicht gefunden")
        return self.parts[real]

    def search(self, query: str, limit: int = 20) -> dict:
        q = query.lower()
        nets = sorted(n for n in self._nets if q in n.lower())[:limit]
        parts = sorted(p for p in self.parts if q in p.lower())[:limit]
        return {"nets": nets, "parts": parts}

    @property
    def net_count(self) -> int:
        return len(self._nets)


# --------------------------------------------------------------------------- #
# Report-Logik (rein, ohne MCP) — so testbar UND als Tool nutzbar             #
# --------------------------------------------------------------------------- #


def _pin_dict(p: Pin) -> dict:
    return {
        "part": p.part,
        "pin": p.pin,
        "net": p.net,
        "x": round(p.x, 2),
        "y": round(p.y, 2),
        "side": p.side,
        "testpoint": p.testpoint,
    }


def net_report(b: Board, net: str) -> dict:
    pins = b.net_pins(net)
    parts = sorted({p.part for p in pins})
    return {
        "net": pins[0].net,
        "part_count": len(parts),
        "parts": parts,
        "pin_count": len(pins),
        "pins": [_pin_dict(p) for p in pins],
        "testpoints": [_pin_dict(p) for p in pins if p.testpoint],
    }


def part_report(b: Board, designator: str) -> dict:
    pt = b.part(designator)
    pins = sorted(pt.pins, key=lambda x: x.pin)
    return {
        "designator": pt.name,
        "side": pt.side,
        "package": pt.package,
        "pin_count": len(pins),
        "pins": [_pin_dict(p) for p in pins],
    }


def connections_report(b: Board, designator: str) -> dict:
    """Je Netz des Bauteils die anderen Parts auf diesem Netz."""
    pt = b.part(designator)
    nets: dict[str, dict] = {}
    for p in pt.pins:
        others = sorted({q.part for q in b.net_pins(p.net)} - {pt.name})
        nets[p.net] = {"pin": p.pin, "connected_parts": others}
    return {"designator": pt.name, "nets": nets}


def shared_report(b: Board, part_a: str, part_b: str) -> dict:
    a = {p.net for p in b.part(part_a).pins}
    c = {p.net for p in b.part(part_b).pins}
    common = sorted(a & c)
    return {
        "part_a": b.part(part_a).name,
        "part_b": b.part(part_b).name,
        "shared_nets": common,
        "connected": bool(common),
    }


def testpoints_report(b: Board, net: str) -> dict:
    pins = b.net_pins(net)
    tps = [_pin_dict(p) for p in pins if p.testpoint]
    return {"net": pins[0].net, "testpoint_count": len(tps), "testpoints": tps}


def nearest_report(
    b: Board, designator: str, limit: int = 8, same_side_only: bool = True
) -> dict:
    """Physisch nächstgelegene Bauteile über Pin-Zentroide."""
    target = b.part(designator)
    tx, ty = target.centroid
    rows: list[tuple[float, str, str]] = []
    for name, pt in b.parts.items():
        if name == target.name or pt.is_testpoint:
            continue
        if same_side_only and pt.side != target.side:
            continue
        px, py = pt.centroid
        rows.append((math.hypot(px - tx, py - ty), name, pt.side))
    rows.sort(key=lambda r: r[0])
    return {
        "reference": target.name,
        "side": target.side,
        "neighbors": [
            {"part": n, "side": s, "distance": round(d, 2)}
            for d, n, s in rows[:limit]
        ],
    }


# --------------------------------------------------------------------------- #
# Loader                                                                      #
# --------------------------------------------------------------------------- #


def _board_from_json(data: dict) -> Board:
    name = str(data.get("name", "unnamed"))
    pins: list[Pin] = []
    for row in data.get("pins", []):
        pins.append(
            Pin(
                part=str(row["part"]),
                pin=str(row.get("pin", "?")),
                net=str(row.get("net", "UNCONNECTED")),
                x=float(row.get("x", 0.0)),
                y=float(row.get("y", 0.0)),
                side=str(row.get("side", "unknown")),
                testpoint=bool(row.get("testpoint", False)),
            )
        )
    if not pins:
        raise ValueError("JSON enthält keine 'pins' — nichts zu indizieren.")
    board = Board(name, pins)
    # Optionale Part-Metadaten (package/side) nachziehen.
    for row in data.get("parts", []):
        pt = board.parts.get(str(row.get("name", "")))
        if pt is None:
            continue
        if row.get("package"):
            pt.package = str(row["package"])
        if row.get("side"):
            pt.side = str(row["side"])
    return board


# Signatur des obfuskierten OpenBoardView-.brd (Test_Link/Landrex).
_ENCODED_BRD_HEADER = bytes([0x23, 0xE2, 0x63, 0x28])

# Sektions-Marker -> interner Block (1..6), gemäß OpenBoardView BRDFile.cpp.
_BRD_SECTIONS = {
    "str_length:": 1,
    "var_data:": 2,
    "Format:": 3,
    "format:": 3,
    "Parts:": 4,
    "Pins1:": 4,
    "Pins:": 5,
    "Pins2:": 5,
    "Nails:": 6,
}


def _decode_brd(raw: bytes) -> str:
    """
    Dekodiert das obfuskierte .brd, falls die Signatur passt.
    Transform je Byte (außer CR/LF/NUL): x = ~ROL2(c) = ~(((c>>6)&3)|(c<<2)).
    """
    if raw[:4] == _ENCODED_BRD_HEADER:
        dec = bytearray(len(raw))
        for i, b in enumerate(raw):
            dec[i] = (
                b if b in (0x0D, 0x0A, 0x00) else (~(((b >> 6) & 3) | (b << 2))) & 0xFF
            )
        raw = bytes(dec)
    return raw.decode("latin-1")


def _brd_side(ptype: int) -> str:
    """Bauteilseite aus dem Type/Layer-Feld (OpenBoardView-Konvention)."""
    if ptype == 1 or 4 <= ptype < 8:
        return "top"
    if ptype == 2 or ptype >= 8:
        return "bottom"
    return "unknown"


def _board_from_brd(raw: bytes, name: str = "820-brd") -> Board:
    """
    Parser für das OpenBoardView-.brd (inkl. obfuskierter Variante).
    Layout je Block:
      var_data: num_format num_parts num_pins num_nails ...
      Parts:    <name> <type> <end_of_pins>
      Pins:     <x> <y> <probe> <part_index(1-based)> <net>
      Nails:    <probe> <x> <y> <side(1=top)> <net>     -> Testpunkte
    Pin-Labels sind im Format nicht enthalten -> laufende Nummer je Part.
    """
    block = 0
    parts_meta: list[tuple[str, str]] = []  # (name, side)
    raw_pins: list[tuple[float, float, int, int, str]] = []
    raw_nails: list[tuple[float, float, int, str]] = []

    for line in _decode_brd(raw).replace("\r", "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line in _BRD_SECTIONS:
            block = _BRD_SECTIONS[line]
            continue
        tok = line.split()
        try:
            if block == 4:  # Parts
                parts_meta.append((tok[0], _brd_side(int(tok[1]))))
            elif block == 5:  # Pins
                net = tok[4] if len(tok) > 4 else "UNCONNECTED"
                raw_pins.append(
                    (float(tok[0]), float(tok[1]), int(tok[2]), int(tok[3]), net)
                )
            elif block == 6:  # Nails (Testpunkte)
                net = tok[4] if len(tok) > 4 else "UNCONNECTED"
                raw_nails.append((float(tok[1]), float(tok[2]), int(tok[3]), net))
        except (ValueError, IndexError):
            continue  # defekte Zeile tolerant überspringen

    if not raw_pins:
        raise ValueError("Keine Pins im .brd gefunden — Format unerwartet.")

    pins: list[Pin] = []
    per_part: dict[str, int] = {}
    for x, y, _probe, pidx, net in raw_pins:
        if 1 <= pidx <= len(parts_meta):
            pname, pside = parts_meta[pidx - 1]
        else:
            pname, pside = f"?{pidx}", "unknown"
        n = per_part.get(pname, 0) + 1
        per_part[pname] = n
        pins.append(Pin(pname, str(n), net, x, y, pside, testpoint=False))

    for i, (x, y, side, net) in enumerate(raw_nails):
        pins.append(
            Pin("TP%05d" % i, "1", net, x, y, "top" if side == 1 else "bottom", True)
        )

    board = Board(name, pins)
    for pname, pside in parts_meta:  # Seiten aus dem Parts-Block übernehmen
        if pname in board.parts and pside != "unknown":
            board.parts[pname].side = pside
    return board


def load_board(path: Path) -> Board:
    """
    Lädt ein Board. Aktuell nativ: JSON-Intermediate.

    Binär-/Encrypted-Boardviews (.fz, proprietäre .brd/.bdv) werden bewusst
    NICHT geraten — ein halb-richtiger Parser ist schlimmer als keiner.
    Zwei saubere Wege, das eigene Format reinzubekommen:
      1) Kleines Konvertierungsskript -> JSON-Schema (siehe Modul-Docstring).
      2) Parser aus OpenBoardView/src/openboardview/FileFormats portieren.
         (FZ ist XOR-"verschlüsselt"; der Key steckt in FZFile.cpp.)
    """
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _board_from_json(json.loads(path.read_text(encoding="utf-8")))
    if suffix == ".brd":
        return _board_from_brd(path.read_bytes(), name=path.stem)
    raise NotImplementedError(
        f"Format '{suffix}' wird (noch) nicht nativ geparst. "
        "Bitte nach JSON konvertieren (Schema im Modul-Docstring) oder den "
        "passenden OpenBoardView-Parser portieren."
    )


# --------------------------------------------------------------------------- #
# MCP-Server                                                                  #
# --------------------------------------------------------------------------- #

mcp = FastMCP("boardview-mcp")


class BoardLibrary:
    """
    Verwaltet ein Verzeichnis von Boardview-Dateien: scannt verfügbare Boards,
    lädt sie LAZY beim ersten Zugriff und cached sie. Start bleibt damit auch
    bei vielen Boards sofortig — neue Dateien einfach reinlegen genügt.

    board_id = Dateiname ohne Endung (z.B. 'MacBook_Pro_13_A1708_820-00875_').
    """

    SUFFIXES = {".brd", ".json"}

    def __init__(self, root: Optional[Path] = None):
        self.root = root
        self.active: Optional[str] = None
        self._files: dict[str, Path] = {}
        self._cache: dict[str, Board] = {}
        if root is not None:
            self.scan()

    def scan(self) -> None:
        """Verzeichnis (rekursiv) nach Boardview-Dateien absuchen."""
        self._files.clear()
        if self.root is None:
            return
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and p.suffix.lower() in self.SUFFIXES:
                self._files[p.stem] = p

    def register(self, board_id: str, board: Board) -> None:
        """In-Memory-Board registrieren (für Tests/Selbsttest ohne Dateien)."""
        self._files[board_id] = Path(f"<memory:{board_id}>")
        self._cache[board_id] = board

    def ids(self) -> list[str]:
        return sorted(self._files)

    def resolve(self, query: str) -> str:
        """
        board_id auflösen: exakt -> eindeutiger Teilstring (case-insensitiv).
        'A1708' oder '820-00875' trifft die Datei; mehrdeutig/leer -> Fehler.
        """
        if query in self._files:
            return query
        q = query.lower()
        hits = [bid for bid in self._files if q in bid.lower()]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise KeyError(f"Kein Board passt zu '{query}'. Verfügbar: {self.ids()}")
        raise KeyError(f"'{query}' ist mehrdeutig: {hits}")

    def get(self, board: Optional[str]) -> Board:
        """Board holen (explizit per board= oder aktives). Lazy-Parse + Cache."""
        bid = self.resolve(board) if board else self.active
        if bid is None:
            raise RuntimeError(
                "Kein Board gewählt — select_board(...) aufrufen oder board= "
                f"angeben. Verfügbar: {self.ids()}"
            )
        if bid not in self._cache:
            self._cache[bid] = load_board(self._files[bid])
        return self._cache[bid]


LIB: Optional[BoardLibrary] = None


def _lib() -> BoardLibrary:
    if LIB is None:
        raise RuntimeError("Keine Board-Library initialisiert.")
    return LIB


def _info_payload(b: Board) -> dict:
    real_parts = sum(1 for p in b.parts.values() if not p.is_testpoint)
    return {
        "name": b.name,
        "parts": real_parts,
        "testpoints": sum(1 for p in b.pins if p.testpoint),
        "pins": sum(1 for p in b.pins if not p.testpoint),
        "nets": b.net_count,
    }


@mcp.tool
def list_boards() -> dict:
    """Verfügbare Boardviews im Verzeichnis. board_id = Dateiname ohne Endung."""
    lib = _lib()
    return {"root": str(lib.root), "active": lib.active, "boards": lib.ids()}


@mcp.tool
def select_board(board: str) -> dict:
    """Aktives Board setzen (fuzzy: 'A1708' o. '820-00875'). Gilt für Folgeabfragen."""
    lib = _lib()
    lib.active = lib.resolve(board)
    return {"active": lib.active, **_info_payload(lib.get(None))}


@mcp.tool
def board_info(board: Optional[str] = None) -> dict:
    """Metadaten (Name, echte Parts, Testpunkte, Pins, Netze). board: opt., sonst aktiv."""
    return _info_payload(_lib().get(board))


@mcp.tool
def get_net(net: str, board: Optional[str] = None) -> dict:
    """Alle Pins/Parts/Testpunkte auf einem Netz. Beispiel: net='PPBUS_G3H'."""
    b = _lib().get(board)
    return {"board": b.name, **net_report(b, net)}


@mcp.tool
def get_part(designator: str, board: Optional[str] = None) -> dict:
    """Alle Pins eines Bauteils inkl. Netz + Koordinate. Beispiel: 'U7800'."""
    b = _lib().get(board)
    return {"board": b.name, **part_report(b, designator)}


@mcp.tool
def connections_of(designator: str, board: Optional[str] = None) -> dict:
    """Was hängt an einem Bauteil? Je Netz die anderen Parts auf dem Netz."""
    b = _lib().get(board)
    return {"board": b.name, **connections_report(b, designator)}


@mcp.tool
def shared_nets(part_a: str, part_b: str, board: Optional[str] = None) -> dict:
    """Gemeinsame Netze zweier Bauteile (Ist A direkt mit B verbunden?)."""
    b = _lib().get(board)
    return {"board": b.name, **shared_report(b, part_a, part_b)}


@mcp.tool
def find_testpoints(net: str, board: Optional[str] = None) -> dict:
    """Erreichbare Testpunkte/Nails auf einem Netz (Messpunkt-Suche)."""
    b = _lib().get(board)
    return {"board": b.name, **testpoints_report(b, net)}


@mcp.tool
def nearest_parts(
    designator: str,
    limit: int = 8,
    same_side_only: bool = True,
    board: Optional[str] = None,
) -> dict:
    """Physisch nächstgelegene Bauteile (Pin-Zentroide) — Mikroskop-Mapping."""
    b = _lib().get(board)
    return {"board": b.name, **nearest_report(b, designator, limit, same_side_only)}


@mcp.tool
def search(query: str, board: Optional[str] = None) -> dict:
    """Fuzzy-Suche über Netz- und Bauteilnamen (Teilstring, case-insensitiv)."""
    b = _lib().get(board)
    return {"board": b.name, **b.search(query)}


# --------------------------------------------------------------------------- #
# Demo / Entry-Point                                                          #
# --------------------------------------------------------------------------- #


def _demo_library() -> BoardLibrary:
    """Zwei synthetische Boards für den Selbsttest (ohne Dateien)."""
    a = Board(
        "DEMO-820-00875",
        [
            Pin("U7800", "A1", "PPBUS_G3H", 100.0, 100.0, "top"),
            Pin("U7800", "B2", "PP3V3_S5", 102.0, 100.0, "top"),
            Pin("U7800", "C3", "PMU_GND", 104.0, 100.0, "top"),
            Pin("C6555", "1", "PPBUS_G3H", 110.0, 98.0, "top"),
            Pin("C6555", "2", "PMU_GND", 110.0, 101.0, "top"),
            Pin("L5001", "1", "PPBUS_G3H", 90.0, 95.0, "top"),
            Pin("L5001", "2", "PP3V3_S5", 88.0, 95.0, "top"),
            Pin("TP_VBUS", "1", "PPBUS_G3H", 200.0, 50.0, "top", testpoint=True),
        ],
    )
    b = Board(
        "DEMO-820-01700",
        [
            Pin("U5000", "1", "PPBUS_G3H", 10.0, 10.0, "top"),
            Pin("U5000", "2", "PP1V8", 12.0, 10.0, "top"),
        ],
    )
    lib = BoardLibrary()
    lib.register("DEMO-820-00875", a)
    lib.register("DEMO-820-01700", b)
    lib.active = "DEMO-820-00875"
    return lib


def main() -> None:
    global LIB
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    ap = argparse.ArgumentParser(description="Boardview MCP-Server (Multi-Board)")
    ap.add_argument(
        "root", nargs="?", help="Verzeichnis mit Boardview-Dateien (.brd/.json)"
    )
    ap.add_argument(
        "--board", help="Beim Start aktives Board vorwählen (fuzzy, z.B. 'A1708')"
    )
    ap.add_argument("--selftest", action="store_true", help="Demo-Library + Queries")
    ap.add_argument("--http", action="store_true", help="HTTP-Server statt stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    if args.selftest:
        LIB = _demo_library()
        log.info("Demo-Library: %s", list_boards())
        for label, payload in [
            ("list_boards()", list_boards()),
            ("board_info('820-01700')  [fuzzy]", board_info("820-01700")),
            ("get_net('PPBUS_G3H')  [aktiv: A1708-Demo]", get_net("PPBUS_G3H")),
            ("shared_nets('U7800','C6555')", shared_nets("U7800", "C6555")),
        ]:
            print(f"\n# {label}")
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    if not args.root:
        ap.error("Entweder --selftest oder ein Verzeichnis angeben.")

    LIB = BoardLibrary(Path(args.root))
    if not LIB.ids():
        ap.error(f"Keine .brd/.json in {args.root} gefunden.")
    if args.board:
        LIB.active = LIB.resolve(args.board)
    log.info(
        "Library: %d Boards %s, aktiv=%s", len(LIB.ids()), LIB.ids(), LIB.active
    )

    if args.http:
        # Ältere FastMCP-Versionen: transport="streamable-http".
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()  # stdio


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError, NotImplementedError, KeyError) as exc:
        log.error("%s", exc)
        sys.exit(1)
