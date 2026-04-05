#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def _safe_list(v):
    return v if isinstance(v, list) else []


def _safe_obj(v):
    return v if isinstance(v, dict) else {}


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


def _find_field(school_obj: dict, key: str) -> dict:
    for cat in _safe_list(school_obj.get("categories")):
        for f in _safe_list(_safe_obj(cat).get("fields")):
            if _safe_obj(f).get("key") == key:
                return _safe_obj(f)
    return {}


def _first_link(field_obj: dict) -> str:
    src = _safe_obj(field_obj.get("source"))
    links = _safe_list(src.get("links"))
    for x in links:
        url = str(_safe_obj(x).get("url") or "").strip()
        if url:
            return url
    u = str(src.get("url") or "").strip()
    return u


def _build_patch_school_fields(school_obj: dict) -> tuple[dict, str]:
    tier = _safe_obj(_find_field(school_obj, "tier")).get("value")
    admission = _safe_obj(_find_field(school_obj, "admission2025")).get("value")
    max_lottery = _safe_obj(_find_field(school_obj, "maxLottery2025")).get("value")
    source_url = _first_link(_find_field(school_obj, "admission2025")) or _first_link(_find_field(school_obj, "schoolName"))
    new_value = {}
    if str(tier or "").strip():
        new_value["tier"] = str(tier).strip()
    ai = _to_int(admission)
    if ai is not None:
        new_value["admission2025"] = ai
    mi = _to_int(max_lottery)
    if mi is not None:
        new_value["maxLottery2025"] = mi
    if source_url:
        new_value["sourceUrl"] = source_url
    return new_value, source_url


def _build_patch_pr_fields(school_obj: dict) -> tuple[dict, str]:
    out = {}
    source_url = ""
    mapping = [
        ("desc", "desc"),
        ("philosophy", "slogan"),
        ("path", "path"),
        ("pros", "pros"),
        ("cons", "cons"),
    ]
    for field_key, pr_key in mapping:
        f = _find_field(school_obj, field_key)
        if not f:
            continue
        val = _safe_obj(f).get("value")
        if field_key in ("path", "pros", "cons"):
            out[pr_key] = _safe_list(val)
        else:
            out[pr_key] = str(val or "").strip()
        if not source_url:
            source_url = _first_link(f)

    hw_field = _find_field(school_obj, "hwStress")
    hw_val = str(_safe_obj(hw_field).get("value") or "").strip()
    if hw_val:
        # expected format: "3 / 3"
        parts = [x.strip() for x in hw_val.split("/") if x.strip()]
        if len(parts) >= 1:
            out["hw"] = _to_int(parts[0]) if _to_int(parts[0]) is not None else parts[0]
        if len(parts) >= 2:
            out["stress"] = _to_int(parts[1]) if _to_int(parts[1]) is not None else parts[1]
        if not source_url:
            source_url = _first_link(hw_field)

    return out, source_url


def _build_patch_tf_fields(school_obj: dict) -> tuple[dict, str]:
    tuition = _safe_obj(_find_field(school_obj, "tuition")).get("value")
    if not isinstance(tuition, dict):
        return {}, ""
    out = {}
    term = _to_int(tuition.get("term"))
    note = str(tuition.get("note") or "").strip()
    if term is not None:
        out["term"] = term
    if note:
        out["note"] = note
    source_url = _first_link(_find_field(school_obj, "tuition"))
    return out, source_url


def main():
    p = argparse.ArgumentParser(description="Convert schools_structured_v1.jsonl to proposals/import payload")
    p.add_argument("--input", required=True, help="JSONL path, each line is one school structured object")
    p.add_argument("--output", default="data/curation/proposals_from_structured.json", help="Output JSON payload path")
    p.add_argument("--source", default="data-curator:structured-v1", help="source name for proposals/import")
    args = p.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    proposals = []
    skipped = 0

    for i, line in enumerate(in_path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            skipped += 1
            continue
        name = str(_safe_obj(obj).get("schoolName") or "").strip()
        if not name:
            skipped += 1
            continue

        patch_sd, ev_sd = _build_patch_school_fields(obj)
        if patch_sd:
            proposals.append(
                {
                    "proposalType": "patch_school_fields",
                    "proposalKey": name,
                    "newValue": patch_sd,
                    "evidenceUrl": ev_sd,
                }
            )

        patch_pr, ev_pr = _build_patch_pr_fields(obj)
        if patch_pr:
            proposals.append(
                {
                    "proposalType": "patch_pr_fields",
                    "proposalKey": name,
                    "newValue": patch_pr,
                    "evidenceUrl": ev_pr,
                }
            )

        patch_tf, ev_tf = _build_patch_tf_fields(obj)
        if patch_tf:
            proposals.append(
                {
                    "proposalType": "patch_tf_fields",
                    "proposalKey": name,
                    "newValue": patch_tf,
                    "evidenceUrl": ev_tf,
                }
            )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"source": args.source, "proposals": proposals}
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "input": str(in_path), "output": str(out_path), "proposals": len(proposals), "skipped": skipped}, ensure_ascii=False))


if __name__ == "__main__":
    main()

