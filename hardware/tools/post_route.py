"""Importa o roteamento do FreeRouting (route/teclado.ses) e cria os planos de GND.

- Remove trilhas/vias antigas antes de importar (o SES traz o roteamento completo).
- GND em F.Cu e B.Cu cobrindo a placa (0,3 mm da borda), alívio térmico nos pads, preenchido.
Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/post_route.py [--no-import]
"""
import sys
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parent.parent
PCB = str(HW / "teclado.kicad_pcb")
SES = str(HW / "route" / "teclado.ses")
mm, to = pcbnew.FromMM, pcbnew.ToMM

b = pcbnew.LoadBoard(PCB)

if "--no-import" not in sys.argv:
    for t in list(b.GetTracks()):
        b.Remove(t)
    ok = pcbnew.ImportSpecctraSES(b, SES)
    print("SES importado:", ok)
    # depois do import os objetos SWIG da placa ficam inválidos: salva e recarrega
    b.Save(PCB)
    # o módulo pcbnew não se recupera no mesmo processo: os planos são feitos numa segunda execução
    import subprocess
    sys.exit(subprocess.call([sys.executable, __file__, "--no-import"]))

# planos de GND: cria os que faltam e preenche todos. Não remove os existentes: depois de um
# b.Remove() o SWIG perde os tipos (Outline() volta SwigPyObject) e não dá para criar zona no mesmo processo.
# contorno a partir dos segmentos de Edge.Cuts (GetBoardEdgesBoundingBox falha no SWIG com a placa roteada)
pts = [p for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts for p in (d.GetStart(), d.GetEnd())]
gnd = b.FindNet("GND")
have = {z.GetLayer() for z in b.Zones() if z.GetNetname() == "GND" and not z.GetIsRuleArea()}
x0, y0, x1, y1 = min(p.x for p in pts), min(p.y for p in pts), max(p.x for p in pts), max(p.y for p in pts)
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    if layer in have:
        continue
    z = pcbnew.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(gnd)
    o = z.Outline()
    o.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        o.Append(x, y)
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    z.SetAssignedPriority(0)
    z.SetZoneName(f"GND_{'F' if layer == pcbnew.F_Cu else 'B'}")
    b.Add(z)

pcbnew.ZONE_FILLER(b).Fill(b.Zones())
b.Save(PCB)
tracks = [t for t in b.GetTracks()]
vias = [t for t in tracks if isinstance(t, pcbnew.PCB_VIA)]
length = sum(to(t.GetLength()) for t in tracks if not isinstance(t, pcbnew.PCB_VIA))
print(f"trilhas: {len(tracks) - len(vias)} ({length / 1000:.2f} m), vias: {len(vias)}, zonas GND: F/B preenchidas")
