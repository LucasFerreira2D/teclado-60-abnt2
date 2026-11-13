"""Limpa o roteamento depois de trocar componentes (ex.: chip QFN -> módulo em soquete).

Remove:
  1. trilhas e vias de redes que não têm mais nenhum pad;
  2. tudo que passa pela região dada (--region x0,y0,x1,y1), que vai ser roteada de novo;
  3. pontas soltas: trilha com uma ponta que não encosta em pad, via ou outra trilha da mesma rede,
     e via ligada a menos de duas coisas. Repete até não sobrar nenhuma. O GND fica fora deste passo
     (as trilhas e vias dele terminam no plano).
Também move um furo de fixação (--move-hole REF,x,y).

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/clean_tracks.py [--region x0,y0,x1,y1] [--move-hole H8,151.5,31.34] [--dry]
"""
import collections
import math
import sys
from pathlib import Path

import pcbnew

PCB = str(Path(__file__).resolve().parent.parent / "teclado.kicad_pcb")
mm, to = pcbnew.FromMM, pcbnew.ToMM
b = pcbnew.LoadBoard(PCB)


def arg(name):
    return sys.argv[sys.argv.index(name) + 1].split(",") if name in sys.argv else None


region = [float(v) for v in arg("--region")] if arg("--region") else None
hole = arg("--move-hole")
if hole:
    f = next(f for f in b.GetFootprints() if f.GetReference() == hole[0])
    f.SetPosition(pcbnew.VECTOR2I(mm(float(hole[1])), mm(float(hole[2]))))
    print(f"{hole[0]} movido para ({hole[1]}, {hole[2]})")

pads = collections.defaultdict(list)        # rede -> [(pad, camadas)]
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetNetCode():
            pads[p.GetNetCode()].append((p, [l for l in (pcbnew.F_Cu, pcbnew.B_Cu) if p.IsOnLayer(l)]))


class It:
    __slots__ = ("o", "net", "via", "l", "p1", "p2", "hw", "alive")


items = []
by_net = collections.defaultdict(list)
for t in b.GetTracks():
    it = It()
    it.o, it.net, it.alive = t, t.GetNetCode(), True
    it.via = isinstance(t, pcbnew.PCB_VIA)
    if it.via:
        p = t.GetPosition()
        it.p1 = it.p2 = (to(p.x), to(p.y))
        it.l, it.hw = None, to(t.GetWidth(pcbnew.F_Cu)) / 2
    else:
        s, e = t.GetStart(), t.GetEnd()
        it.p1, it.p2, it.l, it.hw = (to(s.x), to(s.y)), (to(e.x), to(e.y)), t.GetLayer(), to(t.GetWidth()) / 2
    items.append(it)
    by_net[it.net].append(it)

count = collections.Counter()

# 1. redes sem pad
for it in items:
    if it.net not in pads:
        it.alive = False
        count["rede sem pad"] += 1


# 2. região
def seg_hits_box(p1, p2, x0, y0, x1, y1):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, p1[0] - x0), (dx, x1 - p1[0]), (-dy, p1[1] - y0), (dy, y1 - p1[1])):
        if p == 0:
            if q < 0:
                return False
        elif p < 0:
            t0 = max(t0, q / p)
        else:
            t1 = min(t1, q / p)
    return t0 <= t1


if region:
    for it in items:
        if it.alive and seg_hits_box(it.p1, it.p2, *region):
            it.alive = False
            count["na região"] += 1


# 3. pontas soltas
def pt_seg(pt, a, c):
    dx, dy = c[0] - a[0], c[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / L))
    return math.hypot(pt[0] - a[0] - t * dx, pt[1] - a[1] - t * dy)


def on_pad(net, pt, layer):
    v = pcbnew.VECTOR2I(mm(pt[0]), mm(pt[1]))
    return any(layer in lays and p.HitTest(v) for p, lays in pads.get(net, ()))


def attached(it, pt):
    if on_pad(it.net, pt, it.l):
        return True
    for o in by_net[it.net]:
        if o is it or not o.alive:
            continue
        if o.via:
            if math.dist(pt, o.p1) <= o.hw + 0.01:
                return True
        elif o.l == it.l and pt_seg(pt, o.p1, o.p2) <= o.hw + 0.01:
            return True
    return False


def via_links(v):
    n = 0
    for l in (pcbnew.F_Cu, pcbnew.B_Cu):
        if on_pad(v.net, v.p1, l) or any(o.alive and not o.via and o.l == l and pt_seg(v.p1, o.p1, o.p2) <= o.hw + v.hw
                                         for o in by_net[v.net]):
            n += 1
    return n


gnd = b.GetNetcodeFromNetname("GND")
changed = True
while changed:
    changed = False
    for net, its in by_net.items():
        if net == gnd or net not in pads:
            continue
        for it in its:
            if not it.alive:
                continue
            if it.via:
                dead = via_links(it) < 2
            else:
                dead = not attached(it, it.p1) or not attached(it, it.p2)
            if dead:
                it.alive = False
                count["ponta solta"] += 1
                changed = True

gone = [it for it in items if not it.alive]
print(f"removidos {len(gone)} de {len(items)} itens: {dict(count)}")
if "--dry" not in sys.argv:
    for it in gone:                    # remoções por último: depois de um Remove o SWIG perde os tipos
        b.Remove(it.o)
    b.Save(PCB)
    print("placa salva")
