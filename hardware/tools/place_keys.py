"""Posiciona switches, diodos, estabilizadores, LEDs e capacitores dos LEDs na placa do projeto,
usando as posições calculadas pelo kbplacer (kb_out/kb.kicad_pcb), deslocadas para o contorno.

Layout de teclas (15u x 6u) centrado na largura e encostado embaixo, deixando a faixa superior
(USB-C, OLED, knob, eletrônica) livre.
LED SK6812MINI-E: verso (montagem reversa), 5,08 mm ao sul do centro do switch (south-facing).
Capacitor do LED: verso, ao lado esquerdo do LED.
"""
import re
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parent.parent
PCB = HW / "teclado.kicad_pcb"
KB = HW / "kb_out" / "kb.kicad_pcb"
U = 19.05
MARGIN = 3.125  # (292 - 15u) / 2
LED_DY = 5.08
CAP_DX, CAP_DY = -4.6, 5.08

mm = pcbnew.FromMM
to = pcbnew.ToMM

kb = pcbnew.LoadBoard(str(KB))
board = pcbnew.LoadBoard(str(PCB))
kbfp = {f.GetReference(): f for f in kb.GetFootprints()}
fps = {f.GetReference(): f for f in board.GetFootprints()}

# origem do layout no kbplacer: canto superior esquerdo da tecla 0,0 (SW1 = Esc, 1u)
sw1 = kbfp["SW1"].GetPosition()
kx0, ky0 = to(sw1.x) - U / 2, to(sw1.y) - U / 2
bb = board.GetBoardEdgesBoundingBox()
bx0, by1 = to(bb.GetX()), to(bb.GetBottom())
tx0, ty0 = bx0 + MARGIN, by1 - MARGIN - 6 * U
dx, dy = tx0 - kx0, ty0 - ky0


def put(fp, x, y, angle, back):
    if fp.IsFlipped() != back:
        fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.SetOrientationDegrees(angle)


ROWS = [(1, 13), (14, 27), (28, 41), (42, 54), (55, 68), (69, 76)]  # primeira e última tecla de cada fileira


def serpentine(n):
    for i, (a, z) in enumerate(ROWS):
        if a <= n <= z:
            return a + z - n if i % 2 else n
    raise ValueError(n)


n = 0
for ref, src in kbfp.items():
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    if not m or ref not in fps:
        continue
    kind = m.group(1)
    if kind in ("LED", "C"):
        # cadeia em serpentina: nas fileiras ímpares o LED n fica na tecla espelhada da fileira
        src = kbfp[f"SW{serpentine(int(m.group(2)))}"]
    p = src.GetPosition()
    x, y = to(p.x) + dx, to(p.y) + dy
    if kind in ("SW", "D", "ST"):
        put(fps[ref], x, y, src.GetOrientationDegrees(), src.IsFlipped())
    elif kind == "LED":
        put(fps[ref], x, y + LED_DY, 0, True)
    elif kind == "C":
        put(fps[ref], x + CAP_DX, y + CAP_DY, 90, True)
    else:
        continue
    n += 1

# estabilizadores: o kbplacer não posiciona no modo de criação; STn fica no centro de SWn.
# Enter ISO (2u de altura) leva o estabilizador na vertical.
for ref, f in fps.items():
    m = re.match(r"ST(\d+)$", ref)
    if not m:
        continue
    sw = fps[f"SW{m.group(1)}"]
    p = sw.GetPosition()
    vertical = "Enter" in (kbfp.get(f"SW{m.group(1)}").GetValue() if f"SW{m.group(1)}" in kbfp else "") or ref == "ST41"
    put(f, to(p.x), to(p.y), 90 if vertical else 0, False)
    f.SetExcludedFromBOM(False)  # estabilizador é peça comprada: entra na BOM, como no símbolo
    n += 1

board.Save(str(PCB))
print(f"ok: {n} footprints posicionados; deslocamento ({dx:.3f}, {dy:.3f}) mm; teclas de y={ty0:.2f} a {ty0 + 6 * U:.2f}")
