"""Минимальный разбор IPC-2581 (rev B, экспорт Altium) — только то, что нужно
для привязки платы: медь по слоям с цепями, контур, отверстия.

Без внешних зависимостей. Координаты — мм в системе Altium, как в файле;
Step.Datum (у нашей платы — центр, 1270;1270) отдаётся отдельно.

Геометрия возвращается примитивами:
  Line(x1, y1, x2, y2, width)                    — дорожка, концы круглые
  Arc(x1, y1, x2, y2, cx, cy, ccw, width)        — дуга дорожки
  Poly(rings)                                    — полигон; rings[0] наружный контур,
                                                   остальные — вырезы (Cutout)
  Pad(x, y, shape, rot)                          — площадка по примитиву из словаря
Контур кольца — список сегментов ('L', x, y) / ('A', x, y, cx, cy, ccw),
первая точка — ('M', x, y).
"""
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET

NS = "{http://webstds.ipc.org/2581}"


def _t(e):
    return e.tag[len(NS):] if e.tag.startswith(NS) else e.tag


def _f(e, k, d=0.0):
    v = e.get(k)
    return float(v) if v is not None else d


@dataclass
class Line:
    x1: float; y1: float; x2: float; y2: float; width: float


@dataclass
class Arc:
    x1: float; y1: float; x2: float; y2: float
    cx: float; cy: float; ccw: bool; width: float


@dataclass
class Poly:
    rings: list


@dataclass
class Pad:
    x: float; y: float; shape: object; rot: float = 0.0
    pin: str = ""


@dataclass
class Hole:
    x: float; y: float; d: float; plated: str; name: str = ""


@dataclass
class Board:
    datum: tuple = (0.0, 0.0)
    profile: list = field(default_factory=list)          # кольца контура платы
    layers: dict = field(default_factory=dict)           # имя -> {net: [примитивы]}
    holes: list = field(default_factory=list)
    layer_info: dict = field(default_factory=dict)       # имя -> (function, side)


def _ring(poly):
    """Polygon/Cutout -> [('M',x,y), ('L',x,y) | ('A',x,y,cx,cy,ccw), ...]"""
    out = []
    for ch in poly:
        k = _t(ch)
        if k == "PolyBegin":
            out.append(("M", _f(ch, "x"), _f(ch, "y")))
        elif k == "PolyStepSegment":
            out.append(("L", _f(ch, "x"), _f(ch, "y")))
        elif k == "PolyStepCurve":
            out.append(("A", _f(ch, "x"), _f(ch, "y"), _f(ch, "centerX"), _f(ch, "centerY"),
                        ch.get("clockwise") == "false"))
    return out


def _contour(c):
    rings = []
    for ch in c:
        if _t(ch) in ("Polygon", "Cutout"):
            rings.append(_ring(ch))
    return Poly(rings)


def _width(e):
    d = e.find(NS + "LineDesc")
    return _f(d, "lineWidth") if d is not None else 0.0


def _features(root, sink):
    """Все геометрические элементы под root -> sink (list)."""
    for e in root.iter():
        k = _t(e)
        if k == "Line":
            sink.append(Line(_f(e, "startX"), _f(e, "startY"), _f(e, "endX"), _f(e, "endY"), _width(e)))
        elif k == "Arc":
            sink.append(Arc(_f(e, "startX"), _f(e, "startY"), _f(e, "endX"), _f(e, "endY"),
                            _f(e, "centerX"), _f(e, "centerY"), e.get("clockwise") == "false", _width(e)))
        elif k == "Contour":
            sink.append(_contour(e))


def _primitives(root):
    prims = {}
    for es in root.iter(NS + "EntryStandard"):
        ch = next(iter(es), None)
        if ch is None:
            continue
        k = _t(ch)
        if k == "Circle":
            prims[es.get("id")] = ("circle", _f(ch, "diameter"))
        elif k == "RectCenter":
            prims[es.get("id")] = ("rect", _f(ch, "width"), _f(ch, "height"))
        elif k == "Contour":
            prims[es.get("id")] = ("poly", _contour(ch))
    return prims


def load(path):
    root = ET.parse(path).getroot()
    step = root.find(f".//{NS}Step")
    b = Board()
    d = step.find(NS + "Datum")
    if d is not None:
        b.datum = (_f(d, "x"), _f(d, "y"))
    for lay in root.iter(NS + "Layer"):
        b.layer_info[lay.get("name")] = (lay.get("layerFunction"), lay.get("side"))

    prof = step.find(NS + "Profile")
    if prof is not None:
        b.profile = _contour(prof).rings

    prims = _primitives(root)

    for lf in step.findall(NS + "LayerFeature"):
        nets = b.layers.setdefault(lf.get("layerRef"), {})
        for s in lf.findall(NS + "Set"):
            items = nets.setdefault(s.get("net") or "", [])
            for f in s.findall(NS + "Features"):
                _features(f, items)

    seen = set()
    for ps in step.findall(NS + "PadStack"):
        net = ps.get("net") or ""
        for lh in ps.findall(NS + "LayerHole"):
            key = (round(_f(lh, "x"), 4), round(_f(lh, "y"), 4), round(_f(lh, "diameter"), 4))
            if key not in seen:
                seen.add(key)
                b.holes.append(Hole(key[0], key[1], key[2], lh.get("platingStatus", ""), lh.get("name", "")))
        for lp in ps.findall(NS + "LayerPad"):
            loc = lp.find(NS + "Location")
            ref = lp.find(NS + "StandardPrimitiveRef")
            if loc is None or ref is None or ref.get("id") not in prims:
                continue
            xf = lp.find(NS + "Xform")
            pr = lp.find(NS + "PinRef")
            pin = f"{pr.get('componentRef')}-{pr.get('pin')}" if pr is not None else ""
            b.layers.setdefault(lp.get("layerRef"), {}).setdefault(net, []).append(
                Pad(_f(loc, "x"), _f(loc, "y"), prims[ref.get("id")],
                    _f(xf, "rotation") if xf is not None else 0.0, pin))
    for h in step.iter(NS + "Hole"):
        key = (round(_f(h, "x"), 4), round(_f(h, "y"), 4), round(_f(h, "diameter"), 4))
        if key not in seen:
            seen.add(key)
            b.holes.append(Hole(key[0], key[1], key[2], h.get("platingStatus", ""), h.get("name", "")))
    return b
