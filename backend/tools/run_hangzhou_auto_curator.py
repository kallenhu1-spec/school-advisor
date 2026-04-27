#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_capture(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic Hangzhou auto curator pass")
    parser.add_argument("--qa-before", required=True, help="Path to pre-curator QA json")
    parser.add_argument("--report-out", required=True, help="Path to markdown report")
    parser.add_argument("--qa-after", required=True, help="Path to post-curator QA json")
    args = parser.parse_args()

    qa_before = load_json(Path(args.qa_before))
    report_path = Path(args.report_out)
    qa_after_path = Path(args.qa_after)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    steps = []
    rc, stdout, stderr = run_capture(["python3", "backend/tools/build_hangzhou_school_directory.py"])
    steps.append({"step": "build_hangzhou_school_directory", "rc": rc, "stderr": stderr.strip()})
    if rc != 0:
        raise SystemExit(stderr or stdout or "build_hangzhou_school_directory failed")

    rc, stdout, stderr = run_capture(["python3", "backend/tools/check_hangzhou_seed.py"])
    steps.append({"step": "check_hangzhou_seed", "rc": rc, "stderr": stderr.strip()})
    if rc != 0:
        raise SystemExit(stderr or stdout or "check_hangzhou_seed failed")

    qa_after_path.write_text(stdout, encoding="utf-8")
    qa_after = json.loads(stdout)

    admission_before = qa_before.get("privateAdmissionReadyCount", 0)
    admission_after = qa_after.get("privateAdmissionReadyCount", 0)
    tuition_before = qa_before.get("privateTuitionReadyCount", 0)
    tuition_after = qa_after.get("privateTuitionReadyCount", 0)
    profile_before = qa_before.get("profileMissingCount", 0)
    profile_after = qa_after.get("profileMissingCount", 0)

    lines = [
        "# Data Curator 自动执行报告",
        "",
        "## 本轮动作",
        "- 重新运行杭州 builder，应用现有官方名录与覆盖规则。",
        "- 重新运行杭州 QA，核对招生、学费和画像覆盖率。",
        "",
        "## 指标变化",
        f"- 民办招生覆盖：{admission_before} -> {admission_after}",
        f"- 民办学费覆盖：{tuition_before} -> {tuition_after}",
        f"- 画像缺失：{profile_before} -> {profile_after}",
        "",
        "## 当前说明",
        "- 这是不依赖远端 Codex 的本地 deterministic curator pass。",
        "- 若指标未变化，说明当前规则库还没有新的可落地覆盖项，需要继续补充官方来源或覆盖规则。",
        "",
        "## 下一步建议",
    ]

    if admission_after == admission_before and tuition_after == tuition_before and profile_after == profile_before:
        lines.append("- 优先扩充杭州民办招生/学费的覆盖规则与来源清单，再继续自动补数。")
    else:
        lines.append("- 继续保持 AUTO_CURATOR 开启，让夜班自动沿现有规则持续推进。")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
