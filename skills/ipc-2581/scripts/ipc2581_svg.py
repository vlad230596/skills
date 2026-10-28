#!/usr/bin/env python3
"""Нарисовать слои IPC-2581 в SVG — быстрая проверка «разобрал правильно?» глазами. Без зависимостей.

    python ipc2581_svg.py board.cvg -l "Top Layer" -l "Top Overlay" --holes -o top.svg
    python ipc2581_svg.py board.cvg -l "Bottom Layer" --mirror -o bottom-as-seen-from-below.svg
    python ipc2581_svg.py board.cvg -l "Top Layer" --net "GND" --window=-20,-20,20,20 -o zoom.svg

Координаты — мм от Datum, ось Y вверх (в SVG переворачивается), единицы SVG = мм.
Вид — «сверху насквозь», как в файле. --mirror зеркалит по X (взгляд на плату снизу).
Полигоны рисуются с fill-rule=evenodd, вырезы (Cutout) — дырки. Дуги — настоящие SVG-дуги.
Слои с NEGATIVE-полярностью и Text/Polyline/нестандартные примитивы не рисуются (как и в читателях).
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ipc2581 as ipc  # noqa: E402

COLORS = ["#c83232", "#2a6fdb", "#1a8f3c", "#b8860b", "#8a2be2", "#0f8b8d", "#666"]


def arc_path(x1, y1, x2, y2, cx, cy, ccw, mirror):
    """SVG-дуга от (x1,y1) к (x2,y2) вокруг (cx,cy); точки уже в координатах SVG, ccw — в координатах платы."""
    r = math.hypot(x1 - cx, y1 - cy)
    a1, a2 = math.atan2(y1 - cy, x1 - cx), math.atan2(y2 - cy, x2 - cx)
    # Переворот Y вместе с показом «Y вверх» картинку не меняет: против часовой на плате = против часовой на экране.
    # mirror по X меняет обход на обратный. В SVG угол atan2 растёт по часовой (Y вниз).
    span = (a2 - a1) % (2 * math.pi)
    screen_cw = (not ccw) != mirror
    if not screen_cw:
        span = 2 * math.pi - span if span else 0
    if span == 0 and (x1, y1) == (x2, y2):
        span = 2 * math.pi             # полная окружность: два полукруга
    sweep = 1 if screen_cw else 0
    if span >= 2 * math.pi - 1e-9:
        mx, my = 2 * cx - x1, 2 * cy - y1
        return f"A{r:.4f},{r:.4f} 0 1 {sweep} {mx:.4f},{my:.4f} A{r:.4f},{r:.4f} 0 1 {sweep} {x2:.4f},{y2:.4f}"
    large = 1 if span > math.pi else 0
    return f"A{r:.4f},{r:.4f} 0 {large} {sweep} {x2:.4f},{y2:.4f}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("-l", "--layer", action="append", default=[], help="имя слоя (можно несколько)")
    ap.add_argument("--net", help="рисовать только эту цепь")
    ap.add_argument("--holes", action="store_true", help="добавить отверстия")
    ap.add_argument("--profile", action="store_true", default=True, help="контур платы (по умолчанию да)")
    ap.add_argument("--mirror", action="store_true", help="зеркало по X (вид снизу)")
    ap.add_argument("--window", help="x0,y0,x1,y1 в мм от Datum; по умолчанию — рамка контура")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    b = ipc.load(args.file)
    dx, dy = b.datum
    mir = -1.0 if args.mirror else 1.0

    def P(x, y):
        return mir * (x - dx), -(y - dy)

    def ring_d(ring):
        pts = [s for s in ring]
        x, y = P(pts[0][1], pts[0][2])
        d = [f"M{x:.4f},{y:.4f}"]
        cur = (x, y)
        for s in pts[1:]:
            ex, ey = P(s[1], s[2])
            if s[0] == "A":
                cx, cy = P(s[3], s[4])
                d.append(arc_path(cur[0], cur[1], ex, ey, cx, cy, s[5], args.mirror))
            else:
                d.append(f"L{ex:.4f},{ey:.4f}")
            cur = (ex, ey)
        return " ".join(d) + " Z"

    if args.window:
        x0, y0, x1, y1 = (float(v) for v in args.window.split(","))
    else:
        xs = [p[1] - dx for r in b.profile for p in r]
        ys = [p[2] - dy for r in b.profile for p in r]
        if not xs:
            sys.exit("контура нет — задайте --window")
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        pad = 2
        x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    vx = min(mir * x0, mir * x1)
    vw = abs(x1 - x0)
    vy = -y1
    vh = abs(y1 - y0)

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vx:.3f} {vy:.3f} {vw:.3f} {vh:.3f}" '
           f'width="{min(2400, vw * 12):.0f}" style="background:#fff">']

    if args.profile and b.profile:
        d = " ".join(ring_d(r) for r in b.profile)
        out.append(f'<path d="{d}" fill="none" stroke="#000" stroke-width="0.15" fill-rule="evenodd"/>')

    for i, name in enumerate(args.layer):
        nets = b.layers.get(name)
        if nets is None:
            sys.exit(f"нет слоя {name!r}; есть: {list(b.layers)}")
        col = COLORS[i % len(COLORS)]
        out.append(f'<g id="{name}" stroke="{col}" fill="{col}" fill-opacity="0.45" stroke-linecap="round">')
        for net, items in nets.items():
            if args.net and net != args.net:
                continue
            for it in items:
                if isinstance(it, ipc.Line):
                    ax, ay = P(it.x1, it.y1)
                    bx, by = P(it.x2, it.y2)
                    out.append(f'<path d="M{ax:.4f},{ay:.4f} L{bx:.4f},{by:.4f}" fill="none" stroke-width="{max(it.width, 0.03):.4f}"/>')
                elif isinstance(it, ipc.Arc):
                    ax, ay = P(it.x1, it.y1)
                    bx, by = P(it.x2, it.y2)
                    cx, cy = P(it.cx, it.cy)
                    out.append(f'<path d="M{ax:.4f},{ay:.4f} {arc_path(ax, ay, bx, by, cx, cy, it.ccw, args.mirror)}" '
                               f'fill="none" stroke-width="{max(it.width, 0.03):.4f}"/>')
                elif isinstance(it, ipc.Poly):
                    d = " ".join(ring_d(r) for r in it.rings if r)
                    out.append(f'<path d="{d}" fill-rule="evenodd" stroke-width="0.02"/>')
                elif isinstance(it, ipc.Pad):
                    cx, cy = P(it.x, it.y)
                    sh = it.shape
                    rot = -mir * it.rot
                    if sh[0] == "circle":
                        out.append(f'<circle cx="{cx:.4f}" cy="{cy:.4f}" r="{sh[1] / 2:.4f}" stroke-width="0.02"/>')
                    elif sh[0] == "rect":
                        out.append(f'<rect x="{-sh[1] / 2:.4f}" y="{-sh[2] / 2:.4f}" width="{sh[1]:.4f}" height="{sh[2]:.4f}" '
                                   f'transform="translate({cx:.4f},{cy:.4f}) rotate({rot:.3f})" stroke-width="0.02"/>')
                    elif sh[0] == "poly":
                        d = " ".join(ring_d(r) for r in sh[1].rings if r)
                        out.append(f'<path d="{d}" fill-rule="evenodd" stroke-width="0.02" '
                                   f'transform="translate({cx:.4f},{cy:.4f}) rotate({rot:.3f}) scale({mir},-1)"/>')
        out.append("</g>")

    if args.holes:
        out.append('<g fill="#fff" stroke="#000" stroke-width="0.03">')
        for h in b.holes:
            cx, cy = P(h.x, h.y)
            out.append(f'<circle cx="{cx:.4f}" cy="{cy:.4f}" r="{h.d / 2:.4f}"/>')
        out.append("</g>")

    out.append("</svg>")
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"{args.out}: слоёв {len(args.layer)}, отверстий {len(b.holes) if args.holes else 0}, окно {x0:.1f},{y0:.1f}..{x1:.1f},{y1:.1f} мм")


if __name__ == "__main__":
    main()
