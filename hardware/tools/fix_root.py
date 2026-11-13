"""Normaliza as folhas da raiz depois do add_sheet_symbol do MCP (kcaa 0.2.10):
"Sheet name"/"Sheet file" -> "Sheetname"/"Sheetfile", caminho de instância = raiz, páginas sequenciais."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "teclado.kicad_sch"
s = ROOT.read_text(encoding="utf-8")
root = re.search(r'\(uuid "([^"]+)"', s).group(1)
s = s.replace('(property "Sheet name"', '(property "Sheetname"').replace('(property "Sheet file"', '(property "Sheetfile"')
page = [1]


def fix(m):
    page[0] += 1
    return f'(instances (project "teclado" (path "/{root}" (page "{page[0]}"))))'


s = re.sub(r'\(instances \(project "teclado" \(path "/[0-9a-f-]+" \(page "\d+"\)\)\)\)', fix, s)
ROOT.write_text(s, encoding="utf-8")
print("folhas:", re.findall(r'"Sheetfile" "([^"]+)"', s), "paginas 2 ..", page[0])
