#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import sqlite3
import subprocess
import threading
import uuid
from io import BytesIO
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from openpyxl import load_workbook
except Exception:
    load_workbook = None


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "school_advisor.db"
SOURCES_PATH = ROOT / "config" / "sources.json"
ADMIN_DIR = ROOT / "admin"
SEED_PATH = ROOT / "data" / "seed.json"
PUBLISH_TASKS: dict[str, dict] = {}
PUBLISH_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(body)


def _text_response(handler: BaseHTTPRequestHandler, status: int, body: str, content_type: str) -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _db_conn() as conn:
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
            CREATE TABLE IF NOT EXISTS proposals (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source TEXT NOT NULL,
              proposal_type TEXT NOT NULL,
              proposal_key TEXT NOT NULL,
              new_value_json TEXT NOT NULL,
              evidence_url TEXT,
              status TEXT NOT NULL DEFAULT 'pending',
              note TEXT,
              created_at TEXT NOT NULL,
              reviewed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_proposals_unique
            ON proposals(source, proposal_type, proposal_key, new_value_json)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS policy_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_key TEXT NOT NULL UNIQUE,
              event_date TEXT,
              title TEXT NOT NULL,
              source TEXT,
              evidence_url TEXT,
              payload_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _ensure_default_sources() -> None:
    if SOURCES_PATH.exists():
        return
    SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    default = {
        "sources": [
            {
                "id": "sh_municipal_policy",
                "name": "上海市教委官网（政策）",
                "enabled": False,
                "type": "policy_html",
                "url": "https://edu.sh.gov.cn/",
                "keywords": ["幼升小", "义务教育", "招生", "摇号", "入学", "公办", "民办"],
            },
            {
                "id": "district_school_json_sample",
                "name": "区教育局学校 JSON 样例",
                "enabled": False,
                "type": "school_json",
                "url": "https://example.com/schools.json",
                "mapping": {
                    "name": "name",
                    "district": "district",
                    "schoolType": "type",
                    "lotteryLow": "lotteryLow",
                    "lotteryHigh": "lotteryHigh",
                    "recommend": "recommend",
                    "desc": "desc",
                    "lat": "lat",
                    "lng": "lng",
                    "status": "status",
                    "tier": "tier",
                },
            },
        ]
    }
    SOURCES_PATH.write_text(json.dumps(default, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_sources() -> list[dict]:
    _ensure_default_sources()
    payload = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("sources.json 格式错误：sources 必须是数组")
    return sources


def _normalize_school_name(name: str) -> str:
    return re.sub(r"[（(]\s*小学部\s*[）)]", "小学部", name or "")


def _normalize_payload_names(payload: dict) -> dict:
    sd = payload.get("SD", [])
    pr = payload.get("PR", {})
    tf = payload.get("TF", {})
    dn = payload.get("DN", {})
    updated_at = payload.get("updatedAt")

    name_map: dict[str, str] = {}
    normalized_sd: list = []
    for row in sd:
        if isinstance(row, list) and row:
            old_name = row[0]
            new_name = _normalize_school_name(str(old_name))
            if old_name != new_name:
                name_map[str(old_name)] = new_name
            new_row = list(row)
            new_row[0] = new_name
            normalized_sd.append(new_row)
        else:
            normalized_sd.append(row)

    def _normalize_keyed_map(obj: dict) -> dict:
        out: dict = {}
        for k, v in (obj or {}).items():
            nk = name_map.get(k, _normalize_school_name(k))
            if nk not in out:
                out[nk] = v
        return out

    return {
        "SD": normalized_sd,
        "PR": _normalize_keyed_map(pr),
        "TF": _normalize_keyed_map(tf),
        "DN": dn,
        "updatedAt": updated_at,
    }


def _save_sources(sources: list[dict]) -> None:
    SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_PATH.write_text(
        json.dumps({"sources": sources}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _get_bootstrap_payload() -> dict:
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT sd_json, pr_json, tf_json, dn_json, updated_at FROM datasets WHERE id=1"
        ).fetchone()
        if not row:
            return {"SD": [], "PR": {}, "TF": {}, "DN": {}, "updatedAt": None}
        payload = {
            "SD": json.loads(row["sd_json"]),
            "PR": json.loads(row["pr_json"]),
            "TF": json.loads(row["tf_json"]),
            "DN": json.loads(row["dn_json"]),
            "updatedAt": row["updated_at"],
        }
        return _normalize_payload_names(payload)


def _replace_payload(payload: dict) -> None:
    payload = _normalize_payload_names(payload)
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
                _now(),
            ),
        )
        conn.commit()


def _write_seed_json(payload: dict) -> None:
    SEED_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEED_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_git(args: list[str], extra_env: dict | None = None, timeout_sec: int = 120) -> tuple[int, str]:
    env = None
    if extra_env:
        env = dict(**__import__("os").environ)
        env.update(extra_env)
    try:
        p = subprocess.run(
            args,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_sec,
        )
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") + "\n" + (e.stderr or "")
        return 124, f"命令超时（>{timeout_sec}s）\n{out}".strip()


def _publish_online(message: str, remote: str, refspec: str, git_ssh_command: str = "") -> dict:
    payload = _get_bootstrap_payload()
    _write_seed_json(payload)

    logs = []
    env = {}
    if git_ssh_command.strip():
        env["GIT_SSH_COMMAND"] = git_ssh_command.strip()

    code, out = _run_git(["git", "add", "data/seed.json"], extra_env=env)
    logs.append({"cmd": "git add data/seed.json", "code": code, "output": out.strip()})
    if code != 0:
        return {"ok": False, "step": "git_add", "logs": logs}

    code, out = _run_git(["git", "diff", "--cached", "--quiet"], extra_env=env)
    has_changes = code != 0
    logs.append({"cmd": "git diff --cached --quiet", "code": code, "output": out.strip()})

    committed = False
    if has_changes:
        code, out = _run_git(["git", "commit", "-m", message], extra_env=env)
        logs.append({"cmd": f'git commit -m "{message}"', "code": code, "output": out.strip()})
        if code != 0:
            return {"ok": False, "step": "git_commit", "logs": logs}
        committed = True

    code, out = _run_git(["git", "push", remote, refspec], extra_env=env)
    logs.append({"cmd": f"git push {remote} {refspec}", "code": code, "output": out.strip()})
    if code != 0:
        return {"ok": False, "step": "git_push", "logs": logs, "committed": committed}

    return {"ok": True, "logs": logs, "committed": committed}


def _publish_to_cloudflare_api(url: str, token: str, payload: dict, timeout_sec: int = 30) -> tuple[int, str]:
    if not url or not token:
        return 400, "cloudflare url/token 不能为空"
    try:
        u = urlparse(url)
        origin = f"{u.scheme}://{u.netloc}" if u.scheme and u.netloc else "https://school-advisor.pages.dev"
    except Exception:
        origin = "https://school-advisor.pages.dev"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
            "Origin": origin,
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.getcode(), resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        return 599, str(e)


def _new_publish_task(message: str, remote: str, refspec: str, mode: str = "git", cloudflare_url: str = "") -> dict:
    task_id = str(uuid.uuid4())
    now = _now()
    steps = [{"key": "export_seed", "label": "导出数据库到 seed.json", "status": "pending", "detail": ""}]
    if mode == "api":
        steps.append({"key": "api_publish", "label": "推送到 Cloudflare API", "status": "pending", "detail": ""})
    else:
        steps.extend(
            [
                {"key": "git_add", "label": "Git 暂存文件", "status": "pending", "detail": ""},
                {"key": "git_check", "label": "检查是否有变更", "status": "pending", "detail": ""},
                {"key": "git_commit", "label": "创建提交", "status": "pending", "detail": ""},
                {"key": "git_push", "label": "推送到线上仓库", "status": "pending", "detail": ""},
            ]
        )
    task = {
        "taskId": task_id,
        "status": "pending",
        "message": message,
        "mode": mode,
        "remote": remote,
        "refspec": refspec,
        "cloudflareUrl": cloudflare_url,
        "createdAt": now,
        "updatedAt": now,
        "error": "",
        "logs": [],
        "steps": steps,
    }
    with PUBLISH_LOCK:
        PUBLISH_TASKS[task_id] = task
    return task


def _snapshot_publish_task(task_id: str) -> dict | None:
    with PUBLISH_LOCK:
        task = PUBLISH_TASKS.get(task_id)
        if not task:
            return None
        return json.loads(json.dumps(task))


def _update_publish_task(task_id: str, **kwargs) -> None:
    with PUBLISH_LOCK:
        task = PUBLISH_TASKS.get(task_id)
        if not task:
            return
        task.update(kwargs)
        task["updatedAt"] = _now()


def _set_publish_step(task_id: str, key: str, status: str, detail: str = "") -> None:
    with PUBLISH_LOCK:
        task = PUBLISH_TASKS.get(task_id)
        if not task:
            return
        for step in task.get("steps", []):
            if step.get("key") == key:
                step["status"] = status
                if detail:
                    step["detail"] = detail
                break
        task["updatedAt"] = _now()


def _append_publish_log(task_id: str, cmd: str, code: int, output: str) -> None:
    with PUBLISH_LOCK:
        task = PUBLISH_TASKS.get(task_id)
        if not task:
            return
        task["logs"].append({"time": _now(), "cmd": cmd, "code": code, "output": (output or "").strip()})
        task["updatedAt"] = _now()


def _run_publish_task(
    task_id: str,
    message: str,
    remote: str,
    refspec: str,
    git_ssh_command: str = "",
    mode: str = "git",
    cloudflare_url: str = "",
    publish_token: str = "",
) -> None:
    _update_publish_task(task_id, status="running")
    env = {}
    if git_ssh_command.strip():
        env["GIT_SSH_COMMAND"] = git_ssh_command.strip()

    try:
        _set_publish_step(task_id, "export_seed", "running")
        payload = _get_bootstrap_payload()
        _write_seed_json(payload)
        _set_publish_step(task_id, "export_seed", "success")

        if mode == "api":
            _set_publish_step(task_id, "api_publish", "running")
            code, out = _publish_to_cloudflare_api(cloudflare_url, publish_token, payload, timeout_sec=35)
            _append_publish_log(task_id, f"POST {cloudflare_url}", code, out)
            if code < 200 or code >= 300:
                _set_publish_step(task_id, "api_publish", "failed", "Cloudflare API 推送失败")
                _update_publish_task(task_id, status="failed", error=(out or "").strip())
                return
            _set_publish_step(task_id, "api_publish", "success")
            _update_publish_task(task_id, status="success")
            return

        _set_publish_step(task_id, "git_add", "running")
        code, out = _run_git(["git", "add", "data/seed.json"], extra_env=env)
        _append_publish_log(task_id, "git add data/seed.json", code, out)
        if code != 0:
            _set_publish_step(task_id, "git_add", "failed", "git add 失败")
            _update_publish_task(task_id, status="failed", error=(out or "").strip())
            return
        _set_publish_step(task_id, "git_add", "success")

        _set_publish_step(task_id, "git_check", "running")
        code, out = _run_git(["git", "diff", "--cached", "--quiet"], extra_env=env)
        _append_publish_log(task_id, "git diff --cached --quiet", code, out)
        has_changes = code != 0
        _set_publish_step(task_id, "git_check", "success", "有变更" if has_changes else "无文件变更，继续执行推送")

        if has_changes:
            _set_publish_step(task_id, "git_commit", "running")
            code, out = _run_git(["git", "commit", "-m", message], extra_env=env)
            _append_publish_log(task_id, f'git commit -m "{message}"', code, out)
            if code != 0:
                _set_publish_step(task_id, "git_commit", "failed", "git commit 失败")
                _update_publish_task(task_id, status="failed", error=(out or "").strip())
                return
            _set_publish_step(task_id, "git_commit", "success")
        else:
            _set_publish_step(task_id, "git_commit", "success", "无需提交")

        _set_publish_step(task_id, "git_push", "running")
        code, out = _run_git(["git", "push", remote, refspec], extra_env=env, timeout_sec=90)
        _append_publish_log(task_id, f"git push {remote} {refspec}", code, out)
        if code != 0:
            _set_publish_step(task_id, "git_push", "failed", "git push 失败")
            _update_publish_task(task_id, status="failed", error=(out or "").strip())
            return
        _set_publish_step(task_id, "git_push", "success")
        _update_publish_task(task_id, status="success")
    except Exception as e:
        _update_publish_task(task_id, status="failed", error=str(e))


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(v, default=None):
    if v is None:
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    s = str(v).strip()
    if not s:
        return default
    try:
        return int(float(s))
    except ValueError:
        return default


def _normalize_type(v) -> str:
    s = str(v or "").strip().lower()
    if s in ("pub", "public", "公办"):
        return "pub"
    if s in ("pri", "private", "民办"):
        return "pri"
    return "pub"


def _normalize_tier(v) -> str:
    s = str(v or "").strip().upper().replace(" ", "")
    if s in ("T1", "T2", "T3"):
        return s
    if s in ("1", "2", "3"):
        return f"T{s}"
    return "T3"


def _normalize_status(v) -> str:
    s = str(v or "").strip().lower()
    if s in ("hot", "超额", "超额摇号"):
        return "hot"
    if s in ("cool", "全录", "全部录取"):
        return "cool"
    return "normal"


def _build_school_items(payload: dict) -> list[dict]:
    items = []
    sd = payload.get("SD", [])
    pr = payload.get("PR", {})
    tf = payload.get("TF", {})
    for row in sd:
        if not isinstance(row, list) or not row:
            continue
        name = row[0]
        info = pr.get(name) if isinstance(pr, dict) else None
        fee = tf.get(name) if isinstance(tf, dict) else None
        items.append(
            {
                "name": name,
                "district": row[1] if len(row) > 1 else "",
                "type": row[2] if len(row) > 2 else "",
                "lotteryLow": row[3] if len(row) > 3 else None,
                "lotteryHigh": row[4] if len(row) > 4 else None,
                "recommend": row[5] if len(row) > 5 else None,
                "desc": row[6] if len(row) > 6 else "",
                "lat": row[7] if len(row) > 7 else None,
                "lng": row[8] if len(row) > 8 else None,
                "status": row[9] if len(row) > 9 else "normal",
                "tier": row[10] if len(row) > 10 else "T3",
                "admission2025": row[11] if len(row) > 11 else None,
                "maxLottery2025": row[12] if len(row) > 12 else None,
                "sourceUrl": row[13] if len(row) > 13 else "",
                "profile": info or {},
                "tuition": fee or {},
            }
        )
    return items


def _batch_update_school_tiers(updates: list[dict]) -> dict:
    payload = _get_bootstrap_payload()
    sd = payload.get("SD", [])
    update_map = {}
    for item in updates:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        tier = _normalize_tier(item.get("tier"))
        if not name:
            continue
        update_map[name] = tier
    if not update_map:
        return {"updated": 0, "missing": []}

    updated = 0
    existing_names = set()
    for i, row in enumerate(sd):
        if not isinstance(row, list) or not row:
            continue
        name = row[0]
        existing_names.add(name)
        if name in update_map:
            while len(row) <= 10:
                row.append(None)
            old_tier = _normalize_tier(row[10])
            new_tier = update_map[name]
            if old_tier != new_tier:
                row[10] = new_tier
                sd[i] = row
                updated += 1
    missing = [n for n in update_map.keys() if n not in existing_names]
    if updated > 0:
        payload["SD"] = sd
        _replace_payload(payload)
    return {"updated": updated, "missing": missing}


def _apply_school_changes(changes: dict) -> dict:
    payload = _get_bootstrap_payload()
    sd = payload.get("SD", [])
    pr = payload.get("PR", {})
    tf = payload.get("TF", {})

    tier_updates = changes.get("tierUpdates") or []
    rename_updates = changes.get("renameUpdates") or []
    delete_names = changes.get("deleteNames") or []
    if not isinstance(tier_updates, list):
        raise ValueError("tierUpdates 必须是数组")
    if not isinstance(rename_updates, list):
        raise ValueError("renameUpdates 必须是数组")
    if not isinstance(delete_names, list):
        raise ValueError("deleteNames 必须是数组")

    tier_map = {}
    for item in tier_updates:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        tier = _normalize_tier(item.get("tier"))
        if name:
            tier_map[name] = tier

    rename_map = {}
    for item in rename_updates:
        if not isinstance(item, dict):
            continue
        old_name = str(item.get("oldName") or "").strip()
        new_name = str(item.get("newName") or "").strip()
        if old_name and new_name and old_name != new_name:
            rename_map[old_name] = new_name

    delete_set = {str(x).strip() for x in delete_names if str(x).strip()}
    existing_names = {row[0] for row in sd if isinstance(row, list) and row}
    rename_conflicts = []
    for old_name, new_name in rename_map.items():
        # 仅允许改成不存在的名字，避免覆盖另一所学校
        if new_name in existing_names and new_name != old_name:
            rename_conflicts.append({"oldName": old_name, "newName": new_name, "reason": "newName 已存在"})
    if rename_conflicts:
        raise ValueError("存在重名冲突，请先处理： " + ", ".join([f"{x['oldName']}->{x['newName']}" for x in rename_conflicts]))

    new_sd = []
    tier_updated = 0
    renamed = 0
    deleted = 0
    for row in sd:
        if not isinstance(row, list) or not row:
            continue
        name = row[0]
        if name in delete_set:
            deleted += 1
            continue
        if name in tier_map:
            while len(row) <= 10:
                row.append(None)
            old_tier = _normalize_tier(row[10])
            new_tier = tier_map[name]
            if old_tier != new_tier:
                row[10] = new_tier
                # 同步 PR.tag 中的梯队文本，避免“列表是T1但详情口碑标签还是T2”
                if isinstance(pr, dict):
                    p_node = pr.get(name)
                    if isinstance(p_node, dict):
                        old_tag = p_node.get("tag")
                        if isinstance(old_tag, str) and old_tag.strip():
                            if re.search(r"\bT[123]\b", old_tag):
                                p_node["tag"] = re.sub(r"\bT[123]\b", new_tier, old_tag)
                            else:
                                p_node["tag"] = (old_tag + "·" + new_tier).strip("·")
                            pr[name] = p_node
                tier_updated += 1
        if name in rename_map:
            old_name = name
            new_name = rename_map[name]
            row[0] = new_name
            if isinstance(pr, dict) and old_name in pr:
                pr[new_name] = pr.pop(old_name)
            if isinstance(tf, dict) and old_name in tf:
                tf[new_name] = tf.pop(old_name)
            renamed += 1
        new_sd.append(row)

    for name in delete_set:
        if isinstance(pr, dict):
            pr.pop(name, None)
        if isinstance(tf, dict):
            tf.pop(name, None)

    missing_tier_names = [n for n in tier_map.keys() if n not in existing_names]
    missing_rename_names = [n for n in rename_map.keys() if n not in existing_names]
    missing_delete_names = [n for n in delete_set if n not in existing_names]

    changed = renamed > 0 or deleted > 0 or tier_updated > 0 or (len(delete_set) > len(missing_delete_names))
    if changed:
        payload["SD"] = new_sd
        payload["PR"] = pr
        payload["TF"] = tf
        _replace_payload(payload)

    return {
        "renamed": renamed,
        "tierUpdated": tier_updated,
        "deleted": deleted,
        "missingRenameNames": missing_rename_names,
        "missingTierNames": missing_tier_names,
        "missingDeleteNames": missing_delete_names,
    }


def _extract_school_from_xlsx(content: bytes) -> list[list]:
    if load_workbook is None:
        raise ValueError("openpyxl 未安装，无法解析 .xlsx")
    wb = load_workbook(filename=BytesIO(content), data_only=True, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = None
    for r in rows:
        vals = [str(x).strip() if x is not None else "" for x in r]
        if any(vals):
            header = vals
            break
    if not header:
        return []

    aliases = {
        "name": {"name", "学校名", "学校名称"},
        "district": {"district", "区", "区域"},
        "type": {"type", "学校类型", "类型", "公办民办"},
        "tier": {"tier", "梯队"},
        "lottery_low": {"lotterylow", "中签率低", "中签率下限", "low"},
        "lottery_high": {"lotteryhigh", "中签率高", "中签率上限", "high"},
        "recommend": {"recommend", "推荐度"},
        "desc": {"desc", "简介", "描述"},
        "lat": {"lat", "纬度"},
        "lng": {"lng", "经度"},
        "status": {"status", "状态"},
        "admission_2025": {"admission2025", "2025录取数", "录取数2025"},
        "max_lottery_2025": {"maxlottery2025", "2025最大摇号数", "最大摇号数2025"},
        "source_url": {"sourceurl", "参考信息来源网址", "来源网址", "source"},
    }

    def norm_key(s: str) -> str:
        return re.sub(r"\s+", "", s).lower().replace("-", "").replace("_", "")

    idx = {}
    norm_headers = [norm_key(h) for h in header]
    for canon, keys in aliases.items():
        keyset = {norm_key(k) for k in keys}
        for i, h in enumerate(norm_headers):
            if h in keyset:
                idx[canon] = i
                break

    if "name" not in idx:
        raise ValueError("Excel 缺少必需列：学校名称（name）")

    result = []
    for r in rows:
        vals = list(r)
        if not any(v is not None and str(v).strip() != "" for v in vals):
            continue

        def get(canon, default=None):
            i = idx.get(canon)
            if i is None or i >= len(vals):
                return default
            return vals[i]

        name = str(get("name", "")).strip()
        if not name:
            continue
        district = str(get("district", "")).strip()
        s_type = _normalize_type(get("type", "pub"))
        tier = _normalize_tier(get("tier", "T3"))
        low = _to_float(get("lottery_low"))
        high = _to_float(get("lottery_high"))
        recommend = _to_int(get("recommend"), default=3)
        desc = str(get("desc", "") or "").strip()
        lat = _to_float(get("lat"))
        lng = _to_float(get("lng"))
        status = _normalize_status(get("status", "normal"))
        admission_2025 = _to_int(get("admission_2025"), default=None)
        max_lottery_2025 = _to_int(get("max_lottery_2025"), default=None)
        source_url = str(get("source_url", "") or "").strip()
        row = [
            name,
            district,
            s_type,
            low,
            high,
            recommend,
            desc,
            lat,
            lng,
            status,
            tier,
            admission_2025,
            max_lottery_2025,
            source_url,
        ]
        result.append(row)
    return result


def _insert_proposals(source: str, evidence_url: str, proposals: list[dict]) -> dict:
    created = 0
    skipped = 0
    with _db_conn() as conn:
        for p in proposals:
            p_type = str(p.get("proposalType", "")).strip()
            p_key = str(p.get("proposalKey", "")).strip()
            if not p_type or not p_key or "newValue" not in p:
                skipped += 1
                continue
            try:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO proposals(
                      source, proposal_type, proposal_key, new_value_json, evidence_url, status, created_at
                    ) VALUES(?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        source,
                        p_type,
                        p_key,
                        json.dumps(p["newValue"], ensure_ascii=False),
                        p.get("evidenceUrl") or evidence_url,
                        _now(),
                    ),
                )
                if conn.total_changes > created:
                    created += 1
                else:
                    skipped += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
    return {"created": created, "skipped": skipped}


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "PrimarySchoolAdvisorBot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _to_count(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().lower().replace(",", "")
    if not s:
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([wk万千k]?)$", s)
    if not m:
        try:
            return int(float(s))
        except ValueError:
            return None
    num = float(m.group(1))
    unit = m.group(2)
    if unit in ("w", "万"):
        num *= 10000
    elif unit in ("k", "千"):
        num *= 1000
    return int(num)


def _extract_xhs_meta(url: str) -> dict:
    html = _fetch_text(url)
    title = ""
    m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]*content=["\'](.*?)["\']', html, flags=re.I | re.S)
    if m:
        title = re.sub(r"\s+", " ", m.group(1)).strip()
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()

    published_at = ""
    date_patterns = [
        r"(20\d{2}-\d{1,2}-\d{1,2})",
        r"(20\d{2}/\d{1,2}/\d{1,2})",
        r"(20\d{2}年\d{1,2}月\d{1,2}日)",
    ]
    for p in date_patterns:
        mm = re.search(p, html)
        if mm:
            published_at = mm.group(1)
            break

    def pick_int(patterns):
        for p in patterns:
            mm = re.search(p, html, flags=re.I)
            if mm:
                val = _to_count(mm.group(1))
                if val is not None:
                    return val
        return None

    like_count = pick_int(
        [
            r'"liked_count"\s*:\s*"?([0-9]+(?:\.[0-9]+)?[wk万千k]?)"?',
            r'"like_count"\s*:\s*"?([0-9]+(?:\.[0-9]+)?[wk万千k]?)"?',
            r"点赞[^0-9]{0,6}([0-9]+(?:\.[0-9]+)?[wk万千k]?)",
        ]
    )
    fav_count = pick_int(
        [
            r'"collected_count"\s*:\s*"?([0-9]+(?:\.[0-9]+)?[wk万千k]?)"?',
            r'"collect_count"\s*:\s*"?([0-9]+(?:\.[0-9]+)?[wk万千k]?)"?',
            r"收藏[^0-9]{0,6}([0-9]+(?:\.[0-9]+)?[wk万千k]?)",
        ]
    )

    return {"title": title, "publishedAt": published_at, "likeCount": like_count, "favoriteCount": fav_count}


def _collect_xhs_proposals(items: list[dict], purpose: str) -> dict:
    proposals = []
    errors = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            errors.append({"index": i, "error": "item 必须是对象"})
            continue
        school_name = str(it.get("schoolName") or "").strip()
        url = str(it.get("url") or "").strip()
        if not school_name or not url:
            errors.append({"index": i, "error": "schoolName/url 不能为空"})
            continue
        tier = str(it.get("tier") or "").strip().upper()
        if tier:
            tier = _normalize_tier(tier)
        admission_2025 = _to_int(it.get("admission2025"), default=None)
        max_lottery_2025 = _to_int(it.get("maxLottery2025"), default=None)
        note = str(it.get("note") or "").strip()

        meta = {}
        fetch_error = ""
        try:
            meta = _extract_xhs_meta(url)
        except Exception as e:
            fetch_error = str(e)
            meta = {"title": "", "publishedAt": "", "likeCount": None, "favoriteCount": None}

        new_value = {
            "tier": tier or None,
            "admission2025": admission_2025,
            "maxLottery2025": max_lottery_2025,
            "sourceUrl": url,
            "xhsMeta": {
                **meta,
                "url": url,
                "purpose": purpose,
                "note": note,
                "fetchError": fetch_error,
                "capturedAt": _now(),
            },
        }
        proposals.append(
            {
                "proposalType": "patch_school_fields",
                "proposalKey": school_name,
                "newValue": new_value,
                "evidenceUrl": url,
            }
        )
    result = _insert_proposals(f"xhs:{purpose}", "", proposals)
    return {**result, "errors": errors, "submitted": len(items)}


def _collect_policy_html(source: dict) -> list[dict]:
    html = _fetch_text(source["url"])
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
    page_title = re.sub(r"\s+", " ", title_match.group(1).strip()) if title_match else source["name"]
    keywords = source.get("keywords") or []
    if keywords and not any(k in html for k in keywords):
        return []
    dates = set(re.findall(r"\b(20\d{2}-\d{1,2}-\d{1,2})\b", html))
    zh_dates = re.findall(r"(20\d{2}年\d{1,2}月\d{1,2}日)", html)
    dates.update(zh_dates)
    proposals = []
    for i, d in enumerate(sorted(dates)[:30]):
        key = f"{source['id']}::{d}::{i}"
        proposals.append(
            {
                "proposalType": "add_policy_event",
                "proposalKey": key,
                "newValue": {"date": d, "title": page_title, "source": source["name"], "url": source["url"]},
                "evidenceUrl": source["url"],
            }
        )
    return proposals


def _collect_school_json(source: dict) -> list[dict]:
    raw = _fetch_text(source["url"])
    data = json.loads(raw)
    if not isinstance(data, list):
        return []
    m = source.get("mapping") or {}
    proposals = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get(m.get("name", "name"))
        if not name:
            continue
        row = [
            name,
            item.get(m.get("district", "district"), ""),
            item.get(m.get("schoolType", "type"), "pub"),
            item.get(m.get("lotteryLow", "lotteryLow")),
            item.get(m.get("lotteryHigh", "lotteryHigh")),
            item.get(m.get("recommend", "recommend"), 3),
            item.get(m.get("desc", "desc"), ""),
            item.get(m.get("lat", "lat")),
            item.get(m.get("lng", "lng")),
            item.get(m.get("status", "status"), "normal"),
            item.get(m.get("tier", "tier"), "T3"),
        ]
        proposals.append(
            {
                "proposalType": "upsert_sd",
                "proposalKey": str(name),
                "newValue": row,
                "evidenceUrl": source["url"],
            }
        )
    return proposals


def _run_collect_once() -> dict:
    sources = _load_sources()
    summary = {"scannedSources": 0, "created": 0, "skipped": 0, "errors": []}
    for s in sources:
        if not s.get("enabled"):
            continue
        summary["scannedSources"] += 1
        try:
            proposals = []
            if s.get("type") == "policy_html":
                proposals = _collect_policy_html(s)
            elif s.get("type") == "school_json":
                proposals = _collect_school_json(s)
            result = _insert_proposals(s.get("name") or s.get("id") or "collector", s.get("url", ""), proposals)
            summary["created"] += result["created"]
            summary["skipped"] += result["skipped"]
        except Exception as e:
            summary["errors"].append({"source": s.get("id"), "error": str(e)})
    return summary


def _apply_single_proposal(payload: dict, row: sqlite3.Row) -> bool:
    changed = False
    p_type = row["proposal_type"]
    p_key = row["proposal_key"]
    new_value = json.loads(row["new_value_json"])

    if p_type == "upsert_sd":
        sd = payload["SD"]
        if not isinstance(new_value, list) or not new_value:
            return False
        for i, school in enumerate(sd):
            if isinstance(school, list) and school and school[0] == p_key:
                sd[i] = new_value
                return True
        sd.append(new_value)
        return True
    if p_type == "patch_school_fields":
        if not isinstance(new_value, dict):
            return False
        sd = payload["SD"]
        for i, school in enumerate(sd):
            if not (isinstance(school, list) and school and school[0] == p_key):
                continue
            while len(school) <= 13:
                school.append(None)
            changed = False
            tier_val = new_value.get("tier")
            if isinstance(tier_val, str) and tier_val.strip():
                t = _normalize_tier(tier_val)
                if school[10] != t:
                    school[10] = t
                    changed = True
            admission = _to_int(new_value.get("admission2025"), default=None)
            if admission is not None and school[11] != admission:
                school[11] = admission
                changed = True
            max_lottery = _to_int(new_value.get("maxLottery2025"), default=None)
            if max_lottery is not None and school[12] != max_lottery:
                school[12] = max_lottery
                changed = True

            source_url = str(new_value.get("sourceUrl") or "").strip()
            old_source = str(school[13] or "").strip()
            if source_url:
                if not old_source:
                    school[13] = source_url
                    changed = True
                elif source_url not in old_source:
                    school[13] = old_source + "；" + source_url
                    changed = True

            xhs_meta = new_value.get("xhsMeta")
            if isinstance(xhs_meta, dict):
                pr = payload.get("PR")
                if isinstance(pr, dict):
                    node = pr.get(p_key)
                    if not isinstance(node, dict):
                        node = {}
                    old = node.get("xhsSignals")
                    if not isinstance(old, list):
                        old = []
                    old.append(xhs_meta)
                    node["xhsSignals"] = old[-20:]
                    pr[p_key] = node
                    payload["PR"] = pr
                    changed = True
            if changed:
                sd[i] = school
            return changed
        return False
    if p_type == "upsert_pr":
        payload["PR"][p_key] = new_value
        return True
    if p_type == "upsert_tf":
        payload["TF"][p_key] = new_value
        return True
    if p_type == "set_dn":
        payload["DN"][p_key] = new_value
        return True
    if p_type == "add_policy_event":
        with _db_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO policy_events(
                  event_key, event_date, title, source, evidence_url, payload_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    p_key,
                    str(new_value.get("date") or ""),
                    str(new_value.get("title") or ""),
                    str(new_value.get("source") or row["source"]),
                    row["evidence_url"],
                    json.dumps(new_value, ensure_ascii=False),
                    _now(),
                ),
            )
            conn.commit()
        return False
    return changed


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length) if length > 0 else b"{}"
    return json.loads(raw.decode("utf-8"))


