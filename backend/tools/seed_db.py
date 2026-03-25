#!/usr/bin/env python3
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "school_advisor.db"
SEED_PATH = ROOT / "data" / "seed.json"


def main() -> None:
    if not SEED_PATH.exists():
        raise SystemExit(f"未找到 seed 文件: {SEED_PATH}")

    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for key in ("SD", "PR", "TF", "DN"):
        if key not in payload:
            raise SystemExit(f"seed 缺少字段: {key}")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS datasets (
              id INTEGER PRIMARY KEY CHECK (id=1),
              sd_json TEXT NOT NULL,
              pr_json TEXT NOT NULL,
              tf_json TEXT NOT NULL,
              dn_json TEXT NOT NULL,
              updated_at TEXT NOT NULL
            )
            """
        )
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
    print(f"ok: {DB_PATH}")


if __name__ == "__main__":
    main()
