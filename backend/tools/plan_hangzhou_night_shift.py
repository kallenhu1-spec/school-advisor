#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def build_tasks(qa: dict) -> list[dict]:
    tasks = []
    missing_basics = qa.get("missingBasicsCount", 0)
    private_school_count = qa.get("privateSchoolCount", 0)
    admission_ready = qa.get("privateAdmissionReadyCount", 0)
    tuition_ready = qa.get("privateTuitionReadyCount", 0)
    profile_missing = qa.get("profileMissingCount", 0)
    admission_gap = max(private_school_count - admission_ready, 0)
    tuition_gap = max(private_school_count - tuition_ready, 0)

    if missing_basics > 0:
        tasks.append(
            {
                "role": "data-curator",
                "goal": "补齐杭州学校 P0 基础字段，先修复缺失的 officialName / district / type / address / sourceUrl / basicInfoSourceLevel。",
                "files": [
                    "data/seed_v2_city_hangzhou.json",
                    "backend/tools/build_hangzhou_school_directory.py",
                ],
                "done": "missingBasicsCount = 0，且 duplicateKeys 为空。",
                "risk": "若证据不足，宁可留空并列入待核实，不可编造。",
                "priority": "P0",
            }
        )
        tasks.append(
            {
                "role": "qa-reviewer",
                "goal": "逐项复核 P0 基础字段缺失学校，确认缺失项已清零且没有新增重复学校。",
                "files": [
                    "data/seed_v2_city_hangzhou.json",
                    "backend/tools/check_hangzhou_seed.py",
                ],
                "done": "missingBasicsCount = 0，duplicateKeys 为空，且 QA 结论不再阻断。",
                "risk": "若发现基础字段回归，不允许把精力转去招生、学费或画像。",
                "priority": "P0-验收",
            }
        )
    if admission_gap > 0:
        tasks.append(
            {
                "role": "data-curator",
                "goal": f"补杭州民办学校 2025 招生口径，优先清掉剩余 {admission_gap} 所缺口，重点补 admissionUrl / lotteryNeeded / lotteryData。",
                "files": [
                    "data/seed_v2_city_hangzhou.json",
                    "backend/tools/build_hangzhou_school_directory.py",
                    "data/curation/hangzhou/sources_manifest.json",
                ],
                "done": "privateAdmissionReadyCount 提升，且所有新增字段均标注 official/verified 来源。",
                "risk": "不得把搜索摘要伪装成官方公告。",
                "priority": "P1",
            }
        )
        tasks.append(
            {
                "role": "qa-reviewer",
                "goal": "复核民办招生字段来源等级和覆盖率，确认新增招生口径没有把 candidate 或搜索摘要误标为 official。",
                "files": [
                    "data/seed_v2_city_hangzhou.json",
                    "backend/tools/check_hangzhou_seed.py",
                ],
                "done": "privateAdmissionReadyCount 提升且来源分级准确，若证据不足则列入待核实清单。",
                "risk": "招生简章与报名公告口径不一致时，必须上报主Agent，不得强行合并。",
                "priority": "P1-验收",
            }
        )
        tasks.append(
            {
                "role": "policy",
                "goal": "对招生口径冲突或规则复杂的民办学校做政策判读，优先处理摇号、报名范围、招生简章口径不一致的问题。",
                "files": [
                    "data/seed_v2_city_hangzhou.json",
                    "data/curation/hangzhou/sources_manifest.json",
                ],
                "done": "输出待核实学校清单和口径说明，供 data-curator 回填结构化字段。",
                "risk": "若没有明确官方依据，只能标注冲突说明，不能替主数据做拍板。",
                "priority": "P1-支援",
            }
        )
    if tuition_gap > 0 and len(tasks) < 3:
        tasks.append(
            {
                "role": "data-curator",
                "goal": f"补杭州民办学校学费信息，优先清掉剩余 {tuition_gap} 所缺口，优先学校官网与招生简章可核实字段。",
                "files": [
                    "data/seed_v2_city_hangzhou.json",
                    "backend/tools/build_hangzhou_school_directory.py",
                    "data/curation/hangzhou/sources_manifest.json",
                ],
                "done": "privateTuitionReadyCount 提升，且 tuition.note/sourceUrl/sourceLevel 完整。",
                "risk": "无官方收费来源时保持留空，不写估算价或二手传言。",
                "priority": "P2",
            }
        )
    if tuition_gap > 0 and len(tasks) < 3:
        tasks.append(
            {
                "role": "qa-reviewer",
                "goal": "复核民办学费字段来源等级，确认收费口径、学段和币种/单位没有混淆。",
                "files": [
                    "data/seed_v2_city_hangzhou.json",
                    "backend/tools/check_hangzhou_seed.py",
                ],
                "done": "privateTuitionReadyCount 提升且新增学费字段不存在来源误标。",
                "risk": "若收费公示与招生简章冲突，必须回退为待核实，不得直接覆盖。",
                "priority": "P2-验收",
            }
        )
    if profile_missing > 0 and len(tasks) < 3:
        tasks.append(
            {
                "role": "data-curator",
                "goal": f"补杭州热门学校画像，当前仍缺 {profile_missing} 所，优先 T1/T2 与用户高频查看学校。",
                "files": [
                    "data/seed_v2_city_hangzhou.json",
                ],
                "done": "profileMissingCount 下降，新增画像统一标为 AI总结。",
                "risk": "画像不能覆盖或污染基础信息、招生字段与官方字段。",
                "priority": "P3",
            }
        )
    if not tasks:
        tasks.append(
            {
                "role": "qa-reviewer",
                "goal": "杭州当前无阻断缺口，夜班仅做健康巡检与报告归档。",
                "files": ["data/seed_v2_city_hangzhou.json"],
                "done": "继续保持 schoolCount、P0 字段和重复数稳定。",
                "risk": "若第二天发现官方口径更新，再进入 data-curator 模式。",
                "priority": "巡检",
            }
        )
    return tasks[:3]


