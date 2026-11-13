"""Fecha as ligações que o FreeRouting deixou abertas.

Lê os pares abertos de um JSON (tools/open_pairs.py) e roteia cada um numa grade de 0,05 mm
(onda de Lee em 2 camadas + vias, depois alisamento por linha de visada).

Quando um par não tem caminho (pino cercado pelas trilhas dos vizinhos), tenta de novo ignorando as
trilhas de outras redes dentro de um círculo pequeno em volta da ponta presa (1 a 4 mm). As trilhas
atravessadas são arrancadas (rip-up) e as redes delas são roteadas de novo em seguida. Rede já
roteada por este script fica protegida e não é arrancada de novo, então o processo termina.

O GND fica de fora da lista de pares: é fechado pelos planos + vias de costura (stitch_gnd.py).
Depois rode post_route.py --no-import para preencher os planos.

Uso: "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/route_rest.py <pares.json> [--dry] [--no-rip]
         [--w-sig MM] [--w-pwr MM] [--gnd] [--tight x0,y0,x1,y1]
         [--radii r1,r2,...] [--via-delay N] [--margin MM] [--slack MM]
  --gnd  aceita pares de GND (os que o gnd_islands.py não resolve com via)
"""
import collections
import json
import math
import re
import sys
import time
from pathlib import Path

import numpy as np
import pcbnew

HW = Path(__file__).resolve().parent.parent
PCB = str(HW / "teclado.kicad_pcb")
mm, to = pcbnew.FromMM, pcbnew.ToMM

G = 0.05                         # passo da grade (mm)
CLR = 0.2                        # isolamento entre redes
SLACK = 0.04                     # erro de rasterização
if "--slack" in sys.argv:
    SLACK = float(sys.argv[sys.argv.index("--slack") + 1])
W_SIG, W_PWR = 0.2, 0.3          # largura das trilhas novas
for _k in ("--w-sig", "--w-pwr"):
    if _k in sys.argv:
        _v = float(sys.argv[sys.argv.index(_k) + 1])
        W_SIG, W_PWR = (_v, W_PWR) if _k == "--w-sig" else (W_SIG, _v)
PWR = {"+5V", "VBUS", "+3V3", "GND"}
VIA_D, VIA_DRILL = 0.6, 0.3
VIA_DELAY = 40                   # custo da via, em passos da grade (2 mm)
MARGIN = 25.0                    # janela de busca em volta do par (mm)
if "--margin" in sys.argv:                # janela maior: acha desvios longos (mais lento)
    MARGIN = float(sys.argv[sys.argv.index("--margin") + 1])
EDGE = 0.5                       # cobre até a borda da placa
MH_R = 2.25                      # apoio do espaçador nos furos M2
RADII = () if "--no-rip" in sys.argv else (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)
if "--radii" in sys.argv:                 # raios de rip-up a tentar, em ordem
    RADII = tuple(float(v) for v in sys.argv[sys.argv.index("--radii") + 1].split(","))
if "--via-delay" in sys.argv:             # custo da via em passos da grade (muda o caminho escolhido)
    VIA_DELAY = int(sys.argv[sys.argv.index("--via-delay") + 1])
# --tight x0,y0,x1,y1: área de regra do fanout (em volta do STM32), onde vale trilha 0,15 / isolamento 0,15.
# O roteador usa a regra apertada 0,5 mm para dentro da caixa e troca a largura 0,3 mm para dentro,
# para a ponta arredondada da trilha larga não entrar na parte validada com a regra apertada.
TIGHT = None
T_W, T_CLR = 0.15, 0.15
if "--tight" in sys.argv:
    TIGHT = tuple(float(v) for v in sys.argv[sys.argv.index("--tight") + 1].split(","))


def in_tight(x, y):
    return bool(TIGHT) and TIGHT[0] + 0.5 <= x <= TIGHT[2] - 0.5 and TIGHT[1] + 0.5 <= y <= TIGHT[3] - 0.5


