"""Acabamento: troca os trechos de trilha em ângulo qualquer por trechos retos + diagonais de 45°.

Cada trecho torto (p1 -> p2) vira uma combinação reto/45° com as MESMAS pontas, então nenhuma ligação
muda. Uma forma só é aceita se respeitar o isolamento contra todo cobre de outras redes na mesma camada
(trilhas, vias, pads), os furos, os recortes dos LEDs e a borda. Se nenhuma forma couber, o trecho fica
como está.

Rode sem as vias de costura (stitch_gnd.py --clear) e refaça planos e costura depois.

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/align45.py [--dry]
"""
import collections
import math
import sys
from pathlib import Path

import pcbnew

PCB = str(Path(__file__).resolve().parent.parent / "teclado.kicad_pcb")
mm, to = pcbnew.FromMM, pcbnew.ToMM
CLR, HOLE_CLR, EDGE, LED_EDGE, MH_R, TOL = 0.2, 0.25, 0.5, 0.2, 2.25, 0.005
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
CELL = 4.0

b = pcbnew.LoadBoard(PCB)
edge = [p for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts for p in (d.GetStart(), d.GetEnd())]
BX0, BY0 = to(min(p.x for p in edge)), to(min(p.y for p in edge))
BX1, BY1 = to(max(p.x for p in edge)), to(max(p.y for p in edge))


