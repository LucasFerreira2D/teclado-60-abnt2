"""Costura os planos de GND (F.Cu e B.Cu) com vias.

As trilhas cortam os planos em ilhas; cada ilha só fica ligada se tiver uma via para o plano do outro
lado. Aqui: preenche os planos mantendo as ilhas, coloca uma via GND em cada ponto de uma grade onde
há cobre de GND nas duas camadas com espaço para a via, e preenche de novo removendo o que continuar solto.
Vias GND antigas da costura (as que não tocam trilha) são refeitas a cada execução.

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/stitch_gnd.py [passo_mm]
"""
import math
import sys
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parent.parent
PCB = str(HW / "teclado.kicad_pcb")
mm, to = pcbnew.FromMM, pcbnew.ToMM

_a = [a for a in sys.argv[1:] if not a.startswith("--")]
STEP = float(_a[0]) if _a else 4.0
VIA_D, VIA_DRILL = 0.6, 0.3
R_TEST = VIA_D / 2 + 0.1          # o cobre do plano já guarda a folga das outras redes
PAD_GAP = 0.3                     # via fora dos pads (nada de via-in-pad)

b = pcbnew.LoadBoard(PCB)
gnd = b.FindNet("GND")
zones = [z for z in b.Zones() if z.GetNetname() == "GND" and not z.GetIsRuleArea()]
zf = next(z for z in zones if z.GetLayer() == pcbnew.F_Cu)
zb = next(z for z in zones if z.GetLayer() == pcbnew.B_Cu)

# vias de costura antigas: via GND sem trilha chegando nela
ends = set()
for t in b.GetTracks():
    if not isinstance(t, pcbnew.PCB_VIA):
        ends.add((t.GetStart().x, t.GetStart().y))
        ends.add((t.GetEnd().x, t.GetEnd().y))
old = [t for t in b.GetTracks() if isinstance(t, pcbnew.PCB_VIA) and t.GetNetname() == "GND"
       and (t.GetPosition().x, t.GetPosition().y) not in ends]

if "--clear" in sys.argv:          # só tira as vias de costura (antes de rotear de novo)
    for t in old:
        b.Remove(t)
    b.Save(PCB)
    print(f"vias de costura removidas: {len(old)}")
    sys.exit(0)

pads = []
for f in b.GetFootprints():
    for p in f.Pads():
        q = p.GetBoundingBox()
        pads.append((to(q.GetLeft()) - PAD_GAP - VIA_D / 2, to(q.GetTop()) - PAD_GAP - VIA_D / 2,
                     to(q.GetRight()) + PAD_GAP + VIA_D / 2, to(q.GetBottom()) + PAD_GAP + VIA_D / 2))
CELL = 10.0
grid = {}
for r in pads:
    for i in range(int(r[0] // CELL), int(r[2] // CELL) + 1):
        for j in range(int(r[1] // CELL), int(r[3] // CELL) + 1):
            grid.setdefault((i, j), []).append(r)


edge = [p for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts for p in (d.GetStart(), d.GetEnd())]
x0, y0 = to(min(p.x for p in edge)) + 1.0, to(min(p.y for p in edge)) + 1.0
x1, y1 = to(max(p.x for p in edge)) - 1.0, to(max(p.y for p in edge)) - 1.0

# remoções só agora: depois de um b.Remove() o SWIG perde os tipos das listas da placa
for t in old:
    b.Remove(t)

for z in zones:
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())


# vias que ficam (de qualquer rede): a costura não pode cair em cima nem encostada (furo com furo)
_old = {id(t) for t in old}
keep = [(to(t.GetPosition().x), to(t.GetPosition().y)) for t in b.GetTracks() if isinstance(t, pcbnew.PCB_VIA) and id(t) not in _old]


def on_pad(x, y):
    return any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in grid.get((int(x // CELL), int(y // CELL)), ()))


def filled(x, y):
    for a in range(-1, 8):
        px = x + (R_TEST * math.cos(a * math.pi / 4) if a >= 0 else 0)
        py = y + (R_TEST * math.sin(a * math.pi / 4) if a >= 0 else 0)
        v = pcbnew.VECTOR2I(mm(px), mm(py))
        if not (zf.HitTestFilledArea(pcbnew.F_Cu, v) and zb.HitTestFilledArea(pcbnew.B_Cu, v)):
            return False
    return True


n = 0
y = y0
while y <= y1:
    x = x0
    while x <= x1:
        # procura dentro da célula o primeiro ponto que serve
        for dx, dy in ((0, 0), (STEP / 3, 0), (0, STEP / 3), (-STEP / 3, 0), (0, -STEP / 3),
                       (STEP / 3, STEP / 3), (-STEP / 3, -STEP / 3), (STEP / 3, -STEP / 3), (-STEP / 3, STEP / 3)):
            px, py = x + dx, y + dy
            if not on_pad(px, py) and filled(px, py) and all(math.hypot(px - vx, py - vy) > 1.0 for vx, vy in keep):
                v = pcbnew.PCB_VIA(b)
                v.SetPosition(pcbnew.VECTOR2I(mm(px), mm(py)))
                v.SetWidth(pcbnew.F_Cu, mm(VIA_D))
                v.SetDrill(mm(VIA_DRILL))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetNet(gnd)
                b.Add(v)
                n += 1
                break
        x += STEP
    y += STEP

for z in zones:
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(PCB)
print(f"vias de costura: {n} (removidas {len(old)} antigas), grade {STEP} mm")
