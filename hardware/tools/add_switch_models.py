"""Associa o modelo 3D do switch MX a cada footprint hotswap, para o teclado aparecer montado no
visualizador 3D do KiCad (Alt+3). O footprint só trazia o modelo do soquete (verso).

Uso: "C:\Program Files\KiCad\10.0\bin\python.exe" tools/add_switch_models.py
"""
from pathlib import Path

import pcbnew

PCB = str(Path(__file__).resolve().parent.parent / "teclado.kicad_pcb")
MODEL = "${KICAD6_3RD_PARTY}/3dmodels/com_github_perigoso_keyswitch-kicad-library/3d-library.3dshapes/SW_Cherry_MX_Plate.wrl"

b = pcbnew.LoadBoard(PCB)
n = 0
for f in b.GetFootprints():
    if not str(f.GetFPID().GetLibItemName()).startswith("SW_Hotswap_Kailh_MX"):
        continue
    if any(m.m_Filename == MODEL for m in f.Models()):
        continue
    m = pcbnew.FP_3DMODEL()
    m.m_Filename = MODEL
    f.Add3DModel(m)
    n += 1
b.Save(PCB)
print(f"modelo do switch adicionado em {n} teclas")