def build_decision(qa: dict) -> tuple[str, str]:
    if qa.get("missingBasicsCount", 0) > 0 or qa.get("duplicateKeys"):
        return ("仅生成 PR", "基础字段或重复学校存在风险，先修复后再由主Agent决定是否发布。")
    if qa.get("privateAdmissionReadyCount", 0) < qa.get("privateSchoolCount", 0):
        return ("仅生成 PR", "招生字段仍在补齐阶段，适合夜间持续推进，但不建议静默自动发布。")
    if qa.get("privateTuitionReadyCount", 0) < qa.get("privateSchoolCount", 0):
        return ("仅生成 PR", "学费字段仍有明显覆盖缺口，建议继续补齐并由 QA 复核后再发布。")
    return ("允许自动发布", "基础字段稳定且本轮主要是增量完善，可在 QA 通过后自动发布。")


def render_markdown(qa: dict, tasks: list[dict], decision: tuple[str, str], now_text: str) -> str:
    admission_gap = max(qa.get("privateSchoolCount", 0) - qa.get("privateAdmissionReadyCount", 0), 0)
    tuition_gap = max(qa.get("privateSchoolCount", 0) - qa.get("privateTuitionReadyCount", 0), 0)
    role_lines = []
    if qa.get("missingBasicsCount", 0) > 0:
        role_lines.append("- `data-curator`：先修 P0 基础字段与重复学校。")
        role_lines.append("- `qa-reviewer`：逐项复核 P0 清零后才允许切到后续任务。")
    else:
        if admission_gap > 0:
            role_lines.append(f"- `data-curator`：主补民办招生口径，当前优先清掉 {admission_gap} 所缺口。")
            role_lines.append("- `qa-reviewer`：主验招生字段的来源等级、覆盖率和误标风险。")
            role_lines.append("- `policy`：只在招生公告、简章、摇号规则口径冲突时介入。")
        if tuition_gap > 0:
            role_lines.append(f"- `data-curator`：在招生任务之后补民办学费，当前待清 {tuition_gap} 所缺口。")
            role_lines.append("- `qa-reviewer`：复核收费字段的来源等级和口径一致性。")
    if qa.get("profileMissingCount", 0) > 0:
        role_lines.append("- `frontend`：当前暂不主导，仅在新增字段需要展示时配合。")
    lines = [
        f"# 杭州夜班工作计划 - {now_text}",
        "",
        "## 今日状态",
        f"- 学校总数：{qa.get('schoolCount', 0)}",
        f"- P0 缺失数：{qa.get('missingBasicsCount', 0)}",
        f"- 民办招生覆盖：{qa.get('privateAdmissionReadyCount', 0)} / {qa.get('privateSchoolCount', 0)}",
        f"- 民办学费覆盖：{qa.get('privateTuitionReadyCount', 0)} / {qa.get('privateSchoolCount', 0)}",
        f"- 画像缺失数：{qa.get('profileMissingCount', 0)}",
        "",
        "## 当前策略焦点",
        f"- 第一优先级：民办招生缺口 {admission_gap} 所，由 `data-curator` 主补，`qa-reviewer` 主验，必要时 `policy` 介入口径冲突。",
        f"- 第二优先级：民办学费缺口 {tuition_gap} 所，由 `data-curator` 主补，`qa-reviewer` 复核来源等级。",
        "- 第三优先级：学校画像缺失仅在前两项无阻断时推进，不允许反客为主。",
        "",
        "## Agent 分工",
        *role_lines,
        "",
        "## 今日计划",
    ]
    for idx, task in enumerate(tasks, start=1):
        lines.extend(
            [
                f"### 任务 {idx}",
                f"- 执行角色：`{task['role']}`",
                f"- 任务目标：{task['goal']}",
                f"- 预计影响文件：{', '.join(task['files'])}",
                f"- 完成标准：{task['done']}",
                f"- 风险提示：{task['risk']}",
                f"- 优先级：{task['priority']}",
                "",
            ]
        )
    lines.extend(
        [
            "## 发布决策",
            f"- 结论：`{decision[0]}`",
            f"- 理由：{decision[1]}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Hangzhou nightly orchestrator plan from QA result")
    parser.add_argument("--qa", required=True, help="Path to hangzhou QA json")
    parser.add_argument("--out-md", required=True, help="Path to markdown plan output")
    parser.add_argument("--out-json", required=True, help="Path to json plan output")
    args = parser.parse_args()

    qa_path = Path(args.qa)
    qa = load_json(qa_path)
    tasks = build_tasks(qa)
    decision = build_decision(qa)
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")

    payload = {
        "generatedAt": now_text,
        "summary": {
            "schoolCount": qa.get("schoolCount", 0),
            "missingBasicsCount": qa.get("missingBasicsCount", 0),
            "privateAdmissionReadyCount": qa.get("privateAdmissionReadyCount", 0),
            "privateSchoolCount": qa.get("privateSchoolCount", 0),
            "privateTuitionReadyCount": qa.get("privateTuitionReadyCount", 0),
            "profileMissingCount": qa.get("profileMissingCount", 0),
        },
        "tasks": tasks,
        "publishDecision": {"mode": decision[0], "reason": decision[1]},
    }

    out_md = Path(args.out_md)
    out_json = Path(args.out_json)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_markdown(qa, tasks, decision, now_text) + "\n", encoding="utf-8")
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