def pt_seg(p, a, c):
    dx, dy = c[0] - a[0], c[1] - a[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def cross(o, a, c):
    return (a[0] - o[0]) * (c[1] - o[1]) - (a[1] - o[1]) * (c[0] - o[0])


def seg_seg(a, c, d, e):
    """Distância entre os segmentos a-c e d-e."""
    d1, d2, d3, d4 = cross(d, e, a), cross(d, e, c), cross(a, c, d), cross(a, c, e)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0:
        return 0.0
    return min(pt_seg(a, d, e), pt_seg(c, d, e), pt_seg(d, a, c), pt_seg(e, a, c))


def seg_rect(a, c, r):
    x0, y0, x1, y1 = r
    if (x0 <= a[0] <= x1 and y0 <= a[1] <= y1) or (x0 <= c[0] <= x1 and y0 <= c[1] <= y1):
        return 0.0
    cs = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    return min(seg_seg(a, c, cs[i], cs[(i + 1) % 4]) for i in range(4))


class Ob:
    """Obstáculo: segmento (trilha/via/furo, com raio) ou retângulo (pad/recorte)."""
    __slots__ = ("net", "rect", "a", "c", "r", "clr", "alive")

    def __init__(self, net, rect=None, a=None, c=None, r=0.0, clr=CLR):
        self.net, self.rect, self.a, self.c, self.r, self.clr, self.alive = net, rect, a, c, r, clr, True

    def box(self):
        if self.rect:
            return self.rect
        return (min(self.a[0], self.c[0]) - self.r, min(self.a[1], self.c[1]) - self.r,
                max(self.a[0], self.c[0]) + self.r, max(self.a[1], self.c[1]) + self.r)

    def dist(self, a, c):
        return seg_rect(a, c, self.rect) if self.rect else seg_seg(a, c, self.a, self.c) - self.r


index = {0: collections.defaultdict(list), 1: collections.defaultdict(list)}


def add(ob, layers):
    x0, y0, x1, y1 = ob.box()
    for l in layers:
        for i in range(int((x0 - 1) // CELL), int((x1 + 1) // CELL) + 1):
            for j in range(int((y0 - 1) // CELL), int((y1 + 1) // CELL) + 1):
                index[l][(i, j)].append(ob)
    return ob


def bbox(o):
    q = o.GetBoundingBox()
    return to(q.GetLeft()), to(q.GetTop()), to(q.GetRight()), to(q.GetBottom())


for f in b.GetFootprints():
    name = str(f.GetFPID().GetLibItemName())
    for g in f.GraphicalItems():
        if g.GetLayer() == pcbnew.Edge_Cuts:
            add(Ob(-1, rect=bbox(g), clr=LED_EDGE), (0, 1))
    for p in f.Pads():
        c = p.GetPosition()
        c = (to(c.x), to(c.y))
        x0, y0, x1, y1 = bbox(p)
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            r = MH_R if name.startswith("MountingHole") else max(x1 - x0, y1 - y0, to(p.GetDrillSize().x), to(p.GetDrillSize().y)) / 2
            add(Ob(-1, a=c, c=c, r=r, clr=HOLE_CLR), (0, 1))
        else:
            add(Ob(p.GetNetCode() or -1, rect=(x0, y0, x1, y1)), [l for l in (0, 1) if p.IsOnLayer(LAYERS[l])])

segs = []          # (track, ob, layer)
same = collections.defaultdict(list)       # rede -> [(camadas, ponto)] de pontas de trilha e vias
for t in b.GetTracks():
    net = t.GetNetCode() or -1
    if isinstance(t, pcbnew.PCB_VIA):
        c = t.GetPosition()
        c = (to(c.x), to(c.y))
        add(Ob(net, a=c, c=c, r=to(t.GetWidth(pcbnew.F_Cu)) / 2), (0, 1))
        same[net].append(((0, 1), c))
    else:
        s, e = t.GetStart(), t.GetEnd()
        l = 0 if t.GetLayer() == pcbnew.F_Cu else 1
        ob = add(Ob(net, a=(to(s.x), to(s.y)), c=(to(e.x), to(e.y)), r=to(t.GetWidth()) / 2), (l,))
        segs.append((t, ob, l))
        same[net] += [((l,), ob.a), ((l,), ob.c)]


def clear(net, l, a, c, hw):
    if min(a[0], c[0]) - hw < BX0 + EDGE or max(a[0], c[0]) + hw > BX1 - EDGE or min(a[1], c[1]) - hw < BY0 + EDGE or max(a[1], c[1]) + hw > BY1 - EDGE:
        return False
    seen = set()
    for i in range(int((min(a[0], c[0]) - 1) // CELL), int((max(a[0], c[0]) + 1) // CELL) + 1):
        for j in range(int((min(a[1], c[1]) - 1) // CELL), int((max(a[1], c[1]) + 1) // CELL) + 1):
            for ob in index[l].get((i, j), ()):
                if ob.alive and ob.net != net and id(ob) not in seen:
                    seen.add(id(ob))
                    if ob.dist(a, c) < hw + ob.clr + TOL:
                        return False
    return True


def shapes(p1, p2):
    """Polilinhas reto/45° de p1 a p2: [reto a][diagonal][reto resto], com o reto dividido de várias formas."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    sx, sy = (1 if dx > 0 else -1), (1 if dy > 0 else -1)
    d = min(abs(dx), abs(dy))
    S = abs(abs(dx) - abs(dy))
    horiz = abs(dx) > abs(dy)
    out = []
    for frac in (0.0, 1.0, 0.5, 0.25, 0.75, 0.125, 0.875, 0.375, 0.625):
        a = S * frac
        q1 = (p1[0] + sx * a, p1[1]) if horiz else (p1[0], p1[1] + sy * a)
        q2 = (q1[0] + sx * d, q1[1] + sy * d)
        out.append([p1, q1, q2, p2])
    # "V" de duas diagonais (uma vai além e a outra volta), nas duas ordens
    u, v = (abs(dx) + abs(dy)) / 2, abs(abs(dx) - abs(dy)) / 2
    for first in (u, v):
        if horiz:
            q = (p1[0] + sx * first, p1[1] + (sy if first == u else -sy) * first)
        else:
            q = (p1[0] + (sx if first == u else -sx) * first, p1[1] + sy * first)
        out.append([p1, q, p2])
    return [[p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 1e-6] for pts in out]


def odd(a, c):
    ang = math.degrees(math.atan2(abs(c[1] - a[1]), abs(c[0] - a[0])))
    return min(ang, 90 - ang, abs(ang - 45)) >= 0.05 and math.dist(a, c) > 0.01


new, gone, kept = [], [], 0
for t, ob, l in segs:
    if not odd(ob.a, ob.c):
        continue
    # outra trilha ou via da mesma rede encostando no MEIO do trecho: mudar a forma desfaria a junção
    if any(l in ls and pt_seg(q, ob.a, ob.c) <= ob.r + 0.01 and math.dist(q, ob.a) > 0.05 and math.dist(q, ob.c) > 0.05
           for ls, q in same[ob.net]):
        kept += 1
        continue
    ob.alive = False                       # o próprio trecho não conta (mesma rede de qualquer forma)
    done = False
    for pts in shapes(ob.a, ob.c):
        if all(clear(ob.net, l, pts[i], pts[i + 1], ob.r) for i in range(len(pts) - 1)):
            for i in range(len(pts) - 1):
                add(Ob(ob.net, a=pts[i], c=pts[i + 1], r=ob.r), (l,))
                new.append((t, l, pts[i], pts[i + 1]))
            gone.append(t)
            done = True
            break
    if not done:
        ob.alive = True
        kept += 1

print(f"trechos tortos: {len(gone) + kept}; alinhados: {len(gone)} (viraram {len(new)} trechos); sem espaço, mantidos: {kept}")
if "--dry" not in sys.argv and gone:
    for t, l, p1, p2 in new:
        n = pcbnew.PCB_TRACK(b)
        n.SetStart(pcbnew.VECTOR2I(mm(p1[0]), mm(p1[1])))
        n.SetEnd(pcbnew.VECTOR2I(mm(p2[0]), mm(p2[1])))
        n.SetWidth(t.GetWidth())
        n.SetLayer(t.GetLayer())
        n.SetNet(t.GetNet())
        b.Add(n)
    for t in gone:                         # remoções por último (SWIG)
        b.Remove(t)
    b.Save(PCB)
    print("placa salva")
