#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEED_PATH = ROOT / "data" / "seed.json"


def load_payload(path: pathlib.Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("seed.json 必须是对象")
    if not isinstance(data.get("SD"), list):
        raise ValueError("seed.json 缺少 SD 数组")
    for k in ("PR", "TF", "DN"):
        if not isinstance(data.get(k), dict):
            raise ValueError(f"seed.json 缺少 {k} 对象")
    return data


def post_json(url: str, token: str, payload: dict, timeout: int = 30) -> tuple[int, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")


def main() -> None:
    p = argparse.ArgumentParser(description="Publish seed.json to Cloudflare Pages Function API")
    p.add_argument("--url", required=True, help="如 https://school-advisor.pages.dev/api/admin/bootstrap")
    p.add_argument("--token", default=os.getenv("CF_PUBLISH_TOKEN", ""), help="发布 token（默认读取 CF_PUBLISH_TOKEN）")
    p.add_argument("--file", default=str(SEED_PATH), help="要发布的数据文件，默认 data/seed.json")
    args = p.parse_args()

    if not args.token.strip():
        raise SystemExit("缺少 token：请传 --token 或设置环境变量 CF_PUBLISH_TOKEN")

    file_path = pathlib.Path(args.file).resolve()
    payload = load_payload(file_path)
    code, text = post_json(args.url, args.token.strip(), payload)

    print(f"HTTP {code}")
    print(text)
    if code < 200 or code >= 300:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
