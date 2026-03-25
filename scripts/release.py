#!/usr/bin/env python3
import argparse
import json
import re
import shutil
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "VERSION.json"
CHANGELOG_FILE = ROOT / "versions" / "CHANGELOG.md"
ENTRY_HTML = ROOT / "index.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="标准化发布脚本")
    parser.add_argument("--version", required=True, help="版本号，例如 v8.0.1")
    parser.add_argument("--date", default=str(date.today()), help="发布日期 YYYY-MM-DD")
    parser.add_argument("--notes", action="append", default=[], help="发布说明，可重复传参")
    parser.add_argument("--entry", default=str(ENTRY_HTML), help="入口 HTML 文件路径")
    return parser.parse_args()


def ensure_version(v: str) -> None:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", v):
        raise SystemExit("版本号格式错误，要求 vX.Y.Z，例如 v8.0.1")


def write_version_json(version: str, release_date: str, latest_name: str, snapshot_name: str, notes: list[str]) -> None:
    payload = {
        "version": version,
        "release_date": release_date,
        "entry_html": "index.html",
        "latest_html": latest_name,
        "snapshot_html": snapshot_name,
        "notes": notes,
    }
    VERSION_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepend_changelog(version: str, release_date: str, notes: list[str]) -> None:
    CHANGELOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not CHANGELOG_FILE.exists():
        CHANGELOG_FILE.write_text("# CHANGELOG\n\n", encoding="utf-8")
    current = CHANGELOG_FILE.read_text(encoding="utf-8")
    heading = f"## {version} ({release_date})"
    if heading in current:
        raise SystemExit(f"CHANGELOG 已存在版本条目: {heading}")
    entry_lines = [heading]
    for n in notes:
        entry_lines.append(f"- {n}")
    entry = "\n".join(entry_lines) + "\n\n"
    if current.startswith("# CHANGELOG\n\n"):
        new_text = "# CHANGELOG\n\n" + entry + current[len("# CHANGELOG\n\n") :]
    else:
        new_text = "# CHANGELOG\n\n" + entry + current
    CHANGELOG_FILE.write_text(new_text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    ensure_version(args.version)

    entry = Path(args.entry).resolve()
    if not entry.exists():
        raise SystemExit(f"入口文件不存在: {entry}")

    latest_name = f"school-advisor-{args.version}-latest.html"
    snapshot_name = f"versions/{args.version}-{args.date.replace('-', '')}.html"
    latest_path = ROOT / latest_name
    snapshot_path = ROOT / snapshot_name
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(entry, latest_path)
    shutil.copy2(entry, snapshot_path)

    notes = args.notes or ["常规版本发布"]
    write_version_json(args.version, args.date, latest_name, snapshot_name, notes)
    prepend_changelog(args.version, args.date, notes)

    print("release done")
    print(f"  version: {args.version}")
    print(f"  latest:  {latest_path}")
    print(f"  snapshot:{snapshot_path}")
    print(f"  version: {VERSION_FILE}")
    print(f"  changelog:{CHANGELOG_FILE}")


if __name__ == "__main__":
    main()
