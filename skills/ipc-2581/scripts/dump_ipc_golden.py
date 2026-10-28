"""Эталон для сверки другого читателя: что видит ipc2581.py в файле IPC-2581.

    python scripts/dump_ipc_golden.py board.cvg board.golden.json

Так сверялся порт читателя на C# (эталон его тестов).
Координаты — мм от Step.Datum (x - DX, y - DY).
Слои SIGNAL и LEGEND и контур — полностью, в порядке ipc2581.py; остальные слои —
счётчики и суммы координат. Отверстия ipc2581.py округляет до 1e-4 — так и лежат.
Раздел components ipc2581.py не разбирает: он снят напрямую ElementTree
(независимая сверка, не порт).
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # ipc2581.py лежит рядом
import ipc2581 as ipc  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
src, out = sys.argv[1], sys.argv[2]
b = ipc.load(src)
DX, DY = b.datum
R = lambda v: round(v, 9)


def ring(r, dx=DX, dy=DY):
    o = []
    for s in r:
        if s[0] == "A":
            o.append(["A", R(s[1] - dx), R(s[2] - dy), R(s[3] - dx), R(s[4] - dy), s[5]])
        else:
            o.append([s[0], R(s[1] - dx), R(s[2] - dy)])
    return o


def shape(sh):
    if sh[0] == "circle":
        return ["circle", R(sh[1])]
    if sh[0] == "rect":
        return ["rect", R(sh[1]), R(sh[2])]
    return ["poly", [ring(r, 0, 0) for r in sh[1].rings]]


def prim(it):
    if isinstance(it, ipc.Line):
        return ["L", R(it.x1 - DX), R(it.y1 - DY), R(it.x2 - DX), R(it.y2 - DY), R(it.width)]
    if isinstance(it, ipc.Arc):
        return ["A", R(it.x1 - DX), R(it.y1 - DY), R(it.x2 - DX), R(it.y2 - DY),
                R(it.cx - DX), R(it.cy - DY), it.ccw, R(it.width)]
    if isinstance(it, ipc.Poly):
        return ["P", [ring(r) for r in it.rings]]
    return ["D", R(it.x - DX), R(it.y - DY), R(it.rot), it.pin, shape(it.shape)]


def stats(items):
    """Счётчики и суммы по типам: L/A — все координаты и ширина, P — вершины колец, D — центры."""
    s = {}
    for it in items:
        p = prim(it)
        k = p[0]
        e = s.setdefault(k, {"n": 0, "sum": 0.0, "vertices": 0})
        e["n"] += 1
        if k in ("L", "A"):
            e["sum"] += sum(v for v in p[1:] if not isinstance(v, bool))
        elif k == "P":
            for r in p[1]:
                e["vertices"] += len(r)
                e["sum"] += sum(v for sg in r for v in sg[1:] if not isinstance(v, bool))
        else:
            e["sum"] += p[1] + p[2] + p[3]
    for e in s.values():
        e["sum"] = R(e["sum"])
    return s


layers = []
for name, (func, side) in b.layer_info.items():
    nets = b.layers.get(name, {})
    full = func in ("SIGNAL", "LEGEND")
    layers.append({
        "name": name, "function": func, "side": side,
        "nets": {net: ({"items": [prim(i) for i in items]} if full else {"stats": stats(items)})
                 for net, items in nets.items()},
    })

holes = sorted([[R(h.x - DX), R(h.y - DY), R(h.d), h.plated, h.name] for h in b.holes])

# --- компоненты: напрямую ElementTree ---
NS = ipc.NS
root = ET.parse(src).getroot()
step = root.find(f".//{NS}Step")
pins = {}
for ps in step.findall(NS + "PadStack"):
    for lp in ps.findall(NS + "LayerPad"):
        pr = lp.find(NS + "PinRef")
        if pr is not None:
            pins.setdefault(pr.get("componentRef"), set()).add((pr.get("pin"), lp.get("layerRef")))
comps = []
for c in step.findall(NS + "Component"):
    loc = c.find(NS + "Location"); xf = c.find(NS + "Xform")
    comps.append({
        "refDes": c.get("refDes"), "package": c.get("packageRef"), "layer": c.get("layerRef"),
        "x": R(float(loc.get("x")) - DX), "y": R(float(loc.get("y")) - DY),
        "rotation": R(float(xf.get("rotation", 0)) if xf is not None else 0.0),
        "padCount": len(pins.get(c.get("refDes"), ())),
    })
comps.sort(key=lambda c: c["refDes"])
packages = sorted([{"name": p.get("name"), "pins": len(p.findall(NS + "Pin"))} for p in step.findall(NS + "Package")],
                  key=lambda p: p["name"])

doc = {
    "source": os.path.basename(src),
    "generator": "dump_ipc_golden.py (ipc2581.py)",
    "datum": [DX, DY],
    "outline": [ring(r) for r in b.profile],
    "holes": holes,
    "layers": layers,
    "components": comps,
    "packages": packages,
}
with open(out, "w", encoding="utf-8") as fo:
    json.dump(doc, fo, ensure_ascii=False, separators=(",", ":"))
print(out, os.path.getsize(out), "байт;", len(holes), "отверстий,", len(comps), "компонентов")