def split_tight(segs, hw):
    """(l, p1, p2) -> (l, p1, p2, meia largura): dentro da área apertada a trilha afina."""
    if not TIGHT:
        return [(l, p1, p2, hw) for l, p1, p2 in segs]
    x0, y0, x1, y1 = TIGHT[0] + 0.3, TIGHT[1] + 0.3, TIGHT[2] - 0.3, TIGHT[3] - 0.3
    out = []
    for l, p1, p2 in segs:
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        t0, t1, ok = 0.0, 1.0, True
        for p, q in ((-dx, p1[0] - x0), (dx, x1 - p1[0]), (-dy, p1[1] - y0), (dy, y1 - p1[1])):
            if p == 0:
                ok = ok and q >= 0
            elif p < 0:
                t0 = max(t0, q / p)
            else:
                t1 = min(t1, q / p)
        if not ok or t0 >= t1:
            out.append((l, p1, p2, hw))
            continue
        a, c = (p1[0] + dx * t0, p1[1] + dy * t0), (p1[0] + dx * t1, p1[1] + dy * t1)
        if t0 > 1e-9:
            out.append((l, p1, a, hw))
        out.append((l, a, c, min(hw, T_W / 2)))
        if t1 < 1 - 1e-9:
            out.append((l, c, p2, hw))
    return out

b = pcbnew.LoadBoard(PCB)
edge = [p for d in b.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts for p in (d.GetStart(), d.GetEnd())]
BX0, BY0 = to(min(p.x for p in edge)), to(min(p.y for p in edge))
BX1, BY1 = to(max(p.x for p in edge)), to(max(p.y for p in edge))
W, H = int(round((BX1 - BX0) / G)) + 1, int(round((BY1 - BY0) / G)) + 1
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)

pad_at = np.zeros((2, H, W), np.int16)      # pads e obstáculos fixos: -1 sem rede, n = código da rede
trk_at = np.zeros((2, H, W), np.int16)      # trilhas e vias: n = código da rede
core_pad = np.zeros((2, H, W), bool)        # miolo do cobre: onde uma trilha nova pode começar/terminar
core_trk = np.zeros((2, H, W), bool)
thru_pad = np.zeros((H, W), bool)           # pads PTH e vias ligam as duas camadas
thru_via = np.zeros((H, W), bool)
padmask = np.zeros((H, W), bool)            # qualquer pad (para não pôr via em pad)


def cx(x):
    return (x - BX0) / G


def cy(y):
    return (y - BY0) / G


def win(x0, y0, x1, y1):
    i0, i1 = max(0, int(math.floor(cx(x0)))), min(W, int(math.ceil(cx(x1))) + 1)
    j0, j1 = max(0, int(math.floor(cy(y0)))), min(H, int(math.ceil(cy(y1))) + 1)
    return j0, j1, i0, i1


def stamp_rect(arr, x0, y0, x1, y1, val):
    j0, j1, i0, i1 = win(x0, y0, x1, y1)
    js = np.arange(j0, j1)[:, None] * G + BY0
    is_ = np.arange(i0, i1)[None, :] * G + BX0
    m = (js >= y0) & (js <= y1) & (is_ >= x0) & (is_ <= x1)
    arr[j0:j1, i0:i1][m] = val


def stamp_seg(arr, x1, y1, x2, y2, r, val):
    j0, j1, i0, i1 = win(min(x1, x2) - r, min(y1, y2) - r, max(x1, x2) + r, max(y1, y2) + r)
    if j1 <= j0 or i1 <= i0:
        return
    ys = np.arange(j0, j1)[:, None] * G + BY0
    xs = np.arange(i0, i1)[None, :] * G + BX0
    dx, dy = x2 - x1, y2 - y1
    L = dx * dx + dy * dy
    t = np.zeros((j1 - j0, i1 - i0)) if L == 0 else np.clip(((xs - x1) * dx + (ys - y1) * dy) / L, 0, 1)
    d2 = (xs - x1 - t * dx) ** 2 + (ys - y1 - t * dy) ** 2
    arr[j0:j1, i0:i1][d2 <= r * r] = val


