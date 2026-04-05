#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "backend" / "tools"


def _run(cmd: list[str]) -> dict:
    p = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = (p.stdout or "").strip()
    return {"cmd": cmd, "code": p.returncode, "output": out}


def main():
    ap = argparse.ArgumentParser(description="Data-curator end-to-end pipeline")
    ap.add_argument("--scope", default="district", choices=["district", "school", "city"])
    ap.add_argument("--district", default="", help="district code, e.g. yangpu")
    ap.add_argument("--school-name", default="", help="single school mode")
    ap.add_argument("--city", default="shanghai", help="city code/name, default shanghai")
    ap.add_argument("--index", default="data/curation/official_pdf_index_2025.json", help="task E index json")
    ap.add_argument("--official-output", default="data/curation/official_admission_extract_2025.jsonl")
    ap.add_argument("--structured-input", default="data/curation/schools_structured_v1.jsonl")
    ap.add_argument("--proposals-output", default="data/curation/proposals_from_structured.json")
    ap.add_argument("--bootstrap-structured-from", nargs="*", default=[], help="seed_v2 files used to bootstrap structured jsonl")
    ap.add_argument("--no-auto-bootstrap-structured", action="store_true", help="disable auto bootstrap for missing structured file")
    ap.add_argument("--seed-v1", default="data/seed.json")
    ap.add_argument("--seed-v2-output", default="", help="default: data/seed_v2_<district>.json")
    ap.add_argument("--skip-task-e", action="store_true")
    ap.add_argument("--skip-proposals", action="store_true")
    ap.add_argument("--skip-seed-v2", action="store_true")
    args = ap.parse_args()

    py = sys.executable
    district = str(args.district).strip()
    school_name = str(args.school_name).strip()
    city = str(args.city).strip() or "shanghai"
    scope = str(args.scope).strip()

    if scope == "district" and not district:
        raise SystemExit("--scope district 时必须提供 --district")
    if scope == "school" and not school_name:
        raise SystemExit("--scope school 时必须提供 --school-name")

    if args.seed_v2_output:
        seed_v2_output = args.seed_v2_output
    else:
        if scope == "district":
            seed_v2_output = f"data/seed_v2_{district}.json"
        elif scope == "school":
            safe_name = "".join(ch if ch.isalnum() else "_" for ch in school_name).strip("_") or "school"
            seed_v2_output = f"data/seed_v2_school_{safe_name}.json"
        else:
            seed_v2_output = f"data/seed_v2_city_{city}.json"

    steps = []

    structured_path = Path(args.structured_input)
    if not structured_path.exists() and not args.no_auto_bootstrap_structured:
        bootstrap_inputs = [str(Path(x)) for x in args.bootstrap_structured_from if str(x).strip()]
        if not bootstrap_inputs:
            if scope == "district":
                candidate = ROOT / "data" / f"seed_v2_{district}.json"
                if candidate.exists():
                    bootstrap_inputs.append(str(candidate))
            elif scope == "school":
                safe_name = "".join(ch if ch.isalnum() else "_" for ch in school_name).strip("_") or "school"
                candidate = ROOT / "data" / f"seed_v2_school_{safe_name}.json"
                if candidate.exists():
                    bootstrap_inputs.append(str(candidate))
            else:
                candidate = ROOT / "data" / f"seed_v2_city_{city}.json"
                if candidate.exists():
                    bootstrap_inputs.append(str(candidate))
        if bootstrap_inputs:
            steps.append(
                _run(
                    [
                        py,
                        str(TOOLS / "seed_v2_to_structured.py"),
                        "--inputs",
                        *bootstrap_inputs,
                        "--output",
                        args.structured_input,
                    ]
                )
            )

    if not args.skip_task_e:
        steps.append(
            _run(
                [
                    py,
                    str(TOOLS / "task_e_extract_official.py"),
                    "--index",
                    args.index,
                    "--output",
                    args.official_output,
                ]
            )
        )

    if not args.skip_proposals:
        if structured_path.exists():
            steps.append(
                _run(
                    [
                        py,
                        str(TOOLS / "structured_to_proposals.py"),
                        "--input",
                        args.structured_input,
                        "--output",
                        args.proposals_output,
                        "--source",
                        f"data-curator:{district}:structured-v1",
                    ]
                )
            )
        else:
            steps.append(
                {
                    "cmd": [py, str(TOOLS / "structured_to_proposals.py"), "--input", args.structured_input],
                    "code": 0,
                    "output": f"skip: structured input not found: {args.structured_input}",
                }
            )

    if not args.skip_seed_v2:
        build_cmd = [
            py,
            str(TOOLS / "build_seed_v2_district.py"),
            "--seed-v1",
            args.seed_v1,
            "--official",
            args.official_output,
            "--structured",
            args.structured_input,
            "--output",
            seed_v2_output,
            "--city",
            city,
        ]
        if scope == "district":
            build_cmd.extend(["--district", district])
        elif scope == "school":
            build_cmd.extend(["--school-name", school_name])
        steps.append(
            _run(build_cmd)
        )

    ok = all(int(s.get("code", 1)) == 0 for s in steps)
    print(
        json.dumps(
            {
                "ok": ok,
                "district": district,
                "schoolName": school_name or None,
                "city": city,
                "scope": scope,
                "steps": steps,
                "artifacts": {
                    "officialExtract": args.official_output,
                    "structuredInput": args.structured_input,
                    "proposalsOutput": args.proposals_output,
                    "seedV2Output": seed_v2_output,
                },
            },
            ensure_ascii=False,
        )
    )
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
