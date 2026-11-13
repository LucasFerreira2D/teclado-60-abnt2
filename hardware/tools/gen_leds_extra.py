"""Gera leds_extra.kicad_sch: underglow (14x SK6812MINI no verso, virados para a mesa) e
LEDs laterais (12x SK6812SIDE-A, 6 por lado, iluminando os rasgos do case).

Cadeia: LEDOUT (último LED de tecla) -> LED101..LED114 (underglow) -> LED201..LED206 (lateral esquerda)
-> LED207..LED212 (lateral direita). O DOUT do último fica sem conexão.
"""
import gen_mcu_sheet as G

P, LL, GL, NC = G.P, G.LL, G.GL, G.NC
C603 = "Capacitor_SMD:C_0603_1608Metric"

chain = [f"LED{100 + i}" for i in range(1, 15)] + [f"LED{200 + i}" for i in range(1, 13)]
PARTS = []
for i, ref in enumerate(chain):
    din = GL + "LEDOUT" if i == 0 else LL + f"LX{i}"
    dout = LL + f"LX{i + 1}" if i + 1 < len(chain) else NC
    col, row = i % 7, i // 7
    x, y = 35.56 + col * 50.8, 60.96 + row * 55.88
    if ref.startswith("LED1"):
        PARTS.append((ref, "LED", "SK6812MINI", "SK6812MINI", None, x, y, 0,
                      {"DIN": din, "DOUT": dout, "VDD": P + "+5V", "VSS": P + "GND"}))
    else:
        PARTS.append((ref, "teclado", "SK6812SIDE-A", "SK6812SIDE-A", None, x, y, 0,
                      {"DIN": din, "DOUT": dout, "VDD": P + "+5V", "GND": P + "GND"}))
    cref = f"C{200 + i + 1}"
    PARTS.append((cref, "Device", "C", "100nF", C603, x + 20.32, y + 2.54, 0, {"1": P + "+5V", "2": P + "GND"}))

NOTES = [
    (30.48, 40.64, "Underglow: 14x SK6812MINI no verso, virados para a mesa (cadeia continua do LEDOUT das teclas)"),
    (30.48, 152.4, "Laterais: 12x SK6812SIDE-A na borda da placa, 6 por lado, iluminando os rasgos do case"),
]

if __name__ == "__main__":
    G.build(PARTS, G.HW / "leds_extra.kicad_sch", "leds_extra.kicad_sch", "LEDs extras: underglow e laterais", NOTES,
            pwr_base=500, uuid_ns="teclado/leds_extra/")
