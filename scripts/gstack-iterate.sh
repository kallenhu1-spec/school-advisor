#!/bin/bash
# ============================================================
# GSTACK 多角色本地迭代脚本
# 用法：bash scripts/gstack-iterate.sh [focus_area]
# 示例：bash scripts/gstack-iterate.sh "优化1v1 AI聊天功能"
#       bash scripts/gstack-iterate.sh  （不传参数=全面审查）
# ============================================================

set -e

FOCUS="${1:-全面战略审查与代码迭代}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATE=$(date +%Y%m%d)
LOG_FILE="$REPO_ROOT/.codex/iteration-$DATE.log"

echo "========================================"
echo " GSTACK 多角色迭代启动"
echo " 重点：$FOCUS"
echo " 日志：$LOG_FILE"
echo "========================================"
echo ""

# 检查 codex 是否已安装
if ! command -v codex &>/dev/null; then
  echo "❌ 错误：未找到 codex 命令"
  echo "   请先安装：npm install -g @openai/codex"
  exit 1
fi

# 检查 OPENAI_API_KEY
if [ -z "$OPENAI_API_KEY" ]; then
  echo "❌ 错误：未设置 OPENAI_API_KEY 环境变量"
  echo "   请运行：export OPENAI_API_KEY=sk-..."
  exit 1
fi

cd "$REPO_ROOT"

# ──────────────────────────────────────────
# Step 1: CEO 审查（并行开始）
# ──────────────────────────────────────────
echo "▶ Step 1/4：CEO 战略审查..."
CEO_OUTPUT=$(codex \
  --agent ceo-reviewer \
  --full-auto \
  --quiet \
  "你是 ceo-reviewer Agent。请审查项目现状（读取 AGENTS.md、VERSION.json、school-advisor-strategic-review.md），针对「$FOCUS」给出 CEO 视角的审查报告和TOP3优先级。" \
  2>&1)

echo "$CEO_OUTPUT" | tee -a "$LOG_FILE"
echo ""
echo "✅ CEO 审查完成"
echo ""

# ──────────────────────────────────────────
# Step 2: Design 审查（并行）
# ──────────────────────────────────────────
echo "▶ Step 2/4：Design UX 审查..."
DESIGN_OUTPUT=$(codex \
  --agent design-reviewer \
  --full-auto \
  --quiet \
  "你是 design-reviewer Agent。请审查 index.html 的 UX/UI 设计，针对「$FOCUS」给出设计问题清单和修复建议。" \
  2>&1)

echo "$DESIGN_OUTPUT" | tee -a "$LOG_FILE"
echo ""
echo "✅ Design 审查完成"
echo ""

# ──────────────────────────────────────────
# Step 3: 工程实施（汇总并执行改动）
# ──────────────────────────────────────────
echo "▶ Step 3/4：工程实施..."
echo "  [将 CEO 和 Design 建议汇总，选出最高优先级改动]"
echo ""

codex \
  --agent eng-reviewer \
  --full-auto \
  "你是 eng-reviewer Agent。以下是本次迭代的审查结果：

=== CEO 审查输出 ===
$CEO_OUTPUT

=== Design 审查输出 ===
$DESIGN_OUTPUT

请按照你的 instructions 完成：
1. 从以上建议中选出优先级最高的 1-2 个改动
2. 实施代码改动（遵守编码规范：中文直接UTF-8，禁止unicode_escape）
3. 更新 VERSION.json 和 versions/CHANGELOG.md
4. 存档当前版本
5. 创建 PR（PR body 包含 QA 验证清单）" \
  2>&1 | tee -a "$LOG_FILE"

echo ""
echo "✅ 工程实施完成，PR 已创建"
echo ""

# ──────────────────────────────────────────
# Step 4: QA 验证
# ──────────────────────────────────────────
echo "▶ Step 4/4：QA 质量验证..."

codex \
  --agent qa-reviewer \
  --full-auto \
  "你是 qa-reviewer Agent。Engineering Agent 刚刚修改了 index.html 并创建了 PR。
请执行完整的 QA 验证：
1. 运行 git diff HEAD~1 index.html 查看改动
2. 逐项检查必检清单（功能、中文编码、移动端、数据完整性）
3. 在 PR 评论中发布验证结果（✅/❌/⚠️）
4. 给出最终结论：APPROVE / REQUEST CHANGES / APPROVE WITH NOTES" \
  2>&1 | tee -a "$LOG_FILE"

echo ""
echo "========================================"
echo " ✅ GSTACK 本次迭代全部完成！"
echo ""
echo " 下一步（你只需要做这一件事）："
echo " → 打开 GitHub PR 列表，查看新建的 PR"
echo " → 确认改动内容后，点击 Merge 即可"
echo ""
echo " GitHub: https://github.com/kallenhu1-spec/primary-school-advisor/pulls"
echo "========================================"