def stamp_disc(arr, x, y, r, val):
    stamp_seg(arr, x, y, x, y, r, val)


def bb(o):
    q = o.GetBoundingBox()
    return to(q.GetLeft()), to(q.GetTop()), to(q.GetRight()), to(q.GetBottom())


def pt_seg(px, py, p1, p2):
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - p1[0]) * dx + (py - p1[1]) * dy) / L))
    return math.hypot(px - p1[0] - t * dx, py - p1[1] - t * dy)


class Item:
    """Trilha (kind 'seg') ou via do modelo; obj é o objeto do pcbnew."""
    __slots__ = ("kind", "net", "l", "p1", "p2", "hw", "obj", "alive")

    def __init__(self, kind, net, l, p1, p2, hw, obj):
        self.kind, self.net, self.l, self.p1, self.p2, self.hw, self.obj, self.alive = kind, net, l, p1, p2, hw, obj, True

    def bbox(self):
        return (min(self.p1[0], self.p2[0]) - self.hw, min(self.p1[1], self.p2[1]) - self.hw,
                max(self.p1[0], self.p2[0]) + self.hw, max(self.p1[1], self.p2[1]) + self.hw)

    def stamp(self):
        if self.kind == "via":
            for l in (0, 1):
                stamp_disc(trk_at[l], *self.p1, self.hw, self.net)
                stamp_disc(core_trk[l], *self.p1, 0.15, True)
            stamp_disc(thru_via, *self.p1, 0.15, True)
        else:
            stamp_seg(trk_at[self.l], *self.p1, *self.p2, self.hw, self.net)
            stamp_seg(core_trk[self.l], *self.p1, *self.p2, max(0.04, self.hw * 0.5), True)


items = []
by_net = collections.defaultdict(list)


def add_item(it):
    items.append(it)
    by_net[it.net].append(it)
    it.stamp()


# ---------------------------------------------------------------- rasterização da placa
for f in b.GetFootprints():
    name = str(f.GetFPID().GetLibItemName())
    for g in f.GraphicalItems():
        if g.GetLayer() == pcbnew.Edge_Cuts:               # recorte dos LEDs
            for l in (0, 1):
                stamp_rect(pad_at[l], *bb(g), -1)
    for p in f.Pads():
        x0, y0, x1, y1 = bb(p)
        pc = p.GetPosition()
        px, py = to(pc.x), to(pc.y)
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            r = MH_R if name.startswith("MountingHole") else max(to(p.GetDrillSize().x), to(p.GetDrillSize().y), x1 - x0, y1 - y0) / 2 + 0.1
            for l in (0, 1):
                stamp_disc(pad_at[l], px, py, r, -1)
            continue
        code = p.GetNetCode() or -1
        rc = max(0.1, min(x1 - x0, y1 - y0) / 2 - 0.05)
        stamp_rect(padmask, x0, y0, x1, y1, True)
        both = p.IsOnLayer(pcbnew.F_Cu) and p.IsOnLayer(pcbnew.B_Cu)
        for l, lay in enumerate(LAYERS):
            if p.IsOnLayer(lay):
                stamp_rect(pad_at[l], x0, y0, x1, y1, code)
                stamp_disc(core_pad[l], px, py, rc, True)
        if both:
            stamp_disc(thru_pad, px, py, rc, True)

for t in b.GetTracks():
    code = t.GetNetCode() or -1
    if isinstance(t, pcbnew.PCB_VIA):
        p = t.GetPosition()
        q = (to(p.x), to(p.y))
        add_item(Item("via", code, -1, q, q, to(t.GetWidth(pcbnew.F_Cu)) / 2, t))
    else:
        s, e = t.GetStart(), t.GetEnd()
        add_item(Item("seg", code, 0 if t.GetLayer() == pcbnew.F_Cu else 1, (to(s.x), to(s.y)), (to(e.x), to(e.y)),
                      to(t.GetWidth()) / 2, t))

