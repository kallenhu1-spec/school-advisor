#!/usr/bin/env python3
"""
seed.json (v1) → seed_v2.json + SQLite v2 表 迁移脚本

用法：
  python backend/tools/migrate_v1_to_v2.py                  # 只产出 seed_v2.json
  python backend/tools/migrate_v1_to_v2.py --write-db       # 同时写入 SQLite
  python backend/tools/migrate_v1_to_v2.py --district yangpu # 只迁移杨浦区
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
SEED_V1 = ROOT / "data" / "seed.json"
SEED_V2 = ROOT / "data" / "seed_v2.json"
DB_PATH = ROOT / "data" / "school_advisor.db"
SCHEMA_V2 = ROOT / "cloudflare" / "d1" / "schema_v2.sql"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _calc_rate(admitted, max_lottery):
    """中签率 = admitted / max_lottery * 100，保留两位小数"""
    if admitted is not None and max_lottery is not None and max_lottery > 0:
        return round(admitted / max_lottery * 100, 2)
    return None


def load_v1(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def convert_school(sd_row: list, pr_dict: dict, tf_dict: dict) -> Optional[dict]:
    """将一条 SD 位置数组 + PR 口碑 转为 v2 格式"""
    if not isinstance(sd_row, list) or len(sd_row) < 3:
        return None

    name = sd_row[0] if len(sd_row) > 0 else ""
    district = sd_row[1] if len(sd_row) > 1 else ""
    school_type = sd_row[2] if len(sd_row) > 2 else ""
    # SD[3] = rateLow, SD[4] = rateHigh — 都丢弃，rate 从 admitted/maxLottery 重算
    # SD[5] = score — 丢弃
    desc = sd_row[6] if len(sd_row) > 6 else ""
    lat = sd_row[7] if len(sd_row) > 7 else None
    lng = sd_row[8] if len(sd_row) > 8 else None
    # SD[9] = heat — 丢弃
    tier = sd_row[10] if len(sd_row) > 10 else "T3"
    admitted = sd_row[11] if len(sd_row) > 11 else None
    max_lottery = sd_row[12] if len(sd_row) > 12 else None

    # 计算中签率
    rate = _calc_rate(admitted, max_lottery)

    # admission 对象：如果完全没有数据就设为 null
    admission = None
    if admitted is not None or max_lottery is not None or rate is not None:
        admission = {
            "rate": rate,
            "rateYear": 2025,
            "admitted": admitted,
            "maxLottery": max_lottery,
            "admissionSource": "community",  # v1 数据默认标 community，等官方 PDF 核实后升级
            "admissionUrl": None,
        }

    # 从 PR 提取口碑
    pr = pr_dict.get(name, {}) if isinstance(pr_dict, dict) else {}
    profile = None
    if pr:
        path = pr.get("path", [])
        if isinstance(path, str):
            path = [path]
        profile = {
            "tag": pr.get("tag", ""),
            "philosophy": pr.get("slogan") or pr.get("philosophy"),
            "path": path if isinstance(path, list) else [],
            "pros": pr.get("pros", []) if isinstance(pr.get("pros"), list) else [],
            "cons": pr.get("cons", []) if isinstance(pr.get("cons"), list) else [],
            "sourceLevel": "ai-draft",
            "sourceNote": "AI生成，待真实来源核实",
        }

    # 链接
    xhs = pr.get("xhs") if pr else None
    links = {
        "map": None,
        "xhs": xhs,
        "dianping": None,
    }

    return {
        "name": name,
        "officialName": "",  # 待从官方 PDF 补充
        "district": district,
        "type": school_type,
        "tier": tier if isinstance(tier, str) else "T3",
        "lat": lat,
        "lng": lng,
        "desc": desc,
        "admission": admission,
        "profile": profile,
        "links": links,
    }


def migrate(v1_data: dict, district_filter: Optional[str] = None) -> dict:
    """将 v1 整体转为 v2 格式"""
    sd = v1_data.get("SD", [])
    pr = v1_data.get("PR", {})
    tf = v1_data.get("TF", {})
    dn = v1_data.get("DN", {})

    schools = []
    skipped = 0
    for row in sd:
        school = convert_school(row, pr, tf)
        if school is None:
            skipped += 1
            continue
        if district_filter and school["district"] != district_filter:
            continue
        schools.append(school)

    return {
        "version": "2.0",
        "generatedAt": _now(),
        "migratedFrom": "seed.json v1",
        "schools": schools,
        "stats": {
            "total": len(schools),
            "withAdmission": sum(1 for s in schools if s["admission"] is not None),
            "withProfile": sum(1 for s in schools if s["profile"] is not None),
            "skipped": skipped,
        },
        "TF": tf,
        "DN": dn,
    }


def write_to_db(v2_data: dict, db_path: Path) -> dict:
    """将 v2 数据写入 SQLite v2 表"""
    # 先建表
    schema_sql = SCHEMA_V2.read_text(encoding="utf-8")
    conn = sqlite3.connect(db_path)
    conn.executescript(schema_sql)

    now = _now()
    inserted_schools = 0
    inserted_admissions = 0
    inserted_profiles = 0

    for school in v2_data.get("schools", []):
        # 写 schools 表
        try:
            cur = conn.execute(
                """
                INSERT INTO schools (name, official_name, district, type, tier, lat, lng, desc_text,
                                     link_map, link_xhs, link_dianping, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name, district) DO UPDATE SET
                  official_name = excluded.official_name,
                  type = excluded.type,
                  tier = excluded.tier,
                  lat = excluded.lat,
                  lng = excluded.lng,
                  desc_text = excluded.desc_text,
                  link_map = excluded.link_map,
                  link_xhs = excluded.link_xhs,
                  link_dianping = excluded.link_dianping,
                  updated_at = excluded.updated_at
                """,
                (
                    school["name"],
                    school.get("officialName", ""),
                    school["district"],
                    school["type"],
                    school.get("tier", "T3"),
                    school.get("lat"),
                    school.get("lng"),
                    school.get("desc", ""),
                    (school.get("links") or {}).get("map"),
                    (school.get("links") or {}).get("xhs"),
                    (school.get("links") or {}).get("dianping"),
                    now,
                    now,
                ),
            )
            school_id = cur.lastrowid
            inserted_schools += 1
        except Exception as e:
            print(f"  跳过学校 {school['name']}: {e}", file=sys.stderr)
            continue

        # 确保拿到正确的 school_id（UPSERT 时 lastrowid 可能不对）
        row = conn.execute(
            "SELECT id FROM schools WHERE name = ? AND district = ?",
            (school["name"], school["district"]),
        ).fetchone()
        if row:
            school_id = row[0]

        # 写 admissions 表
        adm = school.get("admission")
        if adm and isinstance(adm, dict):
            try:
                conn.execute(
                    """
                    INSERT INTO admissions (school_id, year, admitted, max_lottery, rate,
                                            admission_source, admission_url, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(school_id, year) DO UPDATE SET
                      admitted = excluded.admitted,
                      max_lottery = excluded.max_lottery,
                      rate = excluded.rate,
                      admission_source = excluded.admission_source,
                      admission_url = excluded.admission_url,
                      updated_at = excluded.updated_at
                    """,
                    (
                        school_id,
                        adm.get("rateYear", 2025),
                        adm.get("admitted"),
                        adm.get("maxLottery"),
                        adm.get("rate"),
                        adm.get("admissionSource", "community"),
                        adm.get("admissionUrl"),
                        now,
                        now,
                    ),
                )
                inserted_admissions += 1
            except Exception as e:
                print(f"  跳过 admission {school['name']}: {e}", file=sys.stderr)

        # 写 profiles 表
        prof = school.get("profile")
        if prof and isinstance(prof, dict):
            try:
                conn.execute(
                    """
                    INSERT INTO profiles (school_id, tag, philosophy, path_json, pros_json, cons_json,
                                          source_level, source_note, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(school_id) DO UPDATE SET
                      tag = excluded.tag,
                      philosophy = excluded.philosophy,
                      path_json = excluded.path_json,
                      pros_json = excluded.pros_json,
                      cons_json = excluded.cons_json,
                      source_level = excluded.source_level,
                      source_note = excluded.source_note,
                      updated_at = excluded.updated_at
                    """,
                    (
                        school_id,
                        prof.get("tag", ""),
                        prof.get("philosophy"),
                        json.dumps(prof.get("path", []), ensure_ascii=False),
                        json.dumps(prof.get("pros", []), ensure_ascii=False),
                        json.dumps(prof.get("cons", []), ensure_ascii=False),
                        prof.get("sourceLevel", "ai-draft"),
                        prof.get("sourceNote"),
                        now,
                        now,
                    ),
                )
                inserted_profiles += 1
            except Exception as e:
                print(f"  跳过 profile {school['name']}: {e}", file=sys.stderr)

    conn.commit()
    conn.close()

    return {
        "schools": inserted_schools,
        "admissions": inserted_admissions,
        "profiles": inserted_profiles,
    }


def main():
    parser = argparse.ArgumentParser(description="seed.json v1 → seed_v2.json 迁移")
    parser.add_argument("--write-db", action="store_true", help="同时写入 SQLite v2 表")
    parser.add_argument("--district", type=str, default=None, help="只迁移指定区（如 yangpu）")
    parser.add_argument("--input", type=str, default=str(SEED_V1), help="输入文件路径")
    parser.add_argument("--output", type=str, default=str(SEED_V2), help="输出文件路径")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    print(f"读取 v1 数据: {input_path}")
    v1_data = load_v1(input_path)
    sd_count = len(v1_data.get("SD", []))
    pr_count = len(v1_data.get("PR", {}))
    print(f"  SD: {sd_count} 条, PR: {pr_count} 条")

    if args.district:
        print(f"  筛选区域: {args.district}")

    print("开始迁移...")
    v2_data = migrate(v1_data, district_filter=args.district)

    stats = v2_data["stats"]
    print(f"迁移完成:")
    print(f"  学校总数: {stats['total']}")
    print(f"  有招生数据: {stats['withAdmission']}")
    print(f"  有口碑数据: {stats['withProfile']}")
    print(f"  跳过: {stats['skipped']}")

    # 写 JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(v2_data, f, ensure_ascii=False, indent=2)
    print(f"已写入: {output_path}")

    # 写 DB
    if args.write_db:
        print(f"写入 SQLite: {DB_PATH}")
        db_stats = write_to_db(v2_data, DB_PATH)
        print(f"  写入 schools: {db_stats['schools']}")
        print(f"  写入 admissions: {db_stats['admissions']}")
        print(f"  写入 profiles: {db_stats['profiles']}")

    print("完成!")


if __name__ == "__main__":
    main()
