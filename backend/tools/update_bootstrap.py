#!/usr/bin/env python3
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "school_advisor.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="用 JSON 文件整体更新 SD/PR/TF/DN")
    parser.add_argument("--file", required=True, help="JSON 文件路径（必须包含 SD/PR/TF/DN）")
    args = parser.parse_args()

    fp = Path(args.file).resolve()
    payload = json.loads(fp.read_text(encoding="utf-8"))
    for key in ("SD", "PR", "TF", "DN"):
        if key not in payload:
            raise SystemExit(f"数据缺少字段: {key}")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO datasets (id, sd_json, pr_json, tf_json, dn_json, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              sd_json=excluded.sd_json,
              pr_json=excluded.pr_json,
              tf_json=excluded.tf_json,
              dn_json=excluded.dn_json,
              updated_at=excluded.updated_at
            """,
            (
                json.dumps(payload["SD"], ensure_ascii=False),
                json.dumps(payload["PR"], ensure_ascii=False),
                json.dumps(payload["TF"], ensure_ascii=False),
                json.dumps(payload["DN"], ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    print(f"ok: updated {DB_PATH} from {fp}")


if __name__ == "__main__":
    main()
