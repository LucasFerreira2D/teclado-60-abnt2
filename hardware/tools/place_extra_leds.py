"""Posiciona os LEDs extras na placa.

Laterais (LED201-206 esquerda, de cima para baixo; LED207-212 direita, de baixo para cima):
  SK6812SIDE-A na face de cima, face de luz a 0,3 mm da borda, girado para emitir para fora.
  Capacitor (C215-C226) no verso, atrás do LED.
Underglow (LED101-114 + C201-C214): verso, anel a 6 mm da borda, começando perto do último LED de tecla
  (LED76) e seguindo no sentido horário. Cada um vai para o ponto livre mais próximo da posição ideal.
  A faixa superior à esquerda (USB-C, OLED, MCU) e o canto do knob ficam reservados.
"""
import math
from pathlib import Path

import pcbnew

PCB = str(Path(__file__).resolve().parent.parent / "teclado.kicad_pcb")
b = pcbnew.LoadBoard(PCB)
mm, to = pcbnew.FromMM, pcbnew.ToMM
fps = {f.GetReference(): f for f in b.GetFootprints()}
bb = b.GetBoardEdgesBoundingBox()
X0, Y0, X1, Y1 = to(bb.GetX()), to(bb.GetY()), to(bb.GetRight()), to(bb.GetBottom())
KEYS_TOP = Y1 - 3.125 - 6 * 19.05


def put(ref, x, y, angle, back):
    f = fps[ref]
    if f.IsFlipped() != back:
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    f.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    f.SetOrientationDegrees(angle)


# ---------------------------------------------------------------- laterais
FACE_GAP, HALF_DEPTH = 0.3, 0.8
ys = [Y0 + 12 + i * (Y1 - Y0 - 24) / 5 for i in range(6)]
for i, y in enumerate(ys):  # esquerda, de cima para baixo
    put(f"LED{201 + i}", X0 + FACE_GAP + HALF_DEPTH, y, 270, False)
    put(f"C{215 + i}", X0 + 1.6, y, 90, True)
for i, y in enumerate(reversed(ys)):  # direita, de baixo para cima
    put(f"LED{207 + i}", X1 - FACE_GAP - HALF_DEPTH, y, 90, False)
    put(f"C{221 + i}", X1 - 1.6, y, 90, True)

# ---------------------------------------------------------------- underglow
ug_refs = {f"LED{101 + i}" for i in range(14)} | {f"C{201 + i}" for i in range(14)}
obst = []
for f in b.GetFootprints():
    if f.GetReference() in ug_refs:
        continue
    f.BuildCourtyardCaches()
    cy = f.GetCourtyard(pcbnew.B_CrtYd)  # inclui o verso de footprints da frente (hotswap dos switches)
    if cy.OutlineCount():
        for i in range(cy.OutlineCount()):
            r = cy.Outline(i).BBox()
            obst.append((to(r.GetX()), to(r.GetY()), to(r.GetRight()), to(r.GetBottom())))
    elif f.IsFlipped():
        r = f.GetBoundingBox(False)
        obst.append((to(r.GetX()), to(r.GetY()), to(r.GetRight()), to(r.GetBottom())))
    for p in f.Pads():
        if p.HasHole() or p.IsOnLayer(pcbnew.B_Cu):
            r = p.GetBoundingBox()
            obst.append((to(r.GetX()) - 0.3, to(r.GetY()) - 0.3, to(r.GetRight()) + 0.3, to(r.GetBottom()) + 0.3))
# zonas reservadas na faixa superior: USB-C/OLED/MCU à esquerda e o knob à direita
obst.append((X0 + 12, Y0, X0 + 170, KEYS_TOP))
obst.append((X1 - 30, Y0, X1, KEYS_TOP))

CAP_DX = 4.0
BLK = (-3.1, -2.3, 5.1, 2.3)  # courtyard do LED (5.69 x 4.09) centrado + capacitor 0603 vertical a +4.0 mm


def free(x, y):
    a = (x + BLK[0], y + BLK[1], x + BLK[2], y + BLK[3])
    if a[0] < X0 + 1 or a[1] < Y0 + 1 or a[2] > X1 - 1 or a[3] > Y1 - 1:
        return False
    return all(a[2] <= o[0] or a[0] >= o[2] or a[3] <= o[1] or a[1] >= o[3] for o in obst)


U = 19.05
KX0 = X0 + 3.125  # borda esquerda do bloco de teclas


# 14 âncoras, na ordem da cadeia. Com a serpentina o último LED de tecla (LED76) é o do Ctrl esquerdo:
# 5 na borda de baixo (esquerda -> direita), 2 na borda direita (subindo), 2 na faixa superior,
# vãos F4/F5 e Esc/F1 da fileira F, 2 na borda esquerda, canto superior esquerdo (ao lado do LED201).
ANCHORS = [
    (X0 + 43, Y1 - 6), (X1 - 192, Y1 - 6), (X1 - 133, Y1 - 6), (X1 - 74, Y1 - 6), (X1 - 14, Y1 - 6),
    (X1 - 6, Y0 + 95), (X1 - 6, Y0 + 50),
    (X0 + 250, Y0 + 6), (X0 + 190, Y0 + 6),
    (KX0 + 6.25 * U, KEYS_TOP + U / 2), (KX0 + 1.5 * U, KEYS_TOP + U / 2),
    (X0 + 6, Y1 - 28), (X0 + 6, Y0 + 64),
    (X0 + 6.5, Y0 + 6.5),
]
placed = []
for i, (ax, ay) in enumerate(ANCHORS):
    best = None
    for rr in [r * 0.5 for r in range(0, 60)]:
        steps = max(1, int(2 * math.pi * rr / 0.5))
        for k in range(steps):
            x = round((ax + rr * math.cos(2 * math.pi * k / steps)) / 0.25) * 0.25
            y = round((ay + rr * math.sin(2 * math.pi * k / steps)) / 0.25) * 0.25
            if free(x, y):
                best = (x, y)
                break
        if best:
            break
    if not best:
        print(f"  sem lugar livre para LED{101 + i} perto de ({ax:.1f}, {ay:.1f})")
        continue
    x, y = best
    put(f"LED{101 + i}", x, y, 0, True)
    put(f"C{201 + i}", x + CAP_DX, y, 90, True)
    obst.append((x + BLK[0], y + BLK[1], x + BLK[2], y + BLK[3]))
    placed.append((f"LED{101 + i}", round(x, 2), round(y, 2), round(math.dist((x, y), (ax, ay)), 1)))

b.Save(PCB)
print("laterais: 12 LEDs; underglow:")
for p in placed:
    print(f"  {p[0]} em ({p[1]}, {p[2]}) - {p[3]} mm da posição ideal")