def _serve_admin_static(handler: BaseHTTPRequestHandler, p: str) -> bool:
    if p == "/admin" or p == "/admin/":
        p = "/admin/index.html"
    if not p.startswith("/admin/"):
        return False
    rel = p[len("/admin/") :]
    file_path = (ADMIN_DIR / rel).resolve()
    if not str(file_path).startswith(str(ADMIN_DIR.resolve())) or not file_path.exists():
        _json_response(handler, 404, {"error": "Not Found"})
        return True
    if file_path.suffix == ".html":
        ctype = "text/html; charset=utf-8"
    elif file_path.suffix == ".js":
        ctype = "application/javascript; charset=utf-8"
    elif file_path.suffix == ".css":
        ctype = "text/css; charset=utf-8"
    else:
        ctype = "text/plain; charset=utf-8"
    _text_response(handler, 200, file_path.read_text(encoding="utf-8"), ctype)
    return True


class Handler(BaseHTTPRequestHandler):
    def _redirect(self, location: str, code: int = 302) -> None:
        self.send_response(code)
        self.send_header("Location", location)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        p = urlparse(self.path)
        if p.path in ("/", "/index.html"):
            self._redirect("/admin/")
            return
        if _serve_admin_static(self, p.path):
            return
        if p.path == "/api/health":
            _json_response(self, 200, {"ok": True, "dbPath": str(DB_PATH), "sourcesPath": str(SOURCES_PATH)})
            return
        if p.path == "/api/bootstrap":
            _json_response(self, 200, _get_bootstrap_payload())
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
        if p.path == "/api/policy-events":
            with _db_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT id, event_key, event_date, title, source, evidence_url, payload_json, created_at
                    FROM policy_events
                    ORDER BY id DESC
                    LIMIT 300
                    """
                ).fetchall()
            items = []
            for r in rows:
                items.append(
                    {
                        "id": r["id"],
                        "eventKey": r["event_key"],
                        "date": r["event_date"],
                        "title": r["title"],
                        "source": r["source"],
                        "evidenceUrl": r["evidence_url"],
                        "payload": json.loads(r["payload_json"]),
                        "createdAt": r["created_at"],
                    }
                )
            _json_response(self, 200, {"count": len(items), "items": items})
            return
        if p.path == "/api/admin/sources":
            _json_response(self, 200, {"sources": _load_sources(), "path": str(SOURCES_PATH)})
            return
        if p.path == "/api/admin/proposals":
            q = parse_qs(p.query)
            status = q.get("status", ["pending"])[0]
            with _db_conn() as conn:
                rows = conn.execute(
                    """
                    SELECT id, source, proposal_type, proposal_key, new_value_json, evidence_url, status, note, created_at, reviewed_at
                    FROM proposals
                    WHERE (? = 'all' OR status = ?)
                    ORDER BY id DESC
                    LIMIT 1000
                    """,
                    (status, status),
                ).fetchall()
            items = []
            for r in rows:
                items.append(
                    {
                        "id": r["id"],
                        "source": r["source"],
                        "proposalType": r["proposal_type"],
                        "proposalKey": r["proposal_key"],
                        "newValue": json.loads(r["new_value_json"]),
                        "evidenceUrl": r["evidence_url"],
                        "status": r["status"],
                        "note": r["note"],
                        "createdAt": r["created_at"],
                        "reviewedAt": r["reviewed_at"],
                    }
                )
            _json_response(self, 200, {"count": len(items), "items": items})
            return
        if p.path == "/api/admin/schools":
            payload = _get_bootstrap_payload()
            items = _build_school_items(payload)
            q = parse_qs(p.query)
            district = str(q.get("district", [""])[0]).strip()
            school_type = str(q.get("type", [""])[0]).strip()
            tier = str(q.get("tier", [""])[0]).strip().upper()
            keyword = str(q.get("q", [""])[0]).strip().lower()

            def ok(it):
                if district and it["district"] != district:
                    return False
                if school_type and it["type"] != school_type:
                    return False
                if tier and str(it["tier"]).upper() != tier:
                    return False
                if keyword and keyword not in str(it["name"]).lower():
                    return False
                return True

            items = [x for x in items if ok(x)]
            items.sort(key=lambda x: (x.get("district", ""), x.get("tier", ""), x.get("name", "")))
            _json_response(self, 200, {"count": len(items), "items": items})
            return
        if p.path == "/api/admin/school-detail":
            q = parse_qs(p.query)
            name = str(q.get("name", [""])[0]).strip()
            if not name:
                _json_response(self, 400, {"error": "name 不能为空"})
                return
            payload = _get_bootstrap_payload()
            for it in _build_school_items(payload):
                if it["name"] == name:
                    _json_response(self, 200, {"ok": True, "item": it})
                    return
            _json_response(self, 404, {"error": "学校不存在"})
            return
        if p.path == "/api/admin/publish-online/status":
            q = parse_qs(p.query)
            task_id = str(q.get("taskId", [""])[0]).strip()
            if not task_id:
                _json_response(self, 400, {"error": "taskId 不能为空"})
                return
            task = _snapshot_publish_task(task_id)
            if not task:
                _json_response(self, 404, {"error": "任务不存在"})
                return
            _json_response(self, 200, {"ok": True, "task": task})
            return
        _json_response(self, 404, {"error": "Not Found"})

    def do_PUT(self) -> None:
        p = urlparse(self.path)
        try:
            body = _read_json_body(self)
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "请求体不是合法 JSON"})
            return

        if p.path == "/api/bootstrap":
            try:
                _replace_payload(body)
            except ValueError as e:
                _json_response(self, 400, {"error": str(e)})
                return
            _json_response(self, 200, {"ok": True})
            return

        if p.path == "/api/admin/sources":
            sources = body.get("sources")
            if not isinstance(sources, list):
                _json_response(self, 400, {"error": "sources 必须是数组"})
                return
            _save_sources(sources)
            _json_response(self, 200, {"ok": True, "count": len(sources)})
            return
        _json_response(self, 404, {"error": "Not Found"})

    def do_POST(self) -> None:
        p = urlparse(self.path)
        try:
            body = _read_json_body(self)
        except json.JSONDecodeError:
            _json_response(self, 400, {"error": "请求体不是合法 JSON"})
            return

        if p.path == "/api/admin/proposals/import":
            source = str(body.get("source") or "manual")
            evidence_url = str(body.get("evidenceUrl") or "")
            proposals = body.get("proposals")
            if not isinstance(proposals, list):
                _json_response(self, 400, {"error": "proposals 必须是数组"})
                return
            result = _insert_proposals(source, evidence_url, proposals)
            _json_response(self, 200, {"ok": True, **result})
            return

        if p.path == "/api/admin/schools/import-xlsx":
            filename = str(body.get("filename") or "upload.xlsx")
            content_b64 = body.get("contentBase64")
            mode = str(body.get("mode") or "proposals").strip().lower()
            if not isinstance(content_b64, str) or not content_b64:
                _json_response(self, 400, {"error": "contentBase64 不能为空"})
                return
            try:
                content = base64.b64decode(content_b64)
                rows = _extract_school_from_xlsx(content)
            except Exception as e:
                _json_response(self, 400, {"error": f"Excel 解析失败: {e}"})
                return

            if mode == "apply":
                payload = _get_bootstrap_payload()
                changed = 0
                for row in rows:
                    name = row[0]
                    updated = False
                    for i, old in enumerate(payload["SD"]):
                        if isinstance(old, list) and old and old[0] == name:
                            payload["SD"][i] = row
                            updated = True
                            break
                    if not updated:
                        payload["SD"].append(row)
                    changed += 1
                _replace_payload(payload)
                _json_response(self, 200, {"ok": True, "mode": "apply", "updated": changed})
                return

            proposals = []
            for row in rows:
                proposals.append(
                    {
                        "proposalType": "upsert_sd",
                        "proposalKey": row[0],
                        "newValue": row,
                        "evidenceUrl": filename,
                    }
                )
            result = _insert_proposals(f"excel:{filename}", filename, proposals)
            _json_response(self, 200, {"ok": True, "mode": "proposals", **result})
            return

        if p.path == "/api/admin/schools/tier-batch-update":
            updates = body.get("updates")
            if not isinstance(updates, list):
                _json_response(self, 400, {"error": "updates 必须是数组"})
                return
            result = _batch_update_school_tiers(updates)
            _json_response(self, 200, {"ok": True, **result})
            return

        if p.path == "/api/admin/schools/push-changes":
            try:
                result = _apply_school_changes(body)
            except ValueError as e:
                _json_response(self, 400, {"error": str(e)})
                return
            _json_response(self, 200, {"ok": True, **result})
            return

        if p.path == "/api/admin/publish-online":
            message = str(body.get("message") or "").strip()
            if not message:
                message = "chore: publish latest school data"
            mode = str(body.get("mode") or "api").strip().lower() or "api"
            if mode not in ("api", "git"):
                _json_response(self, 400, {"error": "mode 必须是 api 或 git"})
                return
            remote = str(body.get("remote") or "cf").strip() or "cf"
            refspec = str(body.get("refspec") or "cf-main:main").strip() or "cf-main:main"
            git_ssh_command = str(body.get("gitSshCommand") or "").strip()
            cloudflare_url = str(body.get("cloudflareUrl") or "https://school-advisor.pages.dev/api/admin/bootstrap").strip()
            publish_token = str(body.get("publishToken") or os.getenv("CF_PUBLISH_TOKEN", "")).strip()
            if mode == "api" and not publish_token:
                _json_response(self, 400, {"error": "缺少 publishToken（可在前端输入或设置 CF_PUBLISH_TOKEN）"})
                return
            task = _new_publish_task(message, remote, refspec, mode=mode, cloudflare_url=cloudflare_url)
            t = threading.Thread(
                target=_run_publish_task,
                args=(task["taskId"], message, remote, refspec, git_ssh_command, mode, cloudflare_url, publish_token),
                daemon=True,
            )
            t.start()
            _json_response(self, 200, {"ok": True, "taskId": task["taskId"], "task": task})
            return

        if p.path == "/api/admin/xhs/collect-proposals":
            items = body.get("items")
            purpose = str(body.get("purpose") or "tier2026").strip() or "tier2026"
            if not isinstance(items, list) or not items:
                _json_response(self, 400, {"error": "items 必须是非空数组"})
                return
            result = _collect_xhs_proposals(items, purpose)
            _json_response(self, 200, {"ok": True, **result})
            return

        if p.path == "/api/admin/collect/run":
            summary = _run_collect_once()
            _json_response(self, 200, {"ok": True, **summary})
            return

        if p.path == "/api/admin/proposals/review":
            ids = body.get("ids")
            action = str(body.get("action") or "").strip()
            note = str(body.get("note") or "")
            if not isinstance(ids, list) or not ids:
                _json_response(self, 400, {"error": "ids 必须是非空数组"})
                return
            if action not in ("approve", "reject"):
                _json_response(self, 400, {"error": "action 必须是 approve 或 reject"})
                return
            with _db_conn() as conn:
                marks = ",".join("?" for _ in ids)
                rows = conn.execute(
                    f"""
                    SELECT id, source, proposal_type, proposal_key, new_value_json, evidence_url
                    FROM proposals
                    WHERE status='pending' AND id IN ({marks})
                    """,
                    ids,
                ).fetchall()
                if action == "reject":
                    conn.execute(
                        f"""
                        UPDATE proposals
                        SET status='rejected', note=?, reviewed_at=?
                        WHERE status='pending' AND id IN ({marks})
                        """,
                        [note, _now(), *ids],
                    )
                    conn.commit()
                    _json_response(self, 200, {"ok": True, "updated": len(rows), "action": action})
                    return

            payload = _get_bootstrap_payload()
            payload_changed = False
            for r in rows:
                payload_changed = _apply_single_proposal(payload, r) or payload_changed
            if payload_changed:
                _replace_payload(payload)
            with _db_conn() as conn:
                marks = ",".join("?" for _ in ids)
                conn.execute(
                    f"""
                    UPDATE proposals
                    SET status='approved', note=?, reviewed_at=?
                    WHERE status='pending' AND id IN ({marks})
                    """,
                    [note, _now(), *ids],
                )
                conn.commit()
            _json_response(
                self,
                200,
                {"ok": True, "updated": len(rows), "action": action, "payloadChanged": payload_changed},
            )
            return
        _json_response(self, 404, {"error": "Not Found"})

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    _init_db()
    _ensure_default_sources()
    parser = argparse.ArgumentParser(description="Primary School Advisor API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"API running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