# faixa da borda: com a dilatação (largura/2 + CLR) o cobre fica a EDGE da borda
band = int(round((EDGE - CLR) / G))
for l in (0, 1):
    pad_at[l, :band + 1, :] = -1
    pad_at[l, -band - 1:, :] = -1
    pad_at[l, :, :band + 1] = -1
    pad_at[l, :, -band - 1:] = -1


def rebuild(x0, y0, x1, y1):
    """Refaz o raster de trilhas/vias numa região (depois de arrancar trilhas)."""
    j0, j1, i0, i1 = win(x0, y0, x1, y1)
    trk_at[:, j0:j1, i0:i1] = 0
    core_trk[:, j0:j1, i0:i1] = False
    thru_via[j0:j1, i0:i1] = False
    for it in items:
        if it.alive:
            q = it.bbox()
            if q[0] <= x1 and q[2] >= x0 and q[1] <= y1 and q[3] >= y0:
                it.stamp()


def dilate(a, r):
    """Dilatação por disco de raio r (mm), por somas acumuladas nas linhas."""
    h, w = a.shape
    c = np.zeros((h, w + 1), np.int32)
    np.cumsum(a, axis=1, out=c[:, 1:])
    out = np.zeros_like(a)
    rc = r / G
    R = int(math.floor(rc))
    ar = np.arange(w)
    for dy in range(-R, R + 1):
        k = int(math.floor(math.sqrt(rc * rc - dy * dy)))
        hrow = (c[:, np.clip(ar + k + 1, 0, w)] - c[:, np.clip(ar - k, 0, w)]) > 0
        if dy >= 0:
            out[dy:, :] |= hrow[:h - dy, :]
        else:
            out[:h + dy, :] |= hrow[-dy:, :]
    return out


def flood(own, thr, seeds):
    """Componente conexa do cobre da rede (2 camadas ligadas em vias/PTH) a partir das sementes."""
    seen = np.zeros_like(own)
    dq = collections.deque()
    for s in seeds:
        if own[s] and not seen[s]:
            seen[s] = True
            dq.append(s)
    h, w = own.shape[1:]
    while dq:
        l, j, i = dq.popleft()
        for n in ((l, j + 1, i), (l, j - 1, i), (l, j, i + 1), (l, j, i - 1), (1 - l, j, i)):
            if n[0] != l and not thr[j, i]:
                continue
            if 0 <= n[1] < h and 0 <= n[2] < w and own[n] and not seen[n]:
                seen[n] = True
                dq.append(n)
    return seen


def seeds_at(own, x, y, j0, i0, layers=(0, 1)):
    out = []
    r = int(round(0.35 / G))
    jc, ic = int(round(cy(y))) - j0, int(round(cx(x))) - i0
    for l in layers:
        for j in range(max(0, jc - r), min(own.shape[1], jc + r + 1)):
            for i in range(max(0, ic - r), min(own.shape[2], ic + r + 1)):
                if own[l, j, i]:
                    out.append((l, j, i))
    return out


def eroded(fr):
    er = fr.copy()
    er[1:-1, 1:-1] = (fr[1:-1, 1:-1] & fr[:-2, 1:-1] & fr[2:, 1:-1] & fr[1:-1, :-2] & fr[1:-1, 2:]
                      & fr[:-2, :-2] & fr[:-2, 2:] & fr[2:, :-2] & fr[2:, 2:])
    return er


def los(fr, er, a, c):
    # linha inclinada passa entre os centros das células: confere na máscara encolhida 1 célula
    if a[0] != c[0] and a[1] != c[1]:
        fr = er
    n = max(abs(c[0] - a[0]), abs(c[1] - a[1])) * 2 + 1
    js = np.rint(np.linspace(a[0], c[0], n)).astype(int)
    is_ = np.rint(np.linspace(a[1], c[1], n)).astype(int)
    return bool(fr[js, is_].all())


