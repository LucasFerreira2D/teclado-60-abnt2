"""Importa as folhas geradas pelo kbplacer (kb_out/) para o projeto.

kb_out/kb-key-matrix.kicad_sch -> matriz.kicad_sch
kb_out/kb-led-chain.kicad_sch  -> leds.kicad_sch  (VCC -> +5V, LEDIN -> RGB_DIN)

Os caminhos de instância são reescritos para o projeto "teclado" e para as folhas
"Matriz"/"LEDs" já presentes na raiz (teclado.kicad_sch).
"""
import re
from pathlib import Path

HW = Path(__file__).resolve().parent.parent
KB = HW / "kb_out"
ROOT = HW / "teclado.kicad_sch"
POWER_LIB = Path(r"C:\Program Files\KiCad\10.0\share\kicad\symbols\power.kicad_sym")


def balanced(txt, start):
    d = 0
    for j in range(start, len(txt)):
        if txt[j] == "(":
            d += 1
        elif txt[j] == ")":
            d -= 1
            if d == 0:
                return txt[start : j + 1]
    raise ValueError("unbalanced")


def sheet_uuid(root_txt, sheetfile):
    for m in re.finditer(r"\(sheet\b", root_txt):
        blk = balanced(root_txt, m.start())
        if f'"Sheetfile" "{sheetfile}"' in blk:
            return re.search(r'\(uuid "([^"]+)"', blk).group(1)
    raise KeyError(sheetfile)


def retarget(txt, root_uuid, sh_uuid):
    txt = re.sub(r'\(project "kb"\s*\(path "/[0-9a-f-]+/[0-9a-f-]+"', f'(project "teclado" (path "/{root_uuid}/{sh_uuid}"', txt)
    assert '(project "kb"' not in txt, "sobrou instância do projeto kb"
    return txt


def power_block(name):
    t = POWER_LIB.read_text(encoding="utf-8")
    i = t.find(f'\n\t(symbol "{name}"')
    return balanced(t, i + 2).replace(f'(symbol "{name}"', f'(symbol "power:{name}"', 1)


def main():
    root_txt = ROOT.read_text(encoding="utf-8")
    root_uuid = re.search(r'\(uuid "([^"]+)"', root_txt).group(1)

    m = (KB / "kb-key-matrix.kicad_sch").read_text(encoding="utf-8")
    m = retarget(m, root_uuid, sheet_uuid(root_txt, "matriz.kicad_sch"))
    (HW / "matriz.kicad_sch").write_text(m, encoding="utf-8")

    led = (KB / "kb-led-chain.kicad_sch").read_text(encoding="utf-8")
    led = retarget(led, root_uuid, sheet_uuid(root_txt, "leds.kicad_sch"))
    # VCC -> +5V: troca a definição do símbolo e as instâncias
    i = led.find('(symbol "power:VCC"')
    led = led[:i] + power_block("+5V") + led[i + len(balanced(led, i)) :]
    led = led.replace('(lib_id "power:VCC")', '(lib_id "power:+5V")')
    led = re.sub(r'\(property "Value" "VCC"', '(property "Value" "+5V"', led)
    led = led.replace('(global_label "LEDIN"', '(global_label "RGB_DIN"')
    assert "power:VCC" not in led
    (HW / "leds.kicad_sch").write_text(led, encoding="utf-8")
    print("ok: matriz.kicad_sch, leds.kicad_sch")


if __name__ == "__main__":
    main()
