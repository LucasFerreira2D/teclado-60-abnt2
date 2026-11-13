"""Espalha os footprints numa área de espera dentro da placa (empacotamento em prateleiras, 2 mm de folga).
Só para visualizar/organizar antes do posicionamento real."""
import pcbnew
from pathlib import Path

PCB = str(Path(__file__).resolve().parent.parent / "teclado.kicad_pcb")
b = pcbnew.LoadBoard(PCB)
bb = b.GetBoardEdgesBoundingBox()
X0, Y0, XW = pcbnew.ToMM(bb.GetX()) + 6, pcbnew.ToMM(bb.GetY()) + 6, pcbnew.ToMM(bb.GetWidth()) - 12
GAP = 2.0
import re

def is_key_part(ref):
    m = re.match(r"(SW|D|LED|C|ST)(\d+)$", ref)
    return bool(m) and int(m.group(2)) < 100

fps = sorted([f for f in b.GetFootprints() if not is_key_part(f.GetReference())], key=lambda f: -pcbnew.ToMM(f.GetCourtyard(pcbnew.F_CrtYd).BBox().GetHeight() or f.GetBoundingBox(False).GetHeight()))
x, y, row_h = X0, Y0, 0.0
for f in fps:
    r = f.GetBoundingBox(False)
    w, h = pcbnew.ToMM(r.GetWidth()), pcbnew.ToMM(r.GetHeight())
    if x + w > X0 + XW:
        x, y, row_h = X0, y + row_h + GAP, 0.0
    # desloca para que o canto superior esquerdo da caixa caia em (x, y)
    dx = pcbnew.FromMM(x) - r.GetX()
    dy = pcbnew.FromMM(y) - r.GetY()
    f.Move(pcbnew.VECTOR2I(dx, dy))
    x += w + GAP
    row_h = max(row_h, h)
b.Save(PCB)
print("ok", len(fps), "footprints; altura usada", round(y + row_h - Y0, 1), "mm")
