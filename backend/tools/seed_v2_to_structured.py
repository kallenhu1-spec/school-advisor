#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def _safe_obj(v):
    return v if isinstance(v, dict) else {}


def _safe_list(v):
    return v if isinstance(v, list) else []


def _make_field(key, label, value, level, target, origin, method, links):
    out_links = []
    for lk in _safe_list(links):
        d = _safe_obj(lk)
        url = str(d.get("url") or "").strip()
        out_links.append({"label": str(d.get("label") or "来源"), "url": url})
    if not out_links:
        out_links = [{"label": "待补充", "url": ""}]
    return {
        "key": key,
        "label": label,
        "value": value,
        "currentLevel": level,
        "targetLevel": target,
        "origin": origin,
        "method": method,
        "links": out_links,
    }


def _school_to_structured(s: dict) -> dict:
    name = str(s.get("name") or "").strip()
    district = str(s.get("district") or "").strip()
    school_type = "民办" if str(s.get("type") or "") == "pri" else "公办"
    tier = str(s.get("tier") or "T3").strip() or "T3"
    lat = s.get("lat")
    lng = s.get("lng")
    desc = str(s.get("desc") or "").strip()

    admission = _safe_obj(s.get("admission"))
    admitted = admission.get("admitted")
    max_lottery = admission.get("maxLottery")
    rate = admission.get("rate")
    admission_source = str(admission.get("admissionSource") or "community").strip() or "community"
    admission_url = str(admission.get("admissionUrl") or "").strip()

    profile = _safe_obj(s.get("profile"))
    profile_level = str(profile.get("sourceLevel") or "ai-draft").strip() or "ai-draft"
    source_note = str(profile.get("sourceNote") or "").strip() or "结构化生产补齐"
    tag = str(profile.get("tag") or "").strip()
    philosophy = profile.get("philosophy")
    path = _safe_list(profile.get("path"))
    pros = _safe_list(profile.get("pros"))
    cons = _safe_list(profile.get("cons"))

    links = _safe_obj(s.get("links"))
    xhs = str(links.get("xhs") or "").strip()
    xhs_link = ""
    if xhs:
        xhs_link = "https://www.xiaohongshu.com/search_result?keyword=" + xhs

    identity_fields = [
        _make_field(
            "schoolName",
            "学校",
            str(s.get("officialName") or name),
            "official",
            "official",
            "seed_v2 基础信息",
            "学校正式名称映射",
            [{"label": "主来源", "url": admission_url}] if admission_url else [],
        ),
        _make_field("district", "区域", district, "official", "official", "seed_v2 区域字段", "结构化映射", []),
        _make_field("schoolType", "类型", school_type, "official", "official", "seed_v2 类型字段", "结构化映射", []),
        _make_field(
            "tier",
            "梯队",
            tier,
            "community",
            "verified",
            "区内口碑与历史经验",
            "后续需结合公开榜单复核",
            [{"label": "社区检索", "url": xhs_link}] if xhs_link else [],
        ),
        _make_field(
            "coord",
            "坐标",
            f"{lat},{lng}" if lat is not None and lng is not None else "",
            "official" if lat is not None and lng is not None else "ai-draft",
            "official",
            "seed_v2 坐标",
            "地理编码/地图补充",
            [],
        ),
    ]

    admission_fields = [
        _make_field(
            "lotteryRange",
            "中签率",
            str(rate) if rate is not None else "",
            admission_source if rate is not None else "ai-draft",
            "verified",
            "录取数与报名上限计算",
            "admitted/maxLottery",
            [{"label": "官方来源", "url": admission_url}] if admission_url else [],
        ),
        _make_field(
            "admission2025",
            "2025录取数",
            admitted if admitted is not None else "",
            admission_source if admitted is not None else "ai-draft",
            "official",
            "官方抽取/seed_v2",
            "字段映射",
            [{"label": "官方来源", "url": admission_url}] if admission_url else [],
        ),
        _make_field(
            "maxLottery2025",
            "2025最大摇号数",
            max_lottery if max_lottery is not None else "",
            admission_source if max_lottery is not None else "community",
            "verified",
            "公开统计/历史口径",
            "字段映射",
            [{"label": "官方来源", "url": admission_url}] if admission_url else [{"label": "社区检索", "url": xhs_link}] if xhs_link else [],
        ),
    ]

    profile_fields = [
        _make_field(
            "desc",
            "简介",
            desc,
            profile_level if desc else "ai-draft",
            "verified",
            source_note,
            "结构化摘要",
            [{"label": "社区检索", "url": xhs_link}] if xhs_link else [],
        ),
        _make_field(
            "tag",
            "标签",
            tag,
            profile_level if tag else "ai-draft",
            "verified",
            source_note,
            "结构化标签",
            [{"label": "社区检索", "url": xhs_link}] if xhs_link else [],
        ),
        _make_field(
            "philosophy",
            "教育理念",
            philosophy if philosophy is not None else "",
            "official" if philosophy else "ai-draft",
            "official",
            source_note,
            "官网理念抽取/复核",
            [{"label": "官方来源", "url": admission_url}] if admission_url else [{"label": "社区检索", "url": xhs_link}] if xhs_link else [],
        ),
        _make_field("path", "升学路径", path, profile_level if path else "ai-draft", "official", source_note, "路径梳理", [{"label": "社区检索", "url": xhs_link}] if xhs_link else []),
        _make_field("pros", "优点", pros, profile_level if pros else "ai-draft", "verified", source_note, "证据归纳", [{"label": "社区检索", "url": xhs_link}] if xhs_link else []),
        _make_field("cons", "注意点", cons, profile_level if cons else "ai-draft", "verified", source_note, "证据归纳", [{"label": "社区检索", "url": xhs_link}] if xhs_link else []),
        _make_field("xhs", "小红书检索词", xhs, "community" if xhs else "ai-draft", "community", "seed_v2.links.xhs", "检索词直传", [{"label": "小红书检索", "url": xhs_link}] if xhs_link else []),
    ]

    return {
        "schoolName": name,
        "categories": [
            {"category": "identity", "title": "第一类 学校身份及基础信息", "fields": identity_fields},
            {"category": "admission", "title": "第二类 招生数据信息", "fields": admission_fields},
            {"category": "profile", "title": "第三类 详细介绍及口碑信息", "fields": profile_fields},
        ],
    }


def main():
    ap = argparse.ArgumentParser(description="Generate schools_structured_v1.jsonl from seed_v2 files")
    ap.add_argument("--inputs", nargs="+", required=True, help="seed_v2 files")
    ap.add_argument("--output", default="data/curation/schools_structured_v1.jsonl")
    args = ap.parse_args()

    out_path = Path(args.output)
    rows = []
    seen = set()
    for p in args.inputs:
        path = Path(p)
        if not path.exists():
            continue
        obj = json.loads(path.read_text(encoding="utf-8"))
        for s in _safe_list(obj.get("schools")):
            name = str(_safe_obj(s).get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            rows.append(_school_to_structured(_safe_obj(s)))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps({"ok": True, "output": str(out_path), "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
