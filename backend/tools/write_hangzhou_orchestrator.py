#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def render_orchestrator(plan: dict) -> str:
    summary = plan.get("summary") or {}
    tasks = plan.get("tasks") or []
    publish = plan.get("publishDecision") or {}
    admission_gap = max(summary.get("privateSchoolCount", 0) - summary.get("privateAdmissionReadyCount", 0), 0)
    tuition_gap = max(summary.get("privateSchoolCount", 0) - summary.get("privateTuitionReadyCount", 0), 0)

    lines = [
        "## 主Agent补充说明",
        f"- 当前主缺口：民办招生 {admission_gap} 所、民办学费 {tuition_gap} 所。",
        "- 主分工：data-curator 主补数据，qa-reviewer 主做门禁与验收，policy 只在招生口径冲突时介入。",
        "- 执行顺序：先招生，再学费，最后画像；只要 P0 或重复学校回归，就立即切回基础信息修复。",
        f"- 发布策略：{publish.get('mode', '仅生成 PR')}。原因：{publish.get('reason', '待补充')}",
        "",
        "## 任务指派",
    ]

    if not tasks:
        lines.append("- 当前无新增任务，保持巡检。")
    for idx, task in enumerate(tasks, start=1):
        lines.append(
            f"- 任务 {idx}：`{task.get('role', 'unknown')}` 负责 {task.get('goal', '待补充目标')}；"
            f"完成标准为 {task.get('done', '待补充')}；"
            f"风险点是 {task.get('risk', '待补充')}。"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Hangzhou orchestrator markdown from plan json")
    parser.add_argument("--plan-json", required=True, help="Path to latest main plan json")
    parser.add_argument("--out", required=True, help="Path to orchestrator markdown output")
    args = parser.parse_args()

    plan = load_json(Path(args.plan_json))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_orchestrator(plan), encoding="utf-8")


if __name__ == "__main__":
    main()
