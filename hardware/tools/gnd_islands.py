"""Acha os pedaços de GND que não estão ligados ao GND principal e liga os que dá com uma via.

Nós do grafo: cada ilha de cobre dos planos GND (F.Cu e B.Cu), cada pad, trilha e via de GND.
Uma ilha solta que passa por cima/baixo de cobre do grupo principal na outra camada recebe uma via
de costura nesse ponto. O que não dá para ligar com via (pad sem plano em volta) sai num JSON de
pares para o route_rest.py --gnd.

Rode depois de post_route.py --no-import (planos preenchidos). Depois rode post_route.py --no-import
de novo para o plano abraçar as vias novas.

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/gnd_islands.py [pares.json] [--dry]
"""
import collections
import json
import math
import sys
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parent.parent
PCB = str(HW / "teclado.kicad_pcb")
mm, to = pcbnew.FromMM, pcbnew.ToMM
VIA_D, VIA_DRILL = 0.6, 0.3
R_TEST = VIA_D / 2 + 0.1
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
TYPES = [pcbnew.PCB_PAD_T, pcbnew.PCB_TRACE_T, pcbnew.PCB_VIA_T, pcbnew.PCB_ARC_T, pcbnew.PCB_ZONE_T]

b = pcbnew.LoadBoard(PCB)
b.BuildConnectivity()
conn = b.GetConnectivity()
gnd = b.FindNet("GND")
zone = {}
for z in b.Zones():
    if z.GetNetname() == "GND" and not z.GetIsRuleArea():
        zone[0 if z.GetLayer() == pcbnew.F_Cu else 1] = z
poly = {l: zone[l].GetFilledPolysList(LAYERS[l]) for l in (0, 1)}
boxes = {l: [poly[l].Outline(i).BBox() for i in range(poly[l].OutlineCount())] for l in (0, 1)}


def island(l, x, y):
    """Índice da ilha do plano da camada l que contém o ponto (mm), ou None."""
    v = pcbnew.VECTOR2I(mm(x), mm(y))
    for i, q in enumerate(boxes[l]):
        if q.Contains(v) and poly[l].Contains(v, i):
            return i
    return None


par = {}


def find(k):
    par.setdefault(k, k)
    while par[k] != k:
        par[k] = par[par[k]]
        k = par[k]
    return k


def union(a, c):
    par[find(a)] = find(c)


def connected(o):
    try:
        return conn.GetConnectedItems(o, 0)
    except Exception:
        return conn.GetConnectedItems(o, TYPES)


info = {}      # nó -> (descrição, (x, y), camadas)
pads = []
for f in b.GetFootprints():
    for p in f.Pads():
        q = p.GetBoundingBox()
        pads.append((to(q.GetLeft()) - 0.3 - VIA_D / 2, to(q.GetTop()) - 0.3 - VIA_D / 2,
                     to(q.GetRight()) + 0.3 + VIA_D / 2, to(q.GetBottom()) + 0.3 + VIA_D / 2))
        if p.GetNetname() != "GND":
            continue
        k = p.m_Uuid.AsString()
        c = p.GetPosition()
        lays = [l for l in (0, 1) if p.IsOnLayer(LAYERS[l])]
        info[k] = (f"{f.GetReference()}.{p.GetNumber()}", (to(c.x), to(c.y)), lays)
        find(k)
        nb = connected(p)
        for n in nb:
            if not isinstance(n, pcbnew.ZONE):
                union(k, n.m_Uuid.AsString())
        if any(isinstance(n, pcbnew.ZONE) for n in nb):
            # ilhas que os raios do alívio térmico alcançam: pontos em volta do pad
            x0, y0, x1, y1 = to(q.GetLeft()) - 0.45, to(q.GetTop()) - 0.45, to(q.GetRight()) + 0.45, to(q.GetBottom()) + 0.45
            xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
            for l in lays:
                for x, y in ((x0, ym), (x1, ym), (xm, y0), (xm, y1)):
                    i = island(l, x, y)
                    if i is not None:
                        union(k, ("isl", l, i))