def smooth(fr, pts):
    er = eroded(fr)
    out, a, n = [pts[0]], 0, len(pts)
    while a < n - 1:
        c = a + 1
        step = 64
        while step:                      # avança enquanto houver linha de visada
            while c + step < n and los(fr, er, pts[a], pts[c + step]):
                c += step
            step //= 2
        out.append(pts[c])
        a = c
    return out


def route(code, hw, pa, pb, zones=(), protected=(), direct=True, la=(0, 1), lb=(0, 1)):
    """Liga o cobre em pa ao cobre em pb. Devolve (trilhas, vias, hw) em mm ou um texto de erro.
    zones: círculos (x, y, r) onde trilhas de redes não protegidas são ignoradas (serão arrancadas)."""
    j0, j1, i0, i1 = win(min(pa[0], pb[0]) - MARGIN, min(pa[1], pb[1]) - MARGIN,
                         max(pa[0], pb[0]) + MARGIN, max(pa[1], pb[1]) + MARGIN)
    P, T = pad_at[:, j0:j1, i0:i1], trk_at[:, j0:j1, i0:i1]
    thr = thru_pad[j0:j1, i0:i1] | thru_via[j0:j1, i0:i1]
    h, w = P.shape[1:]
    own = (P == code) | (T == code)
    otrk = (T != 0) & (T != code)
    if zones:
        ys = (np.arange(j0, j1) * G + BY0)[:, None]
        xs = (np.arange(i0, i1) * G + BX0)[None, :]
        Z = np.zeros((h, w), bool)
        for zx, zy, zr in zones:
            Z |= (xs - zx) ** 2 + (ys - zy) ** 2 <= zr * zr
        otrk &= ~(Z[None] & ~np.isin(T, list(protected)))
    other = ((P != 0) & (P != code)) | otrk
    sa = seeds_at(own, pa[0], pa[1], j0, i0, la)
    sb = seeds_at(own, pb[0], pb[1], j0, i0, lb)
    if not sa or not sb:
        return "sem cobre da rede no ponto"
    M = None
    if TIGHT:
        ys = (np.arange(j0, j1) * G + BY0)[:, None]
        xs = (np.arange(i0, i1) * G + BX0)[None, :]
        M = (xs >= TIGHT[0] + 0.5) & (xs <= TIGHT[2] - 0.5) & (ys >= TIGHT[1] + 0.5) & (ys <= TIGHT[3] - 0.5)
        if not M.any():
            M = None
    free = np.stack([~dilate(other[l], hw + CLR + SLACK) for l in (0, 1)])
    if M is not None:
        free |= np.stack([~dilate(other[l], T_W / 2 + T_CLR + SLACK) for l in (0, 1)]) & M[None]
    free |= own
    free[:, 0, :] = free[:, -1, :] = False
    free[:, :, 0] = free[:, :, -1] = False
    ca = flood(own, thr, sa)
    if any(ca[s] for s in sb):
        if direct:
            # cobre encostado na grade, mas o KiCad não considera ligado: trilha direta entre os dois pontos
            ja, ia = int(round(cy(pa[1]))) - j0, int(round(cx(pa[0]))) - i0
            jb, ib = int(round(cy(pb[1]))) - j0, int(round(cx(pb[0]))) - i0
            for l in (0, 1):
                if own[l, ja, ia] and own[l, jb, ib] and los(free[l], eroded(free[l]), (ja, ia), (jb, ib)):
                    return split_tight([(l, pa, pb)], hw), [], hw
            # cobre da rede nas duas camadas, um em cima do outro, sem via: põe a via
            both = own[0] & own[1] & ~dilate(other[0] | other[1], VIA_D / 2 + CLR + SLACK)
            both &= ~dilate(padmask[j0:j1, i0:i1], VIA_D / 2 + 0.1)
            cand = [(math.hypot(j - jb, i - ib), j, i) for j, i in zip(*np.nonzero(both[max(0, jb - 12):jb + 13, max(0, ib - 12):ib + 13]))]
            if cand:
                _, j, i = min(cand)
                j, i = j + max(0, jb - 12), i + max(0, ib - 12)
                return [], [(BX0 + (i0 + i) * G, BY0 + (j0 + j) * G)], hw
        return "já ligado"
    cb = flood(own, thr, sb)
    via_ok = ~dilate(other[0] | other[1], VIA_D / 2 + CLR + SLACK)
    if M is not None:
        via_ok |= ~dilate(other[0] | other[1], VIA_D / 2 + T_CLR + SLACK) & M
    via_ok &= ~dilate(padmask[j0:j1, i0:i1], VIA_D / 2 + 0.1)
    via_ok &= free[0] & free[1]
    cr = core_pad[:, j0:j1, i0:i1] | core_trk[:, j0:j1, i0:i1]
    src = ca & cr & free
    tgt = cb & cr & free
    if not src.any() or not tgt.any():
        return "ponta sem acesso"
    hwc = h * w
    freef, tgtf, viaf = free.ravel(), tgt.ravel(), via_ok.ravel()
    dist = np.full(2 * hwc, -1, np.int32)
    fr = np.flatnonzero(src.ravel())
    dist[fr] = 0
    hist = collections.deque([fr], maxlen=VIA_DELAY)
    t, end = 0, None
    while any(len(x) for x in hist):
        t += 1
        nb = np.concatenate([fr + 1, fr - 1, fr + w, fr - w]) if len(fr) else fr
        nb = nb[freef[nb] & (dist[nb] < 0)]
        nb = np.unique(nb)
        dist[nb] = t
        if len(hist) == VIA_DELAY and len(hist[0]):
            o = hist[0]
            o = o[viaf[o % hwc]]
            o2 = np.where(o < hwc, o + hwc, o - hwc)
            o2 = np.unique(o2[dist[o2] < 0])
            dist[o2] = t
            nb = np.concatenate([nb, o2])
        hit = nb[tgtf[nb]]
        if len(hit):
            end = int(hit[0])
            break
        fr = nb
        hist.append(nb)
    if end is None:
        return "sem caminho"
    # volta do alvo até a origem
    runs, cur, k, last = [], [], end, None
    while True:
        l, rem = divmod(k, hwc)
        j, i = divmod(rem, w)
        cur.append((j, i))
        d = dist[k]
        if d == 0:
            runs.append((l, cur))
            break
        cand = [k + last] if last else []
        cand += [k + 1, k - 1, k + w, k - w]
        nxt = next((c for c in cand if dist[c] == d - 1), None)
        if nxt is not None:
            last = nxt - k
            k = nxt
            continue
        ko = k + hwc if k < hwc else k - hwc
        if dist[ko] == d - VIA_DELAY and viaf[rem]:
            runs.append((l, cur))
            cur, k, last = [], ko, None
            continue
        return "erro na volta do caminho"
    segs, vias = [], []
    for n, (l, pts) in enumerate(runs):
        sm = smooth(free[l], pts)
        xy = [(BX0 + (i0 + i) * G, BY0 + (j0 + j) * G) for j, i in sm]
        segs += [(l, xy[q], xy[q + 1]) for q in range(len(xy) - 1) if xy[q] != xy[q + 1]]
        if n:
            vias.append(xy[0])
    return split_tight(segs, hw), vias, hw


