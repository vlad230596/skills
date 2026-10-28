#!/usr/bin/env python3
"""Быстрый осмотр файла IPC-2581 из командной строки. Без зависимостей, кроме соседнего ipc2581.py.

    python ipc2581_inspect.py summary    board.cvg      # версия, единицы, Step, Datum, слои, стек, счётчики
    python ipc2581_inspect.py layers     board.cvg      # слои: функция, сторона, полярность, число элементов
    python ipc2581_inspect.py nets       board.cvg [-l "Top Layer"]   # цепи слоя с числом элементов
    python ipc2581_inspect.py components board.cvg      # refdes, корпус, слой, x/y (мм от Datum), поворот, высота
    python ipc2581_inspect.py holes      board.cvg      # отверстия сгруппированы по Ø и металлизации
    python ipc2581_inspect.py bom        board.cvg      # спецификация
    python ipc2581_inspect.py tags       board.cvg      # все пути элементов с числом и атрибутами (разведка формата)

Координаты — мм от Step/Datum, вид сверху, как в ipc2581.py.
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipc2581 as ipc  # noqa: E402

NS = ipc.NS


def tag(e):
    return e.tag[len(NS):] if e.tag.startswith(NS) else e.tag


def fnum(e, k, d=0.0):
    v = e.get(k)
    return float(v) if v is not None else d


def open_file(path):
    root = ET.parse(path).getroot()
    if tag(root) != "IPC-2581":
        sys.exit(f"{path}: корневой элемент {tag(root)}, ожидался IPC-2581")
    return root


def units(root):
    hdr = root.find(f".//{NS}CadHeader")
    return hdr.get("units") if hdr is not None else None


def cmd_summary(args):
    root = open_file(args.file)
    step = root.find(f".//{NS}Step")
    board = ipc.load(args.file)
    dx, dy = board.datum
    print(f"файл      {args.file}")
    print(f"ревизия   {root.get('revision')}   единицы {units(root)}   Step {step.get('name')}")
    print(f"Datum     x={dx} y={dy}  (координаты ниже — от него)")
    xs = [p[1] - dx for r in board.profile for p in r]
    ys = [p[2] - dy for r in board.profile for p in r]
    if xs:
        print(f"контур    {len(board.profile)} колец, рамка x[{min(xs):.3f}..{max(xs):.3f}] y[{min(ys):.3f}..{max(ys):.3f}] "
              f"= {max(xs) - min(xs):.3f} × {max(ys) - min(ys):.3f} мм")
    steps = root.findall(f".//{NS}Step")
    if len(steps) > 1:
        print(f"ВНИМАНИЕ  Step-ов {len(steps)} (панелизация?) — скрипты берут первый")
    stack = root.find(f".//{NS}Stackup")
    if stack is not None:
        print(f"стек      общая толщина {stack.get('overallThickness')} мм")
        for sl in stack.iter(f"{NS}StackupLayer"):
            spec = root.find(f".//{NS}Spec[@name='{sl.get('layerOrGroupRef')}']")
            mat = ""
            if spec is not None:
                p = spec.find(f".//{NS}Property")
                mat = p.get("text") if p is not None else ""
            print(f"          {sl.get('sequence'):>3} {sl.get('layerOrGroupRef'):<28} {sl.get('thickness'):>10}  {mat}")
    comps = step.findall(f"{NS}Component")
    sides = Counter(c.get("layerRef") for c in comps)
    print(f"компонентов {len(comps)}  {dict(sides)}   посадочных мест {len(step.findall(f'{NS}Package'))}   "
          f"PadStack {len(step.findall(f'{NS}PadStack'))}")
    print(f"отверстий (уникальных) {len(board.holes)}")
    print("слои      (layerFunction / side / элементов)")
    for name, (fn, side) in board.layer_info.items():
        nets = board.layers.get(name, {})
        print(f"          {name:<42} {fn or '':<14} {side or '':<9} {sum(len(v) for v in nets.values()):>7}")


def cmd_layers(args):
    board = ipc.load(args.file)
    root = open_file(args.file)
    pol = {l.get("name"): l.get("polarity") for l in root.iter(f"{NS}Layer")}
    for name, (fn, side) in board.layer_info.items():
        nets = board.layers.get(name, {})
        kinds = Counter(type(x).__name__ for v in nets.values() for x in v)
        print(f"{name:<42} {fn or '':<14} {side or '':<9} {pol.get(name) or '':<9} nets={len(nets):<4} {dict(kinds)}")


def cmd_nets(args):
    board = ipc.load(args.file)
    layers = [args.layer] if args.layer else list(board.layers)
    for ln in layers:
        nets = board.layers.get(ln)
        if nets is None:
            sys.exit(f"нет слоя {ln!r}; есть: {list(board.layers)}")
        print(f"[{ln}]  цепей {len(nets)}")
        for net, items in sorted(nets.items(), key=lambda kv: -len(kv[1])):
            print(f"  {len(items):>6}  {net or '(без цепи)'}")


def cmd_components(args):
    root = open_file(args.file)
    step = root.find(f".//{NS}Step")
    d = step.find(f"{NS}Datum")
    dx, dy = (fnum(d, "x"), fnum(d, "y")) if d is not None else (0.0, 0.0)
    print("refDes        package                       layer          x        y      rot  mirror  height  standoff  part")
    for c in step.findall(f"{NS}Component"):
        loc, xf = c.find(f"{NS}Location"), c.find(f"{NS}Xform")
        print(f"{c.get('refDes'):<13} {c.get('packageRef'):<29} {c.get('layerRef'):<12} "
              f"{fnum(loc, 'x') - dx:>8.3f} {fnum(loc, 'y') - dy:>8.3f} "
              f"{fnum(xf, 'rotation') if xf is not None else 0:>6.1f}  "
              f"{(xf.get('mirror') if xf is not None else None) or 'false':<6} "
              f"{fnum(c, 'height'):>6.3f} {fnum(c, 'standoff'):>8.3f}  {c.get('part')}")


def cmd_holes(args):
    board = ipc.load(args.file)
    dx, dy = board.datum
    groups = {}
    for h in board.holes:
        groups.setdefault((round(h.d, 3), h.plated), []).append(h)
    for (d, plating), hs in sorted(groups.items()):
        print(f"Ø{d:<7} {plating:<10} × {len(hs)}")
        if len(hs) <= args.limit:
            for h in hs:
                print(f"     ({h.x - dx:9.3f}, {h.y - dy:9.3f})  {h.name}")


def cmd_bom(args):
    root = open_file(args.file)
    for it in root.iter(f"{NS}BomItem"):
        refs = [r.get("name") for r in it.findall(f"{NS}RefDes")]
        print(f"{it.get('internalPartNumber')}  ×{it.get('quantity')}  pins={it.get('pinCount')}  {it.get('category')}")
        print(f"    {it.get('description')}")
        print(f"    OEM: {it.get('OEMDesignNumberRef')}")
        print(f"    {', '.join(refs)}")


def cmd_tags(args):
    root = open_file(args.file)
    seen = {}

    def walk(e, path):
        p = path + "/" + tag(e)
        n, attrs = seen.setdefault(p, [0, set()])
        seen[p][0] += 1
        attrs.update(e.attrib.keys())
        for ch in e:
            walk(ch, p)

    walk(root, "")
    for p, (n, attrs) in seen.items():
        print(n, p, sorted(attrs))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("summary", cmd_summary), ("layers", cmd_layers), ("nets", cmd_nets), ("components", cmd_components),
                     ("holes", cmd_holes), ("bom", cmd_bom), ("tags", cmd_tags)):
        p = sub.add_parser(name)
        p.add_argument("file")
        if name == "nets":
            p.add_argument("-l", "--layer")
        if name == "holes":
            p.add_argument("--limit", type=int, default=12, help="перечислять координаты, если отверстий группы не больше")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    args.fn(args)


if __name__ == "__main__":
    main()
