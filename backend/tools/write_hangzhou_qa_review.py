#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_review(qa: dict) -> str:
    school_count = qa.get("schoolCount", 0)
    missing_basics = qa.get("missingBasicsCount", 0)
    duplicates = qa.get("duplicateKeys") or []
    private_school_count = qa.get("privateSchoolCount", 0)
    admission_ready = qa.get("privateAdmissionReadyCount", 0)
    tuition_ready = qa.get("privateTuitionReadyCount", 0)
    profile_missing = qa.get("profileMissingCount", 0)
    admission_gap = max(private_school_count - admission_ready, 0)
    tuition_gap = max(private_school_count - tuition_ready, 0)

    blocking = []
    warnings = []
    passed = []

    if school_count > 0:
        passed.append(f"学校总数稳定：{school_count} 所")
    if missing_basics == 0:
        passed.append("P0 基础字段无缺失")
    else:
        blocking.append(f"P0 基础字段仍缺 {missing_basics} 项")
    if not duplicates:
        passed.append("重复学校为 0")
    else:
        blocking.append(f"重复学校 {len(duplicates)} 个")

    if admission_gap > 0:
        warnings.append(f"民办招生覆盖仍缺 {admission_gap} 所，需由 data-curator 主补、qa-reviewer 主验")
    else:
        passed.append("民办招生覆盖已齐")

    if tuition_gap > 0:
        warnings.append(f"民办学费覆盖仍缺 {tuition_gap} 所，需由 data-curator 主补、qa-reviewer 复核来源等级")
    else:
        passed.append("民办学费覆盖已齐")

    if profile_missing > 0:
        warnings.append(f"画像仍缺 {profile_missing} 所，继续放在招生和学费之后推进")
    else:
        passed.append("学校画像已齐")

    conclusion = "✅ **APPROVE**"
    if blocking:
        conclusion = "❌ **REQUEST CHANGES**"
    elif warnings:
        conclusion = "⚠️ **APPROVE WITH NOTES**"

    lines = [
        "### 验证结果摘要",
        f"✅ 通过：{len(passed)} 项",
        f"⚠️ 警告：{len(warnings)} 项",
        f"❌ 阻断：{len(blocking)} 项",
        "",
    ]

    if blocking:
        lines.append("### 阻断问题详情")
        for item in blocking:
            lines.append(f"- {item}")
        lines.append("")

    if warnings:
        lines.append("### 警告说明")
        for item in warnings:
            lines.append(f"- {item}")
        lines.append("")

    lines.append("### QA 最终结论")
    lines.append(conclusion)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Hangzhou nightly QA review markdown")
    parser.add_argument("--qa", required=True, help="Path to latest QA json")
    parser.add_argument("--out", required=True, help="Path to markdown output")
    args = parser.parse_args()

    qa = load_json(Path(args.qa))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_review(qa), encoding="utf-8")


if __name__ == "__main__":
    main()