# ---------------------------------------------------------------- rip-up
def has_pad(net, pt, l):
    j, i = int(round(cy(pt[1]))), int(round(cx(pt[0])))
    return 0 <= j < H and 0 <= i < W and pad_at[l, j, i] == net


def attached(it, pt):
    """A ponta pt da trilha it ainda encosta em outro cobre da mesma rede?"""
    if has_pad(it.net, pt, it.l):
        return True
    for o in by_net[it.net]:
        if o is it or not o.alive:
            continue
        if o.kind == "via":
            if math.dist(pt, o.p1) <= o.hw:
                return True
        elif o.l == it.l and pt_seg(pt[0], pt[1], o.p1, o.p2) <= o.hw + 0.005:
            return True
    return False


def rip(victims):
    """Arranca os itens e as pontas soltas que sobram deles. Devolve os itens arrancados."""
    out = []
    stack = []
    for it in victims:
        if it.alive:
            it.alive = False
            out.append(it)
            stack += [(it.net, it.p1, l) for l in ((0, 1) if it.kind == "via" else (it.l,))]
            if it.kind == "seg":
                stack.append((it.net, it.p2, it.l))
    while stack:
        net, pt, l = stack.pop()
        for o in by_net[net]:
            if not o.alive:
                continue
            if o.kind == "seg" and o.l == l:
                for e, far in ((o.p1, o.p2), (o.p2, o.p1)):
                    if o.alive and math.dist(e, pt) < 0.02 and not attached(o, e):
                        o.alive = False
                        out.append(o)
                        stack.append((net, far, l))
            elif o.kind == "via" and nets[net].GetNetname() != "GND" and math.dist(o.p1, pt) < 0.02:
                # via que perdeu a trilha desta camada e não está em pad: sai junto
                if not has_pad(net, pt, l) and not any(
                        s.alive and s.kind == "seg" and s.l == l and min(math.dist(s.p1, pt), math.dist(s.p2, pt)) <= o.hw
                        for s in by_net[net]):
                    o.alive = False
                    out.append(o)
                    stack.append((net, pt, 1 - l))
    return out


