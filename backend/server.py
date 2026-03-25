#!/usr/bin/env python3
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "school_advisor.db"


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET,PUT,OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _get_bootstrap_payload() -> dict:
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT sd_json, pr_json, tf_json, dn_json, updated_at FROM datasets WHERE id=1"
        ).fetchone()
        if not row:
            return {
                "SD": [],
                "PR": {},
                "TF": {},
                "DN": {},
                "updatedAt": None,
            }
        return {
            "SD": json.loads(row["sd_json"]),
            "PR": json.loads(row["pr_json"]),
            "TF": json.loads(row["tf_json"]),
            "DN": json.loads(row["dn_json"]),
            "updatedAt": row["updated_at"],
        }


def _replace_payload(payload: dict) -> None:
    required = ["SD", "PR", "TF", "DN"]
    missing = [k for k in required if k not in payload]
    if missing:
        raise ValueError(f"缺少字段: {', '.join(missing)}")
    if not isinstance(payload["SD"], list):
        raise ValueError("SD 必须是数组")
    if not isinstance(payload["PR"], dict):
        raise ValueError("PR 必须是对象")
    if not isinstance(payload["TF"], dict):
        raise ValueError("TF 必须是对象")
    if not isinstance(payload["DN"], dict):
        raise ValueError("DN 必须是对象")

    updated_at = datetime.now(timezone.utc).isoformat()
    with _db_conn() as conn:
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
                updated_at,
            ),
        )
        conn.commit()


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,PUT,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        p = urlparse(self.path)
        if p.path == "/api/health":
            _json_response(self, 200, {"ok": True, "dbPath": str(DB_PATH)})
            return
        if p.path == "/api/bootstrap":
            payload = _get_bootstrap_payload()
            _json_response(self, 200, payload)
            return
        if p.path == "/api/schools":
            payload = _get_bootstrap_payload()
            q = parse_qs(p.query)
            district = q.get("district", [""])[0]
            school_type = q.get("type", [""])[0]
            schools = payload["SD"]
            if district:
                schools = [s for s in schools if len(s) > 1 and s[1] == district]
            if school_type:
                schools = [s for s in schools if len(s) > 2 and s[2] == school_type]
            _json_response(self, 200, {"count": len(schools), "items": schools})
            return
        _json_response(self, 404, {"error": "Not Found"})

    def do_PUT(self) -> None:
        p = urlparse(self.path)
        if p.path != "/api/bootstrap":
            _json_response(self, 404, {"error": "Not Found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8"))
            _replace_payload(payload)
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "请求体不是合法 JSON"})
            return
        except ValueError as e:
            _json_response(self, 400, {"error": str(e)})
            return
        _json_response(self, 200, {"ok": True})

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Primary School Advisor API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"API running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
