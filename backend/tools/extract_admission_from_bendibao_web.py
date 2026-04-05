#!/usr/bin/env python3
import argparse
import difflib
import html
import json
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


UA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


DISTRICT_CN_TO_CODE = {
    "黄浦": "huangpu",
    "徐汇": "xuhui",
    "长宁": "changning",
    "静安": "jingan",
    "普陀": "putuo",
    "虹口": "hongkou",
    "杨浦": "yangpu",
    "浦东": "pudong",
    "闵行": "minhang",
    "宝山": "baoshan",
    "嘉定": "jiading",
    "金山": "jinshan",
    "松江": "songjiang",
    "青浦": "qingpu",
    "奉贤": "fengxian",
    "崇明": "chongming",
}


def fetch_text(url: str, timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers=UA_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def search_bendibao_articles(query: str, page: int = 1) -> List[Tuple[str, str]]:
    url = (
        "https://sh.bendibao.com/sou/index.php?action=ajax&q="
        + urllib.parse.quote(query)
        + f"&type=&page={page}&page_type=js"
    )
    req = urllib.request.Request(url, headers=UA_HEADERS | {"X-Requested-With": "XMLHttpRequest"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        obj = json.loads(resp.read().decode("utf-8", errors="ignore"))
    sou_html = obj.get("sou_list", "")
    pairs = []
    for m in re.finditer(r'<a[^>]+href="(https?://sh\.bendibao\.com/edu/\d+/\d+\.shtm)"[^>]*>([\s\S]*?)</a>', sou_html, re.I):
        href = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2))
        title = html.unescape(re.sub(r"\s+", " ", title)).strip()
        pairs.append((href, title))
    return pairs


def search_first_bendibao_article(query: str, district_cn: str) -> str:
    try:
        pairs = search_bendibao_articles(query, page=1)
    except Exception:
        return ""
    if not pairs:
        return ""
    # 优先标题命中区名
    for href, title in pairs:
        if district_cn and district_cn in title and "民办小学" in title:
            return href
    return pairs[0][0]


def clean_html_to_text(raw_html: str) -> str:
    raw = re.sub(r"<script[\s\S]*?</script>", " ", raw_html, flags=re.I)
    raw = re.sub(r"<style[\s\S]*?</style>", " ", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text


def discover_child_pages(base_url: str, raw_html: str) -> List[str]:
    # 实测跨页抓取会引入外区学校，默认只使用区主页面。
    _ = raw_html
    return [base_url]


def normalize_plan_name(name: str) -> str:
    n = "".join(str(name).split())
    n = re.sub(r"根据《关于[\s\S]*$", "", n)
    n = re.sub(r"[（(]?(走读|住宿)[)）]?", "", n)
    n = re.sub(r"(统招|本校教职工子女\*?|联合办学[^（(]*子女\*?)$", "", n)
    n = re.sub(r"[，,;；。]+$", "", n)
    return n.strip()


def parse_admissions_from_page(raw_html: str) -> Dict[str, Dict[str, int]]:
    text = clean_html_to_text(raw_html)
    parts = re.split(r"民办小学分类计划名称[：:]", text)
    by_school = defaultdict(lambda: {"all_max": 0, "tongzhao_max": 0})
    for seg in parts[1:]:
        plan_title = seg[:220]
        plan_title = re.split(r"(顺序号|报名号|电脑随机录取|备注|注：|说明：)", plan_title)[0]
        plan_title = "".join(plan_title.split())
        if not plan_title:
            continue
        if any(
            x in plan_title
            for x in ["员工子女", "教职工子女", "联合办学单位的员工子女", "本校教职工子女"]
        ):
            continue

        serials = [
            int(x)
            for x in re.findall(
                r"\s(\d{1,4})\s+\d{8,}\s+[\u4e00-\u9fa5·]{1,12}\s+[0-9Xx*]{8,}\s+电脑随机录取",
                seg,
            )
        ]
        if not serials:
            serials = [
                int(x)
                for x in re.findall(
                    r"\s(\d{1,4})\s+\d{8,}\s+[\u4e00-\u9fa5·]{1,12}\s+[0-9Xx*]{8,}",
                    seg,
                )
            ]
        if not serials:
            continue

        max_serial = max([x for x in serials if x < 5000], default=0)
        if max_serial <= 0:
            continue

        school = normalize_plan_name(plan_title)
        rec = by_school[school]
        rec["all_max"] = max(rec["all_max"], max_serial)
        if "统招" in plan_title:
            rec["tongzhao_max"] = max(rec["tongzhao_max"], max_serial)
    return by_school


def normalize_match_name(name: str) -> str:
    n = str(name or "")
    n = "".join(n.split())
    n = n.replace("上海市", "").replace("上海", "")
    n = n.replace("浦东新区", "").replace("新区", "").replace("区", "")
    n = n.replace("民办", "")
    n = n.replace("学校", "")
    n = n.replace("小学部", "").replace("小学", "")
    n = n.replace("外国语", "外语")
    n = re.sub(r"[（(].*?[)）]", "", n)
    n = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]", "", n)
    return n.lower()


def match_seed_school(
    extracted_name: str,
    district_code: str,
    pri_schools: List[Dict],
) -> Tuple[Optional[Dict], float]:
    target = normalize_match_name(extracted_name)
    if not target:
        return None, 0.0
    cands = [x for x in pri_schools if x.get("district") == district_code]
    if not cands:
        return None, 0.0

    best = None
    best_score = 0.0
    for c in cands:
        cname = c.get("name")
        sc = difflib.SequenceMatcher(None, target, normalize_match_name(cname)).ratio()
        if target and normalize_match_name(cname) and target in normalize_match_name(cname):
            sc = max(sc, 0.92)
        if sc > best_score:
            best = c
            best_score = sc
    return (best, best_score) if best_score >= 0.56 else (None, best_score)


def load_seed_sd(seed_path: Path) -> List[List]:
    obj = json.loads(seed_path.read_text(encoding="utf-8"))
    sd = obj.get("SD")
    if not isinstance(sd, list):
        raise RuntimeError("seed.json 的 SD 字段不是数组")
    return sd


def sd_private_school_dicts(sd: List[List]) -> List[Dict]:
    rows = []
    for row in sd:
        if not isinstance(row, list):
            continue
        if len(row) < 3:
            continue
        if row[2] != "pri":
            continue
        rows.append(
            {
                "row": row,
                "name": row[0] if len(row) > 0 else "",
                "district": row[1] if len(row) > 1 else "",
                "type": row[2] if len(row) > 2 else "",
            }
        )
    return rows


def ensure_row_len(row: List, min_len: int) -> None:
    while len(row) < min_len:
        row.append(None)


def main():
    ap = argparse.ArgumentParser(description="Extract 2025 admission counts from bendibao web pages and apply to seed.json")
    ap.add_argument("--district-pages", default="data/curation/bendibao_2025_district_pages.json")
    ap.add_argument("--out-jsonl", default="data/curation/official_admission_extract_2025_from_bendibao_web.jsonl")
    ap.add_argument("--seed", default="data/seed.json")
    ap.add_argument("--apply-seed", action="store_true")
    args = ap.parse_args()

    district_pages = json.loads(Path(args.district_pages).read_text(encoding="utf-8")).get("items", [])
    rows = []

    # district -> school name -> best admission count
    extracted_by_district = defaultdict(dict)

    for it in district_pages:
        district_cn = str(it.get("district") or "").strip()
        base_url = str(it.get("pageUrl") or "").strip()
        query = str(it.get("query") or "").strip()
        note = "ok"

        if not base_url:
            base_url = search_first_bendibao_article(query, district_cn) if query else ""
            if base_url:
                note = "resolved_from_search"
        if not base_url:
            rows.append(
                {
                    "district": district_cn,
                    "schoolName": "",
                    "admission2025": None,
                    "sourceUrl": "",
                    "reviewerNote": "page_not_found",
                    "extractionStatus": "blocked_or_pending",
                }
            )
            continue

        try:
            root_html = fetch_text(base_url)
            pages = discover_child_pages(base_url, root_html)
            pages = pages[:120]
            local_best = defaultdict(int)
            local_src = {}
            for page in pages:
                try:
                    raw = root_html if page == base_url else fetch_text(page)
                    parsed = parse_admissions_from_page(raw)
                    for school_name, v in parsed.items():
                        admitted = v["tongzhao_max"] or v["all_max"]
                        if admitted > local_best[school_name]:
                            local_best[school_name] = admitted
                            local_src[school_name] = page
                except Exception:
                    continue

            if not local_best:
                rows.append(
                    {
                        "district": district_cn,
                        "schoolName": "",
                        "admission2025": None,
                        "sourceUrl": base_url,
                        "reviewerNote": f"{note}:no_serial_rows",
                        "extractionStatus": "needs_manual_review",
                    }
                )
                continue

            for school_name, admitted in sorted(local_best.items(), key=lambda kv: kv[1], reverse=True):
                extracted_by_district[district_cn][school_name] = admitted
                rows.append(
                    {
                        "district": district_cn,
                        "schoolName": school_name,
                        "admission2025": admitted,
                        "sourceUrl": local_src.get(school_name, base_url),
                        "reviewerNote": f"{note}:max_row_serial_from_web",
                        "extractionStatus": "extracted",
                    }
                )
        except Exception as e:
            rows.append(
                {
                    "district": district_cn,
                    "schoolName": "",
                    "admission2025": None,
                    "sourceUrl": base_url,
                    "reviewerNote": f"fetch_failed:{e}",
                    "extractionStatus": "failed",
                }
            )

    out_path = Path(args.out_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    applied = 0
    unmatched = []
    if args.apply_seed:
        seed_path = Path(args.seed)
        seed_obj = json.loads(seed_path.read_text(encoding="utf-8"))
        sd = load_seed_sd(seed_path)
        pri_rows = sd_private_school_dicts(sd)
        for district_cn, schools in extracted_by_district.items():
            district_code = DISTRICT_CN_TO_CODE.get(district_cn)
            if not district_code:
                continue
            for extracted_name, admitted in schools.items():
                matched, score = match_seed_school(extracted_name, district_code, pri_rows)
                if not matched:
                    unmatched.append(
                        {
                            "district": district_cn,
                            "schoolName": extracted_name,
                            "admission2025": admitted,
                            "score": round(score, 3),
                        }
                    )
                    continue
                row = matched["row"]
                ensure_row_len(row, 14)
                old = row[11] if len(row) > 11 else None
                if old != admitted:
                    row[11] = admitted
                    # source url
                    row[13] = row[13] or ""
                    applied += 1
        seed_obj["SD"] = sd
        seed_obj["updatedAt"] = "2026-04-05"
        seed_path.write_text(json.dumps(seed_obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

        unmatched_path = out_path.with_suffix(".unmatched.json")
        unmatched_path.write_text(json.dumps(unmatched, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "ok": True,
        "outJsonl": str(out_path),
        "rows": len(rows),
        "extractedRows": len([x for x in rows if x.get("extractionStatus") == "extracted"]),
        "districtsWithAnyExtracted": len(set(x["district"] for x in rows if x.get("extractionStatus") == "extracted")),
        "appliedSeedUpdates": applied,
        "unmatchedCount": len(unmatched),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
