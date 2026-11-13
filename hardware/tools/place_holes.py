"""Furação M2 para fixar a placa na case.

Parte dos alvos do esboço (unidades de tecla) e procura, perto de cada um, o ponto com mais folga de
pads, recortes (Edge.Cuts dos LEDs), corpo dos switches (topo) e soquetes hotswap (verso).
Sem --apply só lista. Com --apply: remove furos H* antigos, coloca MountingHole_2.2mm_M2 (NPTH) e
apaga trilhas/vias dentro da área de apoio (o roteamento é refeito depois).

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/place_holes.py [--fixed] [--apply]
"""
import math
import sys
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parent.parent
PCB = str(HW / "teclado.kicad_pcb")
FP_LIB = r"C:\Program Files\KiCad\10.0\share\kicad\footprints\MountingHole.pretty"
FP_NAME = "MountingHole_2.2mm_M2"
mm, to = pcbnew.FromMM, pcbnew.ToMM

U = 19.05
X0, Y0 = 23.075, 45.625          # canto superior esquerdo da tecla (0,0) em mm
# alvos do esboço (pcb-esboco-v7), em unidades de tecla
TARGETS_U = [(3, 1.82), (12, 1.82), (5.75, 3.82), (9.75, 3.82), (5.45, 5.5), (8.3, 5.5),
             (1.25, 4.82), (6.2, -0.75), (10.6, -0.75), (13.0, -0.75)]

# posições finais (mm, origem do KiCad), usadas com --fixed. H8 foi 10 mm para a direita para dar lugar
# ao módulo Black Pill.
FIXED = [(79.98, 83.05), (252.18, 83.30), (132.61, 120.90), (208.81, 120.90), (126.90, 150.15), (181.19, 150.15),
         (46.64, 143.45), (151.50, 31.34), (225.00, 30.84), (276.23, 30.84)]

R_CU = 2.25 + 0.30              # apoio do espaçador/cabeça (Ø4,5) + folga até cobre/recorte
R_HEAD = 1.9 + 0.2               # cabeça do parafuso M2 até o corpo do switch (topo)
EDGE_MIN = 3.5                   # centro do furo até a borda da placa
SEARCH_X, SEARCH_Y, STEP = 12.0, 10.0, 0.25


def rect_dist(px, py, r):
    dx = max(r[0] - px, 0, px - r[2])
    dy = max(r[1] - py, 0, py - r[3])
    return math.hypot(dx, dy)


def seg_dist(px, py, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / L))
    return math.hypot(px - x1 - t * dx, py - y1 - t * dy)


def bbox(o):
    b = o.GetBoundingBox()
    return (to(b.GetLeft()), to(b.GetTop()), to(b.GetRight()), to(b.GetBottom()))


