"""Cria teclado.kicad_pcb vazio: 2 camadas, 1,6 mm, contorno 292 x 143 mm com cantos arredondados (r = 3 mm)."""
import sys
import pcbnew

out = sys.argv[1]
W, H, R = 292.0, 143.0, 3.0
X0, Y0 = 20.0, 20.0
b = pcbnew.BOARD()
b.SetCopperLayerCount(2)
b.GetDesignSettings().SetBoardThickness(pcbnew.FromMM(1.6))
mm = lambda x, y: pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))

def seg(x1, y1, x2, y2):
    s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(pcbnew.FromMM(0.1))
    s.SetStart(mm(x1, y1)); s.SetEnd(mm(x2, y2)); b.Add(s)

def arc(cx, cy, sx, sy, ang):
    s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_ARC)
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(pcbnew.FromMM(0.1))
    s.SetCenter(mm(cx, cy)); s.SetStart(mm(sx, sy)); s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T)); b.Add(s)

X1, Y1 = X0 + W, Y0 + H
seg(X0 + R, Y0, X1 - R, Y0); seg(X1, Y0 + R, X1, Y1 - R); seg(X1 - R, Y1, X0 + R, Y1); seg(X0, Y1 - R, X0, Y0 + R)
arc(X1 - R, Y0 + R, X1 - R, Y0, 90); arc(X1 - R, Y1 - R, X1, Y1 - R, 90)
arc(X0 + R, Y1 - R, X0 + R, Y1, 90); arc(X0 + R, Y0 + R, X0, Y0 + R, 90)
b.Save(out)
print("ok", out)