def find_victims(code, segs, vias, hw, zones, protected):
    zx0 = min(z[0] - z[2] for z in zones) - 1
    zy0 = min(z[1] - z[2] for z in zones) - 1
    zx1 = max(z[0] + z[2] for z in zones) + 1
    zy1 = max(z[1] + z[2] for z in zones) + 1
    samples = {0: [], 1: []}
    for l, p1, p2, w in segs:
        n = max(1, int(math.dist(p1, p2) / 0.05))
        for k in range(n + 1):
            x, y = p1[0] + (p2[0] - p1[0]) * k / n, p1[1] + (p2[1] - p1[1]) * k / n
            if zx0 <= x <= zx1 and zy0 <= y <= zy1:
                samples[l].append((x, y, w + (T_CLR if in_tight(x, y) else CLR)))
    for x, y in vias:
        for l in (0, 1):
            samples[l].append((x, y, VIA_D / 2 + (T_CLR if in_tight(x, y) else CLR)))
    out = []
    for it in items:
        if not it.alive or it.net == code or it.net in protected:
            continue
        q = it.bbox()
        if q[2] < zx0 or q[0] > zx1 or q[3] < zy0 or q[1] > zy1:
            continue
        for l in ((0, 1) if it.kind == "via" else (it.l,)):
            if any(pt_seg(x, y, it.p1, it.p2) < r + it.hw - 0.005 for x, y, r in samples[l]):
                out.append(it)
                break
    return out


def commit(code, segs, vias, hw):
    for l, p1, p2, w in segs:
        tr = pcbnew.PCB_TRACK(b)
        tr.SetStart(pcbnew.VECTOR2I(mm(p1[0]), mm(p1[1])))
        tr.SetEnd(pcbnew.VECTOR2I(mm(p2[0]), mm(p2[1])))
        tr.SetWidth(mm(w * 2))
        tr.SetLayer(LAYERS[l])
        tr.SetNet(nets[code])
        b.Add(tr)
        add_item(Item("seg", code, l, p1, p2, w, tr))
    for x, y in vias:
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        v.SetWidth(pcbnew.F_Cu, mm(VIA_D))
        v.SetDrill(mm(VIA_DRILL))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(nets[code])
        b.Add(v)
        add_item(Item("via", code, -1, (x, y), (x, y), VIA_D / 2, v))