for t in b.GetTracks():
    if t.GetNetname() != "GND":
        continue
    k = t.m_Uuid.AsString()
    if isinstance(t, pcbnew.PCB_VIA):
        c = t.GetPosition()
        info[k] = ("via", (to(c.x), to(c.y)), [0, 1])
        pts, lays = [(to(c.x), to(c.y))], (0, 1)
    else:
        s, e = t.GetStart(), t.GetEnd()
        l = 0 if t.GetLayer() == pcbnew.F_Cu else 1
        info[k] = ("trk", (to(s.x), to(s.y)), [l])
        pts, lays = [(to(s.x), to(s.y)), (to(e.x), to(e.y)), ((to(s.x) + to(e.x)) / 2, (to(s.y) + to(e.y)) / 2)], (l,)
    find(k)
    for n in connected(t):
        if not isinstance(n, pcbnew.ZONE):
            union(k, n.m_Uuid.AsString())
    for l in lays:
        for x, y in pts:
            i = island(l, x, y)
            if i is not None:
                union(k, ("isl", l, i))
for l in (0, 1):
    for i in range(poly[l].OutlineCount()):
        find(("isl", l, i))

groups = collections.defaultdict(list)
for k in list(par):
    groups[find(k)].append(k)
order = sorted(groups.values(), key=len, reverse=True)
main = set(order[0])
print(f"grupos de GND: {len(order)} (principal com {len(main)} nós)")


def fits(x, y, need):
    """Via cabe em (x, y)? need: {camada: conjunto de ilhas aceitas}."""
    if any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in pads):
        return False
    for a in range(-1, 8):
        px = x + (R_TEST * math.cos(a * math.pi / 4) if a >= 0 else 0)
        py = y + (R_TEST * math.sin(a * math.pi / 4) if a >= 0 else 0)
        for l, ok in need.items():
            if island(l, px, py) not in ok:
                return False
    return True


new_vias, pairs, dead = [], [], []
main_isl = {l: {k[2] for k in main if isinstance(k, tuple) and k[1] == l} for l in (0, 1)}
main_pts = [info[k][1] for k in main if k in info]
for g in order[1:]:
    isl = [k for k in g if isinstance(k, tuple)]
    its = [k for k in g if k in info]
    desc = ", ".join(info[k][0] for k in its if info[k][0] not in ("via", "trk"))[:60] or f"{len(its)} trilhas/vias"
    done = False
    for _, l, i in isl:
        q = boxes[l][i]
        x0, y0, x1, y1 = to(q.GetLeft()), to(q.GetTop()), to(q.GetRight()), to(q.GetBottom())
        y = y0
        while y <= y1 and not done:
            x = x0
            while x <= x1:
                if fits(x, y, {l: {i}, 1 - l: main_isl[1 - l]}):
                    new_vias.append((x, y))
                    print(f"  ilha {'FB'[l]}{i} ({desc}): via em ({x:.2f},{y:.2f})")
                    done = True
                    break
                x += 0.2
            y += 0.2
        if done:
            break
    if not done and its and all(info[k][0] == "via" for k in its):
        # via de costura que ficou em cobre removido (ilha solta): não liga nada, sai
        dead += its
        print(f"  {len(its)} via(s) solta(s) em ({info[its[0]][1][0]:.2f},{info[its[0]][1][1]:.2f}): removida(s)")
        continue
    if not done:
        if not its:
            print(f"  ilha sem pad/trilha {[(k[1], k[2]) for k in isl]}: cobre solto, ignorada")
            continue
        k = its[0]
        p = info[k][1]
        q = min(main_pts, key=lambda m: math.dist(m, p))
        print(f"  {desc}: sem ponto para via; par para rotear ({p[0]:.2f},{p[1]:.2f}) -> ({q[0]:.2f},{q[1]:.2f})")
        pairs.append({"items": [{"description": f"{info[k][0]} [GND]", "pos": {"x": p[0], "y": p[1]}, "layers": info[k][2]},
                                {"description": "principal [GND]", "pos": {"x": q[0], "y": q[1]}, "layers": [0, 1]}]})

out = [a for a in sys.argv[1:] if not a.startswith("--")]
if out:
    json.dump({"violations": [], "unconnected_items": pairs}, open(out[0], "w", encoding="utf-8"))
print(f"vias novas: {len(new_vias)}; vias soltas removidas: {len(dead)}; pares para rotear: {len(pairs)}; abertas no KiCad: {conn.GetUnconnectedCount(True)}")
if "--dry" not in sys.argv and (new_vias or dead):
    for x, y in new_vias:
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        v.SetWidth(pcbnew.F_Cu, mm(VIA_D))
        v.SetDrill(mm(VIA_DRILL))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(gnd)
        b.Add(v)
    objs = {t.m_Uuid.AsString(): t for t in b.GetTracks()}
    for k in dead:                      # remoções por último (SWIG)
        b.Remove(objs[k])
    b.Save(PCB)
    print("placa salva")
