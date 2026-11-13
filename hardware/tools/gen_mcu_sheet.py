"""Gera hardware/mcu.kicad_sch: módulo Black Pill (STM32F411) em soquete + USB-C + ESD + OLED + RGB + knob.

O chip, o cristal, o regulador de 3V3 e os botões BOOT0/NRST vêm no módulo (WeAct Black Pill V3.x).
A placa fornece +5V (USB-C -> fusível) nos pinos 5V do módulo e usa o 3V3 que sai dele.

Conexões por labels e símbolos de alimentação nos pinos (sem fios longos).
Rodar de novo sobrescreve a folha inteira.
"""
import math
import re
import uuid
from pathlib import Path

LIBDIR = Path(r"C:\Program Files\KiCad\10.0\share\kicad\symbols")
HW = Path(__file__).resolve().parent.parent
OUT = HW / "mcu.kicad_sch"
ROOT = HW / "teclado.kicad_sch"
PROJECT = "teclado"


UUID_NS = ["teclado/mcu/"]


def U(key=None):
    """UUID aleatório, ou fixo por chave (símbolos: mantém o vínculo com a placa entre regenerações)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, UUID_NS[0] + key)) if key else str(uuid.uuid4())


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


_libcache = {}


def lib_block(lib, name):
    if lib not in _libcache:
        path = HW / f"{lib}.kicad_sym" if (HW / f"{lib}.kicad_sym").exists() else LIBDIR / f"{lib}.kicad_sym"
        _libcache[lib] = path.read_text(encoding="utf-8")
    t = _libcache[lib]
    i = t.find(f'\n\t(symbol "{name}"')
    if i < 0:
        raise KeyError(f"{lib}:{name}")
    return balanced(t, i + 2)


def flat_block(lib, name):
    b = lib_block(lib, name)
    m = re.search(r'\(extends "([^"]+)"\)', b)
    if not m:
        return b
    parent = m.group(1)
    pb = flat_block(lib, parent)
    # child properties replace parent's
    props = {}
    for pm in re.finditer(r'\(property "([^"]+)"', b):
        props[pm.group(1)] = balanced(b, pm.start())
    out = pb
    for k, v in props.items():
        pm = re.search(r'\(property "' + re.escape(k) + '"', out)
        if pm:
            out = out[: pm.start()] + v + out[pm.start() + len(balanced(out, pm.start())) :]
    out = out.replace(f'(symbol "{parent}"', f'(symbol "{name}"', 1)
    out = re.sub(r'\(symbol "' + re.escape(parent) + r'_(\d+)_(\d+)"', lambda mm: f'(symbol "{name}_{mm.group(1)}_{mm.group(2)}"', out)
    return out


def pins_of(block):
    pins = []
    for m in re.finditer(r"\(pin (\w+) \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)", block):
        seg = balanced(block, m.start())
        num = re.search(r'\(number "([^"]*)"', seg).group(1)
        name = re.search(r'\(name "([^"]*)"', seg).group(1)
        pins.append(dict(num=num, name=name, etype=m.group(1), x=float(m.group(2)), y=float(m.group(3)), a=int(m.group(4))))
    return pins


def rot(x, y, r):
    c, s = round(math.cos(math.radians(r))), round(math.sin(math.radians(r)))
    return x * c - y * s, x * s + y * c


def g(v):
    return round(round(v / 1.27) * 1.27, 4)


# --------------------------------------------------------------------------- parts
R603 = "Resistor_SMD:R_0603_1608Metric"
C603 = "Capacitor_SMD:C_0603_1608Metric"
C805 = "Capacitor_SMD:C_0805_2012Metric"
P = "PWR:"  # power symbol
GL = "G:"  # global label
LL = "L:"  # local label
NC = "NC"

# Pinos do módulo fora da matriz:
#   PA10  USART1_RX do bootloader de fábrica: flutuando impede o DFU por USB -> pull-down R8
#   PA0   botão KEY do módulo (liga ao GND quando apertado): fica no encoder, que também fecha para o GND
#   PB2   BOOT1, com pull-down de 10k no módulo; PC13 é o LED do módulo; PC14/PC15 têm o cristal de 32 kHz
COLS = ["PB0", "PB1", "PB10", "PB12", "PB13", "PB14", "PB15", "PB9", "PA9", "PA15", "PB3", "PB4", "PB5", "PB8"]
ROWS = ["PA2", "PA3", "PA4", "PA5", "PA6", "PA7"]

mcu_nets = {
    "5V": P + "+5V", "3V3": P + "+3V3", "GND": P + "GND", "VBAT": NC, "NRST": NC,
    "PA11": LL + "USB_DM", "PA12": LL + "USB_DP",
    "PB6": LL + "I2C_SCL", "PB7": LL + "I2C_SDA", "PA0": LL + "ENC_A", "PA1": LL + "ENC_B", "PA8": LL + "RGB_3V3",
    "PA10": LL + "PA10_PD", "PB2": NC, "PC13": NC, "PC14": NC, "PC15": NC,
}
for i, p in enumerate(ROWS):
    mcu_nets[p] = GL + f"ROW{i}"
for i, p in enumerate(COLS):
    mcu_nets[p] = GL + f"COL{i}"

# (ref, lib, symbol, value, footprint, x, y, rot, nets{pin number or pin name: net})
PARTS = [
    # --- USB-C + ESD + fusível
    ("J1", "Connector", "USB_C_Receptacle_USB2.0_16P", "USB-C", "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12", 50.8, 80.01, 0,
     {"A4": P + "VBUS", "A1": P + "GND", "SH": P + "GND", "A5": LL + "CC1", "B5": LL + "CC2", "A6": LL + "USB_DP", "B6": LL + "USB_DP",
      "A7": LL + "USB_DM", "B7": LL + "USB_DM", "A8": NC, "B8": NC}),
    ("R1", "Device", "R", "5.1k", R603, 96.52, 66.04, 0, {"1": LL + "CC1", "2": P + "GND"}),
    ("R2", "Device", "R", "5.1k", R603, 106.68, 66.04, 0, {"1": LL + "CC2", "2": P + "GND"}),
    ("U2", "Power_Protection", "USBLC6-2SC6", "USBLC6-2SC6", None, 101.6, 104.14, 0,
     {"1": LL + "USB_DP", "6": LL + "USB_DP", "3": LL + "USB_DM", "4": LL + "USB_DM", "5": P + "VBUS", "2": P + "GND"}),
    ("F1", "Device", "Polyfuse", "500mA", "Fuse:Fuse_1206_3216Metric", 142.24, 50.8, 90, {"1": P + "VBUS", "2": P + "+5V"}),
    # --- módulo Black Pill (soquete DIP-40 largo, no verso)
    ("U1", "teclado", "BlackPill_F411", "BlackPill F411 (WeAct V3.x)", None, 203.2, 152.4, 0, mcu_nets),
    ("R8", "Device", "R", "10k", R603, 147.32, 210.82, 0, {"1": LL + "PA10_PD", "2": P + "GND"}),    # PA10 (USART1_RX do bootloader) nunca flutua
    # --- OLED I2C (módulo SSD1306 0.91": GND VCC SCL SDA)
    ("J3", "Connector_Generic", "Conn_01x04", "OLED_I2C", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", 302.26, 104.14, 0,
     {"1": P + "GND", "2": P + "+3V3", "3": LL + "I2C_SCL", "4": LL + "I2C_SDA"}),
    ("R4", "Device", "R", "4.7k", R603, 342.9, 99.06, 0, {"1": P + "+3V3", "2": LL + "I2C_SCL"}),
    ("R5", "Device", "R", "4.7k", R603, 360.68, 99.06, 0, {"1": P + "+3V3", "2": LL + "I2C_SDA"}),
    # --- RGB: buffer 3V3 -> 5V
    ("U4", "74xGxx", "74AHCT1G125", "74AHCT1G125", "Package_TO_SOT_SMD:SOT-23-5", 309.88, 152.4, 0,
     {"1": P + "GND", "2": LL + "RGB_3V3", "3": P + "GND", "5": P + "+5V", "4": LL + "RGB_5V"}),
    ("R6", "Device", "R", "330", R603, 350.52, 152.4, 90, {"1": LL + "RGB_5V", "2": GL + "RGB_DIN"}),
    ("C114", "Device", "C", "100nF", C603, 289.56, 172.72, 0, {"1": P + "+5V", "2": P + "GND"}),
    ("C115", "Device", "C", "22uF", C805, 330.2, 177.8, 0, {"1": P + "+5V", "2": P + "GND"}),
    # --- knob (EC11): A/B no MCU, clique na matriz (COL13 x ROW0)
    ("SW103", "Device", "RotaryEncoder_Switch", "EC11", "Rotary_Encoder:RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm", 307.34, 223.52, 0,
     {"A": LL + "ENC_A", "B": LL + "ENC_B", "C": P + "GND", "S1": GL + "COL13", "S2": LL + "ENC_SW"}),
    ("D101", "Diode", "1N4148W", "1N4148W", None, 350.52, 228.6, 0, {"2": LL + "ENC_SW", "1": GL + "ROW0"}),
]

POWER_BODY = {"GND": 270, "+3V3": 90, "+5V": 90, "VBUS": 90}  # direção do corpo (Y-up)


def build(parts, out, sheetfile, title, notes, flags=(), pwr_base=0, uuid_ns="teclado/mcu/"):
    """Gera uma folha inteira. parts no formato de PARTS; flags: [(rede, x, y)] para PWR_FLAG."""
    UUID_NS[0] = uuid_ns
    OUT = out
    PARTS = parts
    root_txt = ROOT.read_text(encoding="utf-8")
    root_uuid = re.search(r'\(uuid "([^"]+)"', root_txt).group(1)
    sheet_uuid = None
    for sm in re.finditer(r"\(sheet \(at", root_txt):
        blk = balanced(root_txt, sm.start())
        if f'"{sheetfile}"' in blk:
            sheet_uuid = re.search(r'\(uuid "([^"]+)"', blk).group(1)
    assert sheet_uuid, f"folha {sheetfile} não encontrada na raiz"
    inst_path = f"/{root_uuid}/{sheet_uuid}"
    old = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    m = re.search(r'\(uuid "([^"]+)"', old)
    sheet_file_uuid = m.group(1) if m else U()

    libsyms = {}
    body = []
    pwr_n = [pwr_base]
    used_pts = set()

    def lib(libname, sym):
        key = f"{libname}:{sym}"
        if key not in libsyms:
            b = flat_block(libname, sym)
            libsyms[key] = b.replace(f'(symbol "{sym}"', f'(symbol "{key}"', 1)
        return libsyms[key]

    def prop(b, name, val, x, y, r, force_hide=False):
        """Campo posicionado como o KiCad faz: posição da biblioteca, girada com o símbolo."""
        m = re.search(r'\(property "' + re.escape(name) + r'" "[^"]*"\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\)', b)
        if m:
            lx, ly, la = float(m.group(1)), float(m.group(2)), float(m.group(3))
            eff_i = b.find("(effects", m.end())
            eff = balanced(b, eff_i)
        else:
            lx, ly, la, eff = 0.0, 0.0, 0.0, "(effects (font (size 1.27 1.27)) (hide yes))"
        if force_hide and "(hide yes)" not in eff:
            eff = eff[:-1] + " (hide yes))"
        dx, dy = rot(lx, ly, r)
        ang = (la + r) % 180
        return f'(property "{name}" "{val}" (at {round(x + dx, 4)} {round(y - dy, 4)} {ang:g}) {eff})'

    def place(libname, sym, ref, value, fp, x, y, r, extra_props=(), hide_ref=False, in_bom=True):
        b = lib(libname, sym)
        pins = pins_of(b)
        fpv = fp
        if fpv is None:
            fm = re.search(r'\(property "Footprint" "([^"]*)"', b)
            fpv = fm.group(1) if fm else ""
        bom = "yes" if in_bom else "no"
        s = [f'(symbol (lib_id "{libname}:{sym}") (at {x} {y} {r}) (unit 1) (exclude_from_sim no) (in_bom {bom}) (on_board {bom}) (dnp no) (uuid "{U(ref)}")',
             prop(b, "Reference", ref, x, y, r, force_hide=hide_ref),
             prop(b, "Value", value, x, y, r),
             prop(b, "Footprint", fpv, x, y, r, force_hide=True),
             prop(b, "Datasheet", "", x, y, r, force_hide=True)]
        s += list(extra_props)
        seen = set()
        for p in pins:
            if p["num"] in seen:
                continue
            seen.add(p["num"])
            s.append(f'(pin "{p["num"]}" (uuid "{U(ref + "." + p["num"])}"))')
        s.append(f'(instances (project "{PROJECT}" (path "{inst_path}" (reference "{ref}") (unit 1))))')
        s.append(")")
        body.append("\n".join(s))
        out = []
        for p in pins:
            dx, dy = rot(p["x"], p["y"], r)
            exit_dir = (p["a"] + 180 + r) % 360
            out.append(dict(p, wx=round(x + dx, 4), wy=round(y - dy, 4), exit=exit_dir))
        return out

    def power(net, x, y, exit_dir):
        key = (net, x, y)
        if key in used_pts:
            return
        used_pts.add(key)
        r = (exit_dir - POWER_BODY[net]) % 360
        pwr_n[0] += 1
        place("power", net, f"#PWR{pwr_n[0]:03d}", net, "", x, y, r, hide_ref=True, in_bom=False)

    def wire(x1, y1, x2, y2):
        body.append(f'(wire (pts (xy {round(x1, 4)} {round(y1, 4)}) (xy {round(x2, 4)} {round(y2, 4)})) (stroke (width 0) (type default)) (uuid "{U()}"))')

    def junction(x, y):
        body.append(f'(junction (at {round(x, 4)} {round(y, 4)}) (diameter 0) (color 0 0 0 0) (uuid "{U()}"))')

    STEP = {0: (1, 0), 90: (0, -1), 180: (-1, 0), 270: (0, 1)}  # direção de saída -> passo na tela (Y para baixo)

    def power_pins(reqs, stub=2.54):
        """reqs: [(net, x, y, exit)] de um componente. Stub em cada pino; pinos da mesma rede e lado viram um barramento."""
        groups = {}
        for net, x, y, e in dict.fromkeys(reqs):
            groups.setdefault((net, e), []).append((x, y))
        for (net, e), pts in groups.items():
            sx, sy = STEP[e]
            ends = []
            for x, y in pts:
                ex, ey = round(x + sx * stub, 4), round(y + sy * stub, 4)
                wire(x, y, ex, ey)
                ends.append((ex, ey))
            # ordenar ao longo do eixo perpendicular à saída
            ends.sort(key=lambda p: (p[1], p[0]) if sx else (p[0], p[1]))
            for a, c in zip(ends, ends[1:]):
                wire(a[0], a[1], c[0], c[1])
            for p in ends[1:-1]:
                junction(*p)
            power(net, ends[0][0], ends[0][1], e)

    def label(kind, name, x, y, exit_dir):
        key = (kind, name, x, y)
        if key in used_pts:
            return
        used_pts.add(key)
        just = "left" if exit_dir in (0, 90) else "right"
        if kind == "G":
            body.append(f'(global_label "{name}" (shape bidirectional) (at {x} {y} {exit_dir}) (fields_autoplaced yes) '
                        f'(effects (font (size 1.27 1.27)) (justify {just})) (uuid "{U()}") '
                        f'(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes))))')
        else:
            body.append(f'(label "{name}" (at {x} {y} {exit_dir}) (effects (font (size 1.27 1.27)) (justify {just} bottom)) (uuid "{U()}"))')

    def noconn(x, y):
        if ("NC", x, y) in used_pts:
            return
        used_pts.add(("NC", x, y))
        body.append(f'(no_connect (at {x} {y}) (uuid "{U()}"))')

    unconnected = []
    for ref, libname, sym, value, fp, x, y, r, nets in PARTS:
        pins = place(libname, sym, ref, value, fp, g(x), g(y), r)
        preqs = []
        for p in pins:
            net = nets.get(p["num"], nets.get(p["name"]))
            if net is None:
                # pinos empilhados com o mesmo nome (VBUS/GND do USB-C) herdam a rede do irmão
                sib = [nets[q["num"]] for q in pins if q["name"] == p["name"] and q["num"] in nets]
                net = sib[0] if sib else None
            if net is None:
                unconnected.append(f"{ref}.{p['num']}({p['name']})")
                continue
            if net == NC:
                noconn(p["wx"], p["wy"])
            elif net.startswith(P):
                preqs.append((net[len(P):], p["wx"], p["wy"], p["exit"]))
            elif net.startswith(GL):
                label("G", net[len(GL):], p["wx"], p["wy"], p["exit"])
            else:
                label("L", net[len(LL):], p["wx"], p["wy"], p["exit"])
        power_pins(preqs)

    # PWR_FLAGs: VBUS (vem do conector), +5V (sai do fusível, pino passivo) e GND.
    # Flag e símbolo lado a lado, ligados por um fio, para os textos não se sobreporem.
    for i, (net, x, y) in enumerate(flags):
        fx = x + 7.62
        place("power", "PWR_FLAG", f"#FLG{pwr_base + i + 1:02d}", "PWR_FLAG", "", fx, y, 180 if net == "GND" else 0, hide_ref=True, in_bom=False)
        wire(x, y, fx, y)
        power(net, x, y, 270 if net == "GND" else 90)

    # textos de bloco
    for x, y, t in notes:
        body.append(f'(text "{t}" (exclude_from_sim no) (at {x} {y} 0) (effects (font (size 2 2) (thickness 0.4) bold) (justify left bottom)) (uuid "{U()}"))')

    libs = "\n".join(libsyms.values())
    txt = f"""(kicad_sch
	(version 20250610)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "{sheet_file_uuid}")
	(paper "A3")
	(title_block
		(title "{title}")
		(date "2026-11-11")
		(rev "0.1")
	)
	(lib_symbols
{libs}
	)
{chr(10).join(body)}
	(embedded_fonts no)
)
"""
    OUT.write_text(txt, encoding="utf-8")
    print(f"ok: {len(PARTS)} componentes, {pwr_n[0] - pwr_base} simbolos de alimentacao -> {OUT}")
    if unconnected:
        print("SEM REDE:", ", ".join(unconnected))


MCU_NOTES = [
    (30.48, 40.64, "USB-C, ESD e fusível"), (160.02, 111.76, "Módulo Black Pill STM32F411 (em soquete, no verso)"),
    (129.54, 198.12, "Pull-down PA10 (DFU)"),
    (284.48, 88.9, "OLED I2C"), (284.48, 134.62, "RGB: buffer 3V3 -> 5V (SK6812)"),
    (284.48, 203.2, "Knob EC11: A/B no MCU, clique na matriz (ROW0 x COL13)"),
]


def main():
    # PWR_FLAGs: VBUS (vem do conector), +5V (sai do fusível, pino passivo), GND e +3V3 (sai do módulo, pino passivo)
    build(PARTS, OUT, "mcu.kicad_sch", "MCU, USB e alimentacao", MCU_NOTES,
          flags=[("VBUS", 30.48, 30.48), ("+5V", 50.8, 30.48), ("GND", 71.12, 30.48), ("+3V3", 91.44, 30.48)])


if __name__ == "__main__":
    main()
