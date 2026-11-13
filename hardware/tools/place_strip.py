"""Posiciona a eletrônica da faixa superior (acima da fileira F).

Frente (F): USB-C na borda de cima (centro a 23,5 mm da borda esquerda, boca para fora),
            header da OLED (módulo 0,91" de 38 x 12 mm, centro em X(2,55u)), knob EC11 (eixo em X(14,45u), Y(-0,85u)).
Verso (B):  ESD, CC, fusível, buffer RGB, pull-ups do I2C, diodo do knob e o módulo Black Pill em soquete
            (DIP-40 largo, deitado, ponta do USB do módulo para a esquerda, logo depois da OLED).

Coordenadas relativas ao canto superior esquerdo da placa (mm, Y para baixo).
"""
from pathlib import Path

import pcbnew

PCB = str(Path(__file__).resolve().parent.parent / "teclado.kicad_pcb")
b = pcbnew.LoadBoard(PCB)
mm, to = pcbnew.FromMM, pcbnew.ToMM
fps = {f.GetReference(): f for f in b.GetFootprints()}
# contorno pelos segmentos de Edge.Cuts (GetBoardEdgesBoundingBox falha no SWIG com a placa roteada)
edge = [p for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts for p in (d.GetStart(), d.GetEnd())]
# A origem é a caixa do contorno contando a espessura da linha (0,1 mm), como o GetBoardEdgesBoundingBox
# devolvia quando a placa foi posicionada pela primeira vez: X0 = Y0 = 19,95 e altura 143,1. Mudar isso
# desloca as peças 0,05 mm em relação às trilhas já roteadas.
EDGE_LW = 0.1
X0, Y0 = to(min(p.x for p in edge)) - EDGE_LW / 2, to(min(p.y for p in edge)) - EDGE_LW / 2
HEIGHT = to(max(p.y for p in edge)) + EDGE_LW / 2 - Y0
U = 19.05
KX0 = 3.125                      # borda esquerda do bloco de teclas (relativo a X0)
KY0 = HEIGHT - 3.125 - 6 * U     # topo do bloco de teclas (relativo a Y0)


def key_xy(ux, uy):
    """Coordenada (relativa) de um ponto em unidades de tecla, origem no canto superior esquerdo do Esc."""
    return KX0 + ux * U, KY0 + uy * U


OLED_CX, _ = key_xy(2.55, 0)
KNOB_X, KNOB_Y = key_xy(14.45, -0.85)

# módulo Black Pill: pino 1 (B12, lado do USB do módulo) em cima à esquerda; fileira 1-20 em cima,
# fileira 21-40 embaixo (perto das teclas). Pino 1 em (95,30; 25,38) mm; corpo de 52,8 x 20,8 mm.
MOD_PIN1 = (75.35, 5.43)
MOD_PITCH, MOD_ROWS = 2.54, 15.24

F, B = False, True
PLACE = {
    # ---- USB-C (frente) e proteção (verso)
    "J1":   (23.5, 3.5, 180, F),          # boca 0,2 mm para fora da borda de cima
    "U2":   (23.5, 11.5, 0, B),           # ESD USBLC6
    "R1":   (17.5, 11.0, 90, B),          # CC1 5,1k
    "R2":   (29.5, 11.0, 90, B),          # CC2 5,1k
    "F1":   (16.0, 17.0, 0, B),           # polyfuse VBUS -> +5V
    "C115": (16.0, 21.5, 0, B),           # 22uF no +5V dos LEDs
    # ---- buffer RGB 3V3 -> 5V (perto do primeiro LED de tecla, no Esc)
    "U4":   (23.5, 18.5, 0, B),
    "C114": (23.5, 22.5, 0, B),
    "R6":   (29.5, 18.5, 90, B),
    # ---- OLED (header na ponta esquerda do módulo OLED) e pull-ups
    "J3":   (OLED_CX - 17.0, 5.6, 0, F),
    "R4":   (38.0, 21.0, 90, B),
    "R5":   (41.0, 21.0, 90, B),
    # ---- pull-down do PA10 (pino 7 do módulo), entre a fileira de cima e a borda
    "R8":   (MOD_PIN1[0] + 6 * MOD_PITCH, 2.65, 0, B),
    # ---- knob (frente) e diodo do clique (verso)
    "SW103": (KNOB_X - 7.5, KNOB_Y - 2.5, 0, F),
    "D101": (KNOB_X + 1.5, 20.5, 0, B),
}

for ref, (x, y, ang, back) in PLACE.items():
    f = fps[ref]
    if f.IsFlipped() != back:
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    f.SetPosition(pcbnew.VECTOR2I(mm(X0 + x), mm(Y0 + y)))
    f.SetOrientationDegrees(ang)

# ---- módulo: no verso, girado até o pino 20 ficar à direita do 1 e o pino 40 abaixo do 1
u1 = fps["U1"]
if not u1.IsFlipped():
    u1.Flip(u1.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
tx, ty = X0 + MOD_PIN1[0], Y0 + MOD_PIN1[1]
ok = False
for ang in (0, 90, 180, 270):
    u1.SetOrientationDegrees(ang)
    pads = {p.GetNumber(): p.GetPosition() for p in u1.Pads()}
    u1.Move(pcbnew.VECTOR2I(mm(tx) - pads["1"].x, mm(ty) - pads["1"].y))
    pads = {p.GetNumber(): (to(p.GetPosition().x), to(p.GetPosition().y)) for p in u1.Pads()}
    if (abs(pads["20"][0] - tx - 19 * MOD_PITCH) < 0.01 and abs(pads["20"][1] - ty) < 0.01
            and abs(pads["40"][0] - tx) < 0.01 and abs(pads["40"][1] - ty - MOD_ROWS) < 0.01):
        ok = True
        break
assert ok, "orientação do módulo não encontrada"

# ---- serigrafia no verso: nomes dos pinos dos cantos e a ponta do USB, para conferir o módulo antes de encaixar
have = {d.GetText() for d in b.GetDrawings() if isinstance(d, pcbnew.PCB_TEXT)}
LABELS = [("B12", pads["1"][0], pads["1"][1] - 2.3, 0), ("3V3", pads["20"][0], pads["20"][1] - 2.3, 0),
          ("5V", pads["40"][0], pads["40"][1] + 2.3, 0), ("VB", pads["21"][0], pads["21"][1] + 2.3, 0),
          ("USB DO MODULO", tx - 4.0, ty + MOD_ROWS / 2, 90), ("BLACK PILL F411", tx + 9.5 * MOD_PITCH, ty + MOD_ROWS / 2, 0)]
for text, x, y, ang in LABELS:
    if text in have:
        continue
    t = pcbnew.PCB_TEXT(b)
    t.SetText(text)
    t.SetLayer(pcbnew.B_SilkS)
    t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    t.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
    t.SetTextThickness(mm(0.15))
    t.SetMirrored(True)
    t.SetTextAngleDegrees(ang)
    b.Add(t)

b.Save(PCB)
print(f"ok: {len(PLACE)} componentes na faixa superior + módulo (orientação {ang}); pino 1 em ({pads['1'][0]:.2f},{pads['1'][1]:.2f}), "
      f"20 em ({pads['20'][0]:.2f},{pads['20'][1]:.2f}), 21 em ({pads['21'][0]:.2f},{pads['21'][1]:.2f}), 40 em ({pads['40'][0]:.2f},{pads['40'][1]:.2f})")
