"""Exporta route/teclado.dsn para o FreeRouting, sem os planos de GND.

Com os planos no DSN o FreeRouting trata F.Cu e B.Cu como camadas de plano e quase não roteia sinal
na F.Cu. Aqui as zonas saem só da cópia em memória (o .kicad_pcb não é alterado) e o GND vai para
uma classe própria ("GND_plane"), para poder ficar fora do roteamento (-inc GND_plane): ele é fechado
depois pelos planos + vias de costura (post_route.py / stitch_gnd.py).

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/export_dsn.py [--keep-tracks] [--power-width UM]
  --keep-tracks    mantém as trilhas atuais no DSN (continuar um roteamento)
  --power-width UM largura da classe Power (+5V/VBUS) no DSN, em um (padrão: a do projeto)
"""
import re
import sys
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parent.parent
PCB = str(HW / "teclado.kicad_pcb")
DSN = HW / "route" / "teclado.dsn"

b = pcbnew.LoadBoard(PCB)
# sem as trilhas antigas: o FreeRouting 2.2.3 estoura a pilha (PolylineTrace.combine) ao carregá-las,
# e elas foram feitas com a F.Cu tratada como plano. Roteia do zero.
zones = [z for z in b.Zones() if not z.GetIsRuleArea()]
tracks = [] if "--keep-tracks" in sys.argv else list(b.GetTracks())   # listas antes de remover: depois do Remove o SWIG perde os tipos
for o in zones + tracks:
    b.Remove(o)
# exportar direto depois de remover itens derruba o pcbnew (SWIG): salva numa cópia e recarrega
TMP = str(HW / "route" / "teclado_sem_trilhas.kicad_pcb")
b.Save(TMP)
b = pcbnew.LoadBoard(TMP)
print("DSN exportado:", pcbnew.ExportSpecctraDSN(b, str(DSN)), flush=True)

txt = DSN.read_text(encoding="utf-8")
m = re.search(r"\(class Power\b([^()]*)", txt)
nets = m.group(1).split()
assert "GND" in nets, nets
start = m.start()
depth, i = 0, start
while True:                      # fim do bloco (class Power ...)
    depth += {"(": 1, ")": -1}.get(txt[i], 0)
    i += 1
    if depth == 0:
        break
block = txt[start:i]
power = block.replace(m.group(0), "(class Power " + " ".join(n for n in nets if n != "GND") + "\n      ", 1)
gnd = block.replace(m.group(0), "(class GND_plane GND\n      ", 1)
if "--power-width" in sys.argv:
    w = sys.argv[sys.argv.index("--power-width") + 1]
    power = re.sub(r"\(width \d+\)", f"(width {w})", power)
    gnd = re.sub(r"\(width \d+\)", f"(width {w})", gnd)
DSN.write_text(txt[:start] + power + "\n    " + gnd + txt[i:], encoding="utf-8")
print("classes:", re.findall(r"\(class (\S+)", DSN.read_text(encoding="utf-8")), "| planos:", txt.count("(plane "))
