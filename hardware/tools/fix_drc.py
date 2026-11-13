"""Remove as trilhas e vias apontadas pelo DRC em violações de isolamento, para serem roteadas de novo.

Lê o JSON do kicad-cli (pcb drc --format json) e remove o item de trilha/via de cada violação dos tipos
clearance, hole_clearance e copper_edge_clearance. Pads e zonas não são tocados.
Depois: clean_tracks.py (tira as pontas soltas), open_pairs.py e route_rest.py.

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/fix_drc.py <drc.json> [--dry]
"""
import json
import math
import re
import sys
from pathlib import Path

import pcbnew

PCB = str(Path(__file__).resolve().parent.parent / "teclado.kicad_pcb")
TYPES = {"clearance", "hole_clearance", "copper_edge_clearance"}
to = pcbnew.ToMM
b = pcbnew.LoadBoard(PCB)
tracks = list(b.GetTracks())

want = []
for v in json.load(open(sys.argv[1], encoding="utf-8"))["violations"]:
    if v["type"] not in TYPES:
        continue
    for i in v["items"]:
        m = re.match(r"(Trilha|Track|Via) \[(.*?)\]", i["description"])
        if m:
            want.append((m.group(1) == "Via", m.group(2), i["pos"]["x"], i["pos"]["y"], i["description"]))

gone = {}
for via, net, x, y, desc in want:
    for t in tracks:
        if t.GetNetname() != net or isinstance(t, pcbnew.PCB_VIA) != via:
            continue
        pts = [t.GetPosition()] if via else [t.GetStart(), t.GetEnd()]
        if any(math.hypot(to(p.x) - x, to(p.y) - y) < 0.01 for p in pts):
            gone[id(t)] = (t, desc)
for t, desc in gone.values():
    print("remove:", desc)
print(f"{len(gone)} itens")
if "--dry" not in sys.argv and gone:
    for t, _ in gone.values():
        b.Remove(t)
    b.Save(PCB)
    print("placa salva")
