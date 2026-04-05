#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED_V1 = ROOT / "data" / "seed.json"
DEFAULT_OFFICIAL = ROOT / "data" / "curation" / "official_admission_extract_2025.jsonl"
DEFAULT_STRUCTURED = ROOT / "data" / "curation" / "schools_structured_v1.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_obj(v):
    return v if isinstance(v, dict) else {}


def _safe_list(v):
    return v if isinstance(v, list) else []


def _to_int(v):
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        return None


def _to_float(v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _calc_rate(admitted, max_lottery):
    if admitted is not None and max_lottery and max_lottery > 0:
        return round(admitted / max_lottery * 100, 2)
    return None


def _parse_school_type(v: str) -> str:
    s = str(v or "").strip().lower()
    if s in ("pub", "public", "公办"):
        return "pub"
    if s in ("pri", "private", "民办"):
        return "pri"
    return ""


def _parse_source_level(v: str) -> str:
    s = str(v or "").strip().lower()
    if s in ("official", "verified", "community", "ai-draft"):
        return s
    return ""


def _normalize_district(v: str) -> str:
    s = str(v or "").strip().lower()
    mapping = {
        "浦东": "pudong",
        "浦东新区": "pudong",
        "闵行": "minhang",
        "闵行区": "minhang",
        "徐汇": "xuhui",
        "徐汇区": "xuhui",
        "长宁": "changning",
        "长宁区": "changning",
        "静安": "jingan",
        "静安区": "jingan",
        "黄浦": "huangpu",
        "黄浦区": "huangpu",
        "普陀": "putuo",
        "普陀区": "putuo",
        "杨浦": "yangpu",
        "杨浦区": "yangpu",
        "虹口": "hongkou",
        "虹口区": "hongkou",
        "嘉定": "jiading",
        "嘉定区": "jiading",
        "青浦": "qingpu",
        "青浦区": "qingpu",
        "宝山": "baoshan",
        "宝山区": "baoshan",
        "金山": "jinshan",
        "金山区": "jinshan",
        "松江": "songjiang",
        "松江区": "songjiang",
        "奉贤": "fengxian",
        "奉贤区": "fengxian",
        "崇明": "chongming",
        "崇明区": "chongming",
    }
    return mapping.get(s, s)


def _first_url(field_obj: dict) -> str:
    f = _safe_obj(field_obj)
    for lk in _safe_list(f.get("links")):
        url = str(_safe_obj(lk).get("url") or "").strip()
        if url:
            return url
    src = _safe_obj(f.get("source"))
    for lk in _safe_list(src.get("links")):
        url = str(_safe_obj(lk).get("url") or "").strip()
        if url:
            return url
    u = str(src.get("url") or "").strip()
    if u:
        return u
    return ""


def _field_level(field_obj: dict) -> str:
    f = _safe_obj(field_obj)
    lv = _parse_source_level(f.get("currentLevel"))
    if lv:
        return lv
    src = _safe_obj(f.get("source"))
    return _parse_source_level(src.get("currentLevel"))


def _parse_coord(v):
    if isinstance(v, str):
        m = re.match(r"\s*([-+]?\d+(?:\.\d+)?)\s*[,，]\s*([-+]?\d+(?:\.\d+)?)\s*$", v)
        if m:
            return float(m.group(1)), float(m.group(2))
    if isinstance(v, list) and len(v) >= 2:
        return _to_float(v[0]), _to_float(v[1])
    return None, None


def _build_v2_school(sd_row: list, pr_row: dict) -> dict:
    name = sd_row[0]
    source_url = sd_row[13] if len(sd_row) > 13 else None
    admitted = sd_row[11] if len(sd_row) > 11 else None
    max_lottery = sd_row[12] if len(sd_row) > 12 else None
    rate = _calc_rate(_to_int(admitted), _to_int(max_lottery))
    if rate is None and len(sd_row) > 3 and isinstance(sd_row[3], (int, float)):
        rate = float(sd_row[3])
    admission = None
    if admitted is not None or max_lottery is not None or rate is not None or source_url:
        admission = {
            "rate": rate,
            "rateYear": 2025,
            "admitted": _to_int(admitted),
            "maxLottery": _to_int(max_lottery),
            "admissionSource": "official" if source_url else "community",
            "admissionUrl": source_url or None,
        }

    p = _safe_obj(pr_row)
    profile = {
        "tag": str(p.get("tag") or "").strip(),
        "philosophy": (str(p.get("slogan") or "").strip() or None),
        "path": _safe_list(p.get("path")),
        "pros": _safe_list(p.get("pros")),
        "cons": _safe_list(p.get("cons")),
        "sourceLevel": _parse_source_level(p.get("sourceLevel")) or "ai-draft",
        "sourceNote": str(p.get("sourceNote") or "").strip() or "基于 seed v1 导入，待补充真实来源",
    }

    if not any([profile["tag"], profile["philosophy"], profile["path"], profile["pros"], profile["cons"]]):
        profile = None

    return {
        "name": name,
        "officialName": str(name or "").strip(),
        "district": sd_row[1] if len(sd_row) > 1 else "",
        "type": sd_row[2] if len(sd_row) > 2 else "",
        "tier": sd_row[10] if len(sd_row) > 10 else "T3",
        "lat": sd_row[7] if len(sd_row) > 7 else None,
        "lng": sd_row[8] if len(sd_row) > 8 else None,
        "desc": str(sd_row[6] if len(sd_row) > 6 else "").strip(),
        "admission": admission,
        "profile": profile,
        "links": {
            "map": None,
            "xhs": str(p.get("xhs") or "").strip() or None,
            "dianping": None,
        },
    }


def _apply_official_extract(school_map: dict, district: str, official_path: Path) -> dict:
    stats = {"rows": 0, "matched": 0, "updated": 0}
    if not official_path.exists():
        return stats
    for line in official_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except Exception:
            continue
        stats["rows"] += 1
        row_district = _normalize_district(str(row.get("district") or "").strip())
        if row_district != district:
            continue
        name = str(row.get("schoolName") or "").strip()
        if not name or name not in school_map:
            continue
        stats["matched"] += 1
        school = school_map[name]
        admission = _safe_obj(school.get("admission"))
        if not admission:
            admission = {
                "rate": None,
                "rateYear": 2025,
                "admitted": None,
                "maxLottery": None,
                "admissionSource": "official",
                "admissionUrl": None,
            }
        before = json.dumps(admission, ensure_ascii=False, sort_keys=True)
        ai = _to_int(row.get("admission2025"))
        if ai is not None:
            admission["admitted"] = ai
        admission["admissionSource"] = "official"
        pdf_url = str(row.get("pdfUrl") or "").strip()
        if pdf_url:
            admission["admissionUrl"] = pdf_url
        admission["rateYear"] = 2025
        admission["rate"] = _calc_rate(admission.get("admitted"), admission.get("maxLottery"))
        school["admission"] = admission
        after = json.dumps(admission, ensure_ascii=False, sort_keys=True)
        if before != after:
            stats["updated"] += 1
    return stats


def _apply_structured(school_map: dict, structured_path: Path) -> dict:
    stats = {"rows": 0, "matched": 0, "updated": 0}
    if not structured_path.exists():
        return stats

    for line in structured_path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        stats["rows"] += 1
        name = str(_safe_obj(obj).get("schoolName") or "").strip()
        if not name or name not in school_map:
            continue
        stats["matched"] += 1
        school = school_map[name]
        before = json.dumps(school, ensure_ascii=False, sort_keys=True)

        fields = {}
        for cat in _safe_list(_safe_obj(obj).get("categories")):
            for f in _safe_list(_safe_obj(cat).get("fields")):
                key = str(_safe_obj(f).get("key") or "").strip()
                if key:
                    fields[key] = _safe_obj(f)

        f_school = _safe_obj(fields.get("schoolName"))
        school_name_val = str(f_school.get("value") or "").strip()
        if school_name_val:
            school["officialName"] = school_name_val

        f_type = _safe_obj(fields.get("schoolType"))
        st = _parse_school_type(f_type.get("value"))
        if st:
            school["type"] = st

        f_tier = _safe_obj(fields.get("tier"))
        tier = str(f_tier.get("value") or "").strip().upper()
        if tier in ("T1", "T2", "T3"):
            school["tier"] = tier

        f_coord = _safe_obj(fields.get("coord"))
        lat, lng = _parse_coord(f_coord.get("value"))
        if lat is not None and lng is not None:
            school["lat"], school["lng"] = lat, lng

        f_desc = _safe_obj(fields.get("desc"))
        desc = str(f_desc.get("value") or "").strip()
        if desc:
            school["desc"] = desc

        profile = _safe_obj(school.get("profile"))
        if not profile:
            profile = {"tag": "", "philosophy": None, "path": [], "pros": [], "cons": [], "sourceLevel": "ai-draft", "sourceNote": ""}

        f_tag = _safe_obj(fields.get("tag"))
        tag = str(f_tag.get("value") or "").strip()
        if tag:
            profile["tag"] = tag

        f_phi = _safe_obj(fields.get("philosophy"))
        phi = str(f_phi.get("value") or "").strip()
        if phi:
            profile["philosophy"] = phi

        for src_key in ("path", "pros", "cons"):
            f = _safe_obj(fields.get(src_key))
            val = f.get("value")
            if isinstance(val, list) and val:
                profile[src_key] = [str(x).strip() for x in val if str(x).strip()]
            elif isinstance(val, str) and val.strip():
                profile[src_key] = [x.strip() for x in val.split("|") if x.strip()]

        prof_level_candidates = [
            _field_level(fields.get("philosophy")),
            _field_level(fields.get("path")),
            _field_level(fields.get("pros")),
            _field_level(fields.get("cons")),
        ]
        prof_level_candidates = [x for x in prof_level_candidates if x]
        if prof_level_candidates:
            rank = {"ai-draft": 0, "community": 1, "verified": 2, "official": 3}
            profile["sourceLevel"] = sorted(prof_level_candidates, key=lambda x: rank.get(x, -1), reverse=True)[0]
        source_note_urls = []
        for k in ("philosophy", "path", "pros", "cons"):
            u = _first_url(fields.get(k))
            if u:
                source_note_urls.append(u)
        if source_note_urls:
            profile["sourceNote"] = "结构化证据来源：" + "; ".join(source_note_urls[:3])
        school["profile"] = profile

        admission = _safe_obj(school.get("admission"))
        if not admission:
            admission = {
                "rate": None,
                "rateYear": 2025,
                "admitted": None,
                "maxLottery": None,
                "admissionSource": "community",
                "admissionUrl": None,
            }

        f_adm = _safe_obj(fields.get("admission2025"))
        ai = _to_int(f_adm.get("value"))
        if ai is not None:
            admission["admitted"] = ai
        f_max = _safe_obj(fields.get("maxLottery2025"))
        mi = _to_int(f_max.get("value"))
        if mi is not None:
            admission["maxLottery"] = mi
        adm_level = _field_level(f_adm) or _field_level(f_max)
        if adm_level:
            admission["admissionSource"] = adm_level
        adm_url = _first_url(f_adm) or _first_url(f_max)
        if adm_url:
            admission["admissionUrl"] = adm_url
        if any([admission.get("admitted") is not None, admission.get("maxLottery") is not None, admission.get("admissionUrl")]):
            admission["rateYear"] = 2025
            admission["rate"] = _calc_rate(admission.get("admitted"), admission.get("maxLottery"))
            school["admission"] = admission

        school["links"] = _safe_obj(school.get("links"))
        fxhs = _safe_obj(fields.get("xhs"))
        xhs = str(fxhs.get("value") or "").strip()
        if xhs:
            school["links"]["xhs"] = xhs

        after = json.dumps(school, ensure_ascii=False, sort_keys=True)
        if before != after:
            stats["updated"] += 1
    return stats


def main():
    ap = argparse.ArgumentParser(description="Build seed_v2 bundle from seed v1 + official extract + structured schools")
    ap.add_argument("--district", default="", help="district code, e.g. yangpu")
    ap.add_argument("--school-name", default="", help="single school mode")
    ap.add_argument("--city", default="shanghai", help="city code/name, default shanghai")
    ap.add_argument("--seed-v1", default=str(DEFAULT_SEED_V1))
    ap.add_argument("--official", default=str(DEFAULT_OFFICIAL))
    ap.add_argument("--structured", default=str(DEFAULT_STRUCTURED))
    ap.add_argument("--output", default="", help="default: data/seed_v2_<district>.json")
    args = ap.parse_args()

    district = str(args.district or "").strip()
    school_name = str(args.school_name or "").strip()
    city = str(args.city or "").strip() or "shanghai"
    if not district and not school_name:
        # city mode: include all schools in seed_v1
        pass

    seed_v1_path = Path(args.seed_v1)
    official_path = Path(args.official)
    structured_path = Path(args.structured)
    if args.output:
        output_path = Path(args.output)
    else:
        if school_name:
            safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "_", school_name).strip("_") or "school"
            output_path = ROOT / "data" / f"seed_v2_school_{safe_name}.json"
        elif district:
            output_path = ROOT / "data" / f"seed_v2_{district}.json"
        else:
            output_path = ROOT / "data" / f"seed_v2_city_{city}.json"

    seed_v1 = json.loads(seed_v1_path.read_text(encoding="utf-8"))
    sd = _safe_list(seed_v1.get("SD"))
    pr = _safe_obj(seed_v1.get("PR"))

    schools = []
    for row in sd:
        if not (isinstance(row, list) and len(row) >= 2):
            continue
        if district and str(row[1]) != district:
            continue
        if school_name and str(row[0]) != school_name:
            continue
        schools.append(_build_v2_school(row, _safe_obj(pr.get(row[0]))))

    school_map = {s["name"]: s for s in schools}
    official_stats = _apply_official_extract(school_map, district, official_path) if district else {"rows": 0, "matched": 0, "updated": 0}
    structured_stats = _apply_structured(school_map, structured_path)

    out = {
        "version": "2.0",
        "generatedAt": _now(),
        "district": district or None,
        "city": city,
        "scope": "school" if school_name else ("district" if district else "city"),
        "schoolName": school_name or None,
        "dataNote": "由 data-curator pipeline 生成：seed_v1 + official_extract + structured_v1",
        "schools": schools,
        "TF": {},
        "DN": {},
        "pipelineMeta": {
            "seedV1": str(seed_v1_path),
            "officialExtract": str(official_path),
            "structuredInput": str(structured_path),
            "officialStats": official_stats,
            "structuredStats": structured_stats,
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "district": district,
                "schoolName": school_name or None,
                "city": city,
                "output": str(output_path),
                "schools": len(schools),
                "officialStats": official_stats,
                "structuredStats": structured_stats,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