# ---------------------------------------------------------------- pares abertos
data = json.load(open(sys.argv[1], encoding="utf-8"))
pairs = []
for u in data["unconnected_items"]:
    a, c = u["items"][0], u["items"][1]
    m = re.search(r"\[(.*?)\]", a["description"])
    if not m or (m.group(1) == "GND" and "--gnd" not in sys.argv):
        continue
    pa, pb = (a["pos"]["x"], a["pos"]["y"]), (c["pos"]["x"], c["pos"]["y"])
    pairs.append((math.dist(pa, pb), m.group(1), pa, pb, tuple(a.get("layers", (0, 1))), tuple(c.get("layers", (0, 1)))))
pairs.sort()
nets = b.GetNetsByNetcode()
work = collections.deque((name, pa, pb, True, la, lb) for _, name, pa, pb, la, lb in pairs)
protected = set()
ok, fail, ripped_all = 0, [], []
while work:
    name, pa, pb, direct, la, lb = work.popleft()
    code = b.GetNetcodeFromNetname(name)
    hw = (W_PWR if name in PWR else W_SIG) / 2
    L = math.dist(pa, pb)
    t0 = time.time()
    r = route(code, hw, pa, pb, direct=direct, la=la, lb=lb)
    zones = None
    if isinstance(r, str) and r in ("sem caminho", "ponta sem acesso"):
        for rad in RADII:
            for zs in ((pa,), (pb,), (pa, pb)):
                z = [(x, y, rad) for x, y in zs]
                r2 = route(code, hw, pa, pb, z, protected, direct, la, lb)
                if not isinstance(r2, str):
                    r, zones = r2, z
                    break
            if zones:
                break
    if isinstance(r, str):
        if r != "já ligado" or direct:
            fail.append((name, pa, pb, r))
        print(f"{name:22s} {L:6.1f} mm  {r}  ({time.time() - t0:.0f}s)", flush=True)
        continue
    segs, vias, hw = r
    note = ""
    if zones:
        victims = find_victims(code, segs, vias, hw, zones, protected)
        gone = rip(victims)
        ripped_all += gone
        if gone:
            rebuild(min(g.bbox()[0] for g in gone), min(g.bbox()[1] for g in gone),
                    max(g.bbox()[2] for g in gone), max(g.bbox()[3] for g in gone))
        hit = collections.defaultdict(list)
        for g in gone:
            for pt in ((g.p1,) if g.kind == "via" else (g.p1, g.p2)):
                for l in ((0, 1) if g.kind == "via" else (g.l,)):
                    j, i = int(round(cy(pt[1]))), int(round(cx(pt[0])))
                    if (pad_at[l, j, i] == g.net or trk_at[l, j, i] == g.net) and pt not in hit[g.net]:
                        hit[g.net].append(pt)
        for net, pts in hit.items():
            for q in pts[1:]:
                work.appendleft((nets[net].GetNetname(), pts[0], q, False, (0, 1), (0, 1)))
        note = f" | raio {zones[0][2]}: arrancou {len(gone)} itens de {sorted(nets[n].GetNetname() for n in {g.net for g in gone})}"
    commit(code, segs, vias, hw)
    protected.add(code)
    ok += 1
    print(f"{name:22s} {L:6.1f} mm  ok: {len(segs)} trilhas, {len(vias)} vias{note}  ({time.time() - t0:.0f}s)", flush=True)

print(f"\nligadas: {ok}; falharam: {len(fail)}; itens arrancados: {len(ripped_all)}")
for name, pa, pb, why in fail:
    print(f"  {name}: ({pa[0]:.2f},{pa[1]:.2f}) -> ({pb[0]:.2f},{pb[1]:.2f}): {why}")
if "--dry" not in sys.argv:
    for g in ripped_all:               # remoções por último: depois de um Remove o SWIG perde os tipos
        if g.obj is not None:
            b.Remove(g.obj)
    b.Save(PCB)
    print("placa salva")
