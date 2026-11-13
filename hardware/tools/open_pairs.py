"""Lista as ligações abertas (sem o GND) pelas ilhas de conectividade do pcbnew e grava em JSON
para o route_rest.py. (O kicad-cli pcb drc deixou de gravar o relatório nesta placa.)

Cada ponta leva as camadas onde tem cobre (0 = F.Cu, 1 = B.Cu), para o roteador não confundir
um pad de um lado com uma trilha que passa por baixo dele no outro.

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/open_pairs.py <saida.json>
"""
import collections
import json
import math
import sys
from pathlib import Path

import pcbnew

b = pcbnew.LoadBoard(str(Path(__file__).resolve().parent.parent / "teclado.kicad_pcb"))
to = pcbnew.ToMM
b.BuildConnectivity()
conn = b.GetConnectivity()
TYPES = [pcbnew.PCB_PAD_T, pcbnew.PCB_TRACE_T, pcbnew.PCB_VIA_T, pcbnew.PCB_ARC_T]

items = {}     # uuid -> (objeto, rede, pontos, descrição, camadas)
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetNetCode() and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH:
            q = p.GetPosition()
            lays = [l for l, lay in enumerate((pcbnew.F_Cu, pcbnew.B_Cu)) if p.IsOnLayer(lay)]
            items[p.m_Uuid.AsString()] = (p, p.GetNetname(), [(to(q.x), to(q.y))], f"{f.GetReference()}.{p.GetNumber()}", lays)
for t in b.GetTracks():
    if not t.GetNetCode():
        continue
    if isinstance(t, pcbnew.PCB_VIA):
        q = t.GetPosition()
        items[t.m_Uuid.AsString()] = (t, t.GetNetname(), [(to(q.x), to(q.y))], "via", [0, 1])
    else:
        s, e = t.GetStart(), t.GetEnd()
        items[t.m_Uuid.AsString()] = (t, t.GetNetname(), [(to(s.x), to(s.y)), (to(e.x), to(e.y))],
                                      "trk " + b.GetLayerName(t.GetLayer()), [0 if t.GetLayer() == pcbnew.F_Cu else 1])

par = {k: k for k in items}


def find(k):
    while par[k] != k:
        par[k] = par[par[k]]
        k = par[k]
    return k


for k, (o, net, pts, d, lays) in items.items():
    if net == "GND":
        continue
    try:
        nb = conn.GetConnectedItems(o, 0)
    except Exception:
        nb = conn.GetConnectedItems(o, TYPES)
    for n in nb:
        kn = n.m_Uuid.AsString()
        if kn in par:
            par[find(k)] = find(kn)

nets = collections.defaultdict(lambda: collections.defaultdict(list))
for k, (o, net, pts, d, lays) in items.items():
    if net != "GND":
        nets[net][find(k)].append(k)

out = {"violations": [], "unconnected_items": []}
for net, cl in sorted(nets.items()):
    if len(cl) < 2:
        continue
    cls = sorted(cl.values(), key=len, reverse=True)
    main = [(p, items[k][3], items[k][4]) for k in cls[0] for p in items[k][2]]
    for c in cls[1:]:
        L, p, dp, lp, q, dq, lq = min(((math.dist(p, q), p, items[k][3], items[k][4], q, dq, lq)
                                       for k in c for p in items[k][2] for q, dq, lq in main), key=lambda z: z[0])
        print(f"{net:20s} {L:6.1f}  ilha de {len(c):3d} itens  {dp:10s} ({p[0]:.2f},{p[1]:.2f}) -> {dq:10s} ({q[0]:.2f},{q[1]:.2f})")
        out["unconnected_items"].append({"items": [
            {"description": f"{dp} [{net}]", "pos": {"x": p[0], "y": p[1]}, "layers": lp},
            {"description": f"{dq} [{net}]", "pos": {"x": q[0], "y": q[1]}, "layers": lq}]})
        main += [(pp, items[k][3], items[k][4]) for k in c for pp in items[k][2]]
total = conn.GetUnconnectedCount(True)
print(f"abertas (sem GND): {len(out['unconnected_items'])} | GND: {total - len(out['unconnected_items'])} | total KiCad: {total}")
json.dump(out, open(sys.argv[1], "w", encoding="utf-8"))