def local_rect(f, x1, y1, x2, y2):
    """Retângulo em coordenadas locais do footprint -> bbox na placa (respeita a rotação)."""
    a = math.radians(f.GetOrientationDegrees())
    c, s = math.cos(a), math.sin(a)
    p = f.GetPosition()
    pts = [(to(p.x) + x * c + y * s, to(p.y) - x * s + y * c) for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
    return (min(q[0] for q in pts), min(q[1] for q in pts), max(q[0] for q in pts), max(q[1] for q in pts))


b = pcbnew.LoadBoard(PCB)
edge = [p for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts for p in (d.GetStart(), d.GetEnd())]
BX0, BY0 = to(min(p.x for p in edge)), to(min(p.y for p in edge))
BX1, BY1 = to(max(p.x for p in edge)), to(max(p.y for p in edge))

cu_rects, head_rects = [], []     # obstáculos com R_CU / R_HEAD
for f in b.GetFootprints():
    name = str(f.GetFPID().GetLibItemName())
    if name.startswith("MountingHole"):
        continue
    for pad in f.Pads():
        cu_rects.append(bbox(pad))
    for g in f.GraphicalItems():
        if g.GetLayer() == pcbnew.Edge_Cuts:
            cu_rects.append(bbox(g))
    if name.startswith("SW_Hotswap"):
        head_rects.append(local_rect(f, -7, -7, 7, 7))             # corpo do switch (recorte 14x14 da plate)
        cu_rects.append(local_rect(f, -8.4, -7.0, 7.2, -0.6))      # soquete Kailh no verso
    elif not name.startswith("Stabilizer"):
        cy = f.GetCourtyard(f.GetLayer())
        if cy.OutlineCount():
            q = cy.BBox()
            cu_rects.append((to(q.GetLeft()), to(q.GetTop()), to(q.GetRight()), to(q.GetBottom())))

segs, vias = [], []
for t in b.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        p = t.GetPosition()
        vias.append((to(p.x), to(p.y), to(t.GetWidth(pcbnew.F_Cu)) / 2, t))
    else:
        s, e = t.GetStart(), t.GetEnd()
        segs.append((to(s.x), to(s.y), to(e.x), to(e.y), to(t.GetWidth()) / 2, t))


def near(rects, px, py, r):
    return [q for q in rects if q[0] - r <= px <= q[2] + r and q[1] - r <= py <= q[3] + r]


def hits(px, py):
    """Trilhas e vias que invadem a área de apoio do furo."""
    out = [s[5] for s in segs if seg_dist(px, py, s[:4]) - s[4] < R_CU]
    out += [v[3] for v in vias if math.hypot(px - v[0], py - v[1]) - v[2] < R_CU]
    return out


FIX = "--fixed" in sys.argv      # usa as posições finais, sem procurar de novo
chosen = list(FIXED) if FIX else []
for ux, uy in ([] if FIX else TARGETS_U):
    tx, ty = X0 + ux * U, Y0 + uy * U
    lc = near(cu_rects, tx, ty, SEARCH_X + SEARCH_Y + R_CU)
    lh = near(head_rects, tx, ty, SEARCH_X + SEARCH_Y + R_HEAD)
    best = None
    nx, ny = int(SEARCH_X / STEP), int(SEARCH_Y / STEP)
    for i in range(-nx, nx + 1):
        for j in range(-ny, ny + 1):
            px, py = tx + i * STEP, ty + j * STEP
            if min(px - BX0, BX1 - px, py - BY0, BY1 - py) < EDGE_MIN:
                continue
            if any(math.hypot(px - c[0], py - c[1]) < 25 for c in chosen):
                continue
            m = min([rect_dist(px, py, r) - R_CU for r in lc] + [rect_dist(px, py, r) - R_HEAD for r in lh] + [9])
            if m < 0:
                continue
            n = len(hits(px, py))
            score = min(m, 1.0) - 0.15 * n - 0.02 * math.hypot(px - tx, py - ty)
            if best is None or score > best[0]:
                best = (score, px, py, m, n)
    if best is None:
        print(f"alvo ({ux},{uy}) -> ({tx:.2f},{ty:.2f}): SEM PONTO LIVRE")
        continue
    _, px, py, m, n = best
    chosen.append((px, py))
    print(f"alvo ({ux:5.2f},{uy:5.2f}) ({tx:6.2f},{ty:6.2f}) -> furo ({px:6.2f},{py:6.2f})  folga extra {m:.2f} mm, "
          f"desvio {math.hypot(px - tx, py - ty):4.1f} mm, trilhas/vias a refazer: {n}")

if "--apply" not in sys.argv:
    sys.exit(0)

# Furos que já existem são movidos; só os que faltam são criados. Todas as remoções ficam para o fim:
# depois de um b.Remove() o pcbnew (SWIG) deixa de funcionar direito no mesmo processo.
old = {f.GetReference(): f for f in b.GetFootprints() if str(f.GetFPID().GetLibItemName()).startswith("MountingHole")}
gone = []
for i, (px, py) in enumerate(chosen, 1):
    gone += hits(px, py)
    f = old.pop(f"H{i}", None)
    if f is None:
        f = pcbnew.FootprintLoad(FP_LIB, FP_NAME)
        f.SetReference(f"H{i}")
        f.SetValue("M2")
        f.Reference().SetVisible(False)
        f.Value().SetVisible(False)
        f.SetAttributes(f.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_BOARD_ONLY)
        b.Add(f)
    f.SetPosition(pcbnew.VECTOR2I(mm(px), mm(py)))
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
gone = list({id(t): t for t in gone}.values())
for t in gone + list(old.values()):
    b.Remove(t)
b.Save(PCB)
print(f"{len(chosen)} furos M2 colocados, {len(gone)} trilhas/vias removidas, {len(old)} furos a mais removidos")
