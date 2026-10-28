"""Проверка проекта на соответствие rules.toml. Только stdlib (Python 3.11+).

    python check.py [PROJECT]          # один проект (по умолчанию — текущая папка)
    python check.py --all <папка>     # каждая подпапка — отдельный проект, сводка
    python check.py --json PROJECT     # машинный вывод
    python check.py --rules X.toml ... # другой файл правил (или env PROJECT_CONVENTIONS_RULES)

Код выхода: 0 — нарушений нет, 1 — есть хотя бы одно error, 2 — ошибка запуска.
Glob'ы сравниваются с именами в корне проекта с учётом регистра (Windows иначе путает Docs и docs).
"""

import argparse
import fnmatch
import json
import os
import re
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "rules.toml"


@dataclass
class Result:
    id: str
    title: str
    severity: str
    status: str  # ok | fail | n/a
    problems: list[str] = field(default_factory=list)


def matches(names: list[str], pattern: str) -> list[str]:
    return [n for n in names if fnmatch.fnmatchcase(n, pattern)]


def check_rule(root: Path, names: list[str], rule: dict) -> Result:
    res = Result(rule["id"], rule["title"], rule.get("severity", "error"), "ok")

    applies = rule.get("applies_if_any", [])
    if applies and not any(matches(names, p) for p in applies):
        res.status = "n/a"
        return res

    for pattern in rule.get("require", []):
        if not matches(names, pattern):
            res.problems.append(f"нет {pattern}")

    allow = set(rule.get("allow", []))
    for pattern in rule.get("forbid", []):
        for name in matches(names, pattern):
            if name not in allow:
                res.problems.append(f"лишнее: {name}")

    for item in rule.get("forbid_text", []):
        path = root / item["file"]
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(item["pattern"], text, re.MULTILINE):
                res.problems.append(f"{item['file']}: {item.get('message', item['pattern'])}")

    if res.problems:
        res.status = "fail"
    return res


def check_project(root: Path, rules: list[dict]) -> list[Result]:
    names = sorted(os.listdir(root))
    return [check_rule(root, names, r) for r in rules]


def has_errors(results: list[Result]) -> bool:
    return any(r.status == "fail" and r.severity == "error" for r in results)


def print_project(root: Path, results: list[Result]) -> None:
    print(f"{root}")
    for r in results:
        mark = {"ok": "  ok ", "n/a": "  -- ", "fail": "  ERR" if r.severity == "error" else "  WRN"}[r.status]
        print(f"{mark} {r.id}: {r.title}")
        for p in r.problems:
            print(f"        {p}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--all", action="store_true", help="PROJECT — папка с проектами, проверить каждую подпапку")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--rules", default=os.environ.get("PROJECT_CONVENTIONS_RULES", DEFAULT_RULES))
    args = ap.parse_args()

    try:
        rules = tomllib.loads(Path(args.rules).read_text(encoding="utf-8"))["rule"]
    except (OSError, tomllib.TOMLDecodeError, KeyError) as e:
        print(f"не удалось прочитать правила {args.rules}: {e}", file=sys.stderr)
        return 2

    base = Path(args.project).resolve()
    if not base.is_dir():
        print(f"нет такой папки: {base}", file=sys.stderr)
        return 2
    roots = sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith((".", "$"))) if args.all else [base]

    report = {str(root): check_project(root, rules) for root in roots}

    if args.json:
        print(json.dumps({k: [asdict(r) for r in v] for k, v in report.items()}, ensure_ascii=False, indent=2))
    else:
        for root, results in report.items():
            print_project(Path(root), results)
        if args.all:
            bad = sum(has_errors(v) for v in report.values())
            print(f"\nпроектов: {len(report)}, с ошибками: {bad}")

    return 1 if any(has_errors(v) for v in report.values()) else 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
