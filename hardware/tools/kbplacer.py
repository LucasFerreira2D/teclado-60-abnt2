"""Roda o kbplacer (plugin instalado no KiCad 10) com o Python do KiCad e as dependências locais (.pydeps).
Uso: "C:\Program Files\KiCad\10.0\bin\python.exe" tools/kbplacer.py <args do kbplacer>
"""
import os, runpy, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".pydeps"))
sys.path.insert(0, os.path.expanduser(r"~\Documents\KiCad\10.0\3rdparty\plugins"))
sys.argv[0] = "kbplacer"
runpy.run_module("com_github_adamws_kicad-kbplacer", run_name="__main__", alter_sys=True)
