"""Update PCB from Schematic sem GUI (KiCad fechado).

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/sync_pcb.py
- Exporta a netlist do esquemático (kicad-cli), adiciona à placa os footprints que faltam,
  vincula cada um ao símbolo (KIID path, igual ao F8) e atribui as redes aos pads.
- Footprints já presentes só têm valor/redes atualizados; posição é preservada.
- Novos entram empilhados por grupo dentro da faixa superior da placa.
"""
import re
import subprocess
from pathlib import Path

import pcbnew

HW = Path(__file__).resolve().parent.parent
SCH = HW / "teclado.kicad_sch"
PCB = HW / "teclado.kicad_pcb"
NET = HW / "teclado.net"
FPDIR = Path(r"C:\Program Files\KiCad\10.0\share\kicad\footprints")
CLI = r"C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"


def sexp(txt):
    tok = re.findall(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+', txt)
    st = [[]]
    for t in tok:
        if t == "(":
            st.append([])
        elif t == ")":
            x = st.pop()
            st[-1].append(x)
        else:
            st[-1].append(t[1:-1] if t.startswith('"') else t)
    return st[0][0]


def find(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def val(node, key, default=""):
    f = find(node, key)
    return f[0][1] if f and len(f[0]) > 1 else default


def lib_path(nick):
    t = HW / "fp-lib-table"
    if t.exists():
        m = re.search(r'\(name "' + re.escape(nick) + r'"\)\(type "KiCad"\)\(uri "([^"]+)"', t.read_text(encoding="utf-8"))
        if m:
            uri = m.group(1).replace("${KICAD10_3RD_PARTY}", str(Path.home() / "Documents" / "KiCad" / "10.0" / "3rdparty"))
            return uri.replace("${KIPRJMOD}", str(HW))
    return str(FPDIR / f"{nick}.pretty")


def main():
    subprocess.run([CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(NET), str(SCH)], check=True, capture_output=True)
    root = sexp(NET.read_text(encoding="utf-8"))
    comps = find(find(root, "components")[0], "comp")
    nets = find(find(root, "nets")[0], "net")

    pad_net = {}
    for n in nets:
        name = val(n, "name")
        for node in find(n, "node"):
            pad_net[(val(node, "ref"), val(node, "pin"))] = name

    board = pcbnew.LoadBoard(str(PCB))
    netinfo = {}
    for name in sorted(set(pad_net.values())):
        ni = board.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
        netinfo[name] = ni

    want = {val(c, "ref"): val(c, "footprint") for c in comps}
    removed = []
    for fp in list(board.GetFootprints()):
        ref = fp.GetReference()
        if fp.GetAttributes() & pcbnew.FP_BOARD_ONLY:      # furos de fixação etc.: não vêm do esquemático
            continue
        if want.get(ref) != fp.GetFPIDAsString():
            board.Remove(fp)
            removed.append(ref)
    if removed:
        print(f"removidos {len(removed)}: {' '.join(removed)}", flush=True)
        # depois de um Remove o SWIG perde os tipos das listas da placa: salva e continua em outro processo
        board.Save(str(PCB))
        import sys
        sys.exit(subprocess.call([sys.executable, __file__]))
    existing = {fp.GetReference(): fp for fp in board.GetFootprints()}
    bb = board.GetBoardEdgesBoundingBox()
    x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
    slot = {"x": x0 + 10, "y": y0 + 8}
    added, updated = [], []

    for c in sorted(comps, key=lambda c: (re.sub(r"\d", "", val(c, "ref")), int(re.sub(r"\D", "", val(c, "ref")) or 0))):
        ref, value, fpid = val(c, "ref"), val(c, "value"), val(c, "footprint")
        if not fpid:
            print(f"  sem footprint: {ref}")
            continue
        sheet = find(c, "sheetpath")[0]
        tstamps = val(sheet, "tstamps")
        uid = val(c, "tstamps") or val(c, "tstamp")
        path = pcbnew.KIID_PATH(f"{tstamps}{uid}")
        fp = existing.get(ref)
        if fp is None:
            lib, name = fpid.split(":", 1)
            fp = pcbnew.FootprintLoad(lib_path(lib), name)
            if fp is None:
                print(f"  footprint não encontrado: {ref} -> {fpid}")
                continue
            fp.SetReference(ref)
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(slot["x"]), pcbnew.FromMM(slot["y"])))
            board.Add(fp)
            w = pcbnew.ToMM(fp.GetBoundingBox(False).GetWidth())
            slot["x"] += max(w, 3) + 3
            if slot["x"] > x0 + 280:
                slot["x"], slot["y"] = x0 + 10, slot["y"] + 10
            added.append(ref)
        else:
            updated.append(ref)
        fp.SetValue(value)
        fp.SetPath(path)
        fp.SetFPIDAsString(fpid)
        for pad in fp.Pads():
            n = pad_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(netinfo[n])

    board.BuildConnectivity()
    board.Save(str(PCB))
    NET.unlink()
    print(f"adicionados {len(added)}: {' '.join(added)}")
    print(f"atualizados {len(updated)}")
    print(f"redes: {len(netinfo)}")


if __name__ == "__main__":
    main()
