# GSTACK 多角色 Agent 安装指南
## 「上海幼升小择校助手」自动化迭代系统

**目标**：安装完成后，你只需要 **确认 PR** 就能完成一次完整的产品迭代。所有审查、代码修改、版本管理都由 4 个 Agent 自动完成。

---

## 一、架构总览

```
你（只需确认PR）
    ↑
GitHub PR ←── QA Agent（验证+Approve）
                  ↑
          Engineering Agent（汇总建议+写代码+创建PR）
           ↑              ↑
    CEO Agent        Design Agent
   （战略审查）       （UX审查）
```

**触发方式（三选一）：**
- ⏰ **定时自动**：每周一早上 9 点（北京时间）自动运行
- 🏷️ **Issue 标签触发**：给任意 Issue 加上 `gstack-iterate` 标签
- 🖱️ **手动触发**：在 GitHub Actions 页面点击 "Run workflow"

---

## 二、安装步骤（一次性操作）

### 步骤 1：安装 Codex CLI（本地用）

```bash
# 安装
npm install -g @openai/codex

# 验证安装
codex --version
```

### 步骤 2：配置 OpenAI API Key

```bash
# 方法A：临时设置（当前终端会话有效）
export OPENAI_API_KEY=sk-你的key

# 方法B：永久设置（推荐）
echo 'export OPENAI_API_KEY=sk-你的key' >> ~/.zshrc
source ~/.zshrc
```

> 💡 在哪里获取 API Key：https://platform.openai.com/api-keys
> 需要有 ChatGPT Plus 或 API 账户，选择有 `o4-mini` 权限的计划

### 步骤 3：在 GitHub 仓库设置 Secrets

打开：`https://github.com/kallenhu1-spec/primary-school-advisor/settings/secrets/actions`

添加以下 2 个 Secret：

| Secret 名称 | 值 | 说明 |
|------------|-----|------|
| `OPENAI_API_KEY` | `sk-你的key` | OpenAI API 密钥（GitHub Actions 自动迭代用） |
| `GITHUB_TOKEN` | *(自动提供，无需设置)* | GitHub 自动提供，用于创建 PR |

### 步骤 4：Push 配置文件到 GitHub

将本次新增的文件推送到仓库：

```bash
cd /path/to/primary-school-advisor

git add AGENTS.md
git add .codex/agents/
git add .github/workflows/gstack-iteration.yml
git add scripts/gstack-iterate.sh
git add GSTACK-SETUP-GUIDE.md

git commit -m "feat: 添加 GSTACK 多角色自动迭代系统"
git push origin master
```

### 步骤 5：在 GitHub 创建 `gstack-iterate` 和 `gstack-report` 标签

打开：`https://github.com/kallenhu1-spec/primary-school-advisor/labels`

点击 "New label" 创建：
- **gstack-iterate**：颜色 `#0075ca`，用于触发迭代
- **gstack-report**：颜色 `#e4e669`，用于标记迭代报告

### 步骤 6：在 Codex 网页版连接 GitHub（可选但推荐）

打开：https://chatgpt.com/codex

1. 点击 Settings → GitHub Integration
2. 授权连接你的 GitHub 账号
3. 选择仓库：`kallenhu1-spec/primary-school-advisor`
4. 开启 **Automatic reviews**（新 PR 自动触发 Codex 审查）

---

## 三、日常使用方式

### 方式 A：完全自动（推荐，什么都不用做）

每周一早上 9 点，系统自动：
1. CEO Agent 审查产品方向
2. Design Agent 审查 UX
3. Engineering Agent 实施改动并创建 PR
4. QA Agent 验证并审查 PR
5. 你收到 GitHub 通知 → 打开 PR → 确认 → Merge

**你的唯一操作**：打开邮件/GitHub 通知，看一眼 PR，点 Merge。

---

### 方式 B：随时手动触发（有灵感时用）

**方法1 — GitHub 网页触发：**
1. 打开：`Actions` 标签 → `GSTACK 多角色自动迭代`
2. 右上角点 **Run workflow**
3. 可选填"本次重点"（例如：`优化1v1 AI聊天功能`）
4. 点击绿色 **Run workflow** 按钮
5. 等待约 5-15 分钟，收到 PR 通知

**方法2 — Issue 标签触发：**
1. 打开任意 Issue（或新建一个）
2. 在右侧 Labels 栏加上 `gstack-iterate`
3. 自动触发迭代

**方法3 — 本地 CLI 触发（最快）：**
```bash
cd primary-school-advisor

# 全面审查
bash scripts/gstack-iterate.sh

# 指定重点
bash scripts/gstack-iterate.sh "优化移动端体验和策略报告样式"
```

---

### 方式 C：在 Codex 网页直接对话触发（最灵活）

打开 https://chatgpt.com/codex，连接仓库后，直接说：

> "帮我用 GSTACK 框架审查项目，重点优化付费引导流程，然后创建 PR"

Codex 会读取你的 `AGENTS.md` 和 `.codex/agents/` 配置，自动调用相应角色。

---

## 四、PR 确认流程（你的操作只有这个）

每次迭代结束后，你会收到邮件通知（如果开启了 GitHub 邮件通知）。

PR 内容一般包含：
- ✅ CEO 建议采纳了哪些
- ✅ Design 建议采纳了哪些
- 📝 具体代码改动（diff 摘要）
- ✅ QA 验证结果
- 📋 下次迭代建议

**你需要做的：**
1. 打开 PR 链接
2. 看一眼改动摘要（1-2分钟）
3. 如果 QA 通过（显示 ✅ APPROVE），点击 **Merge pull request**
4. 完成！线上版本自动更新（GitHub Pages 1-2 分钟生效）

**如果不满意：**
- 在 PR 评论框说明你的想法
- 给 PR 加 `gstack-iterate` 标签 → 触发新一轮迭代

---

## 五、文件结构说明

```
primary-school-advisor/
├── AGENTS.md                          # ← Codex 的项目总指令（必须有）
├── GSTACK-SETUP-GUIDE.md             # ← 本文件
│
├── .codex/
│   ├── agents/
│   │   ├── ceo-reviewer.toml         # ← CEO 战略审查角色
│   │   ├── design-reviewer.toml      # ← Design UX审查角色
│   │   ├── eng-reviewer.toml         # ← 工程实施角色（唯一写代码的）
│   │   └── qa-reviewer.toml          # ← QA验证角色
│   └── iteration-YYYYMMDD.log        # ← 每次迭代日志（自动生成）
│
├── .github/
│   └── workflows/
│       ├── sync_to_cloudflare_repo.yml  # ← 原有的部署工作流
│       └── gstack-iteration.yml         # ← 新增：GSTACK自动迭代工作流
│
└── scripts/
    └── gstack-iterate.sh              # ← 本地手动触发脚本
```

---

## 六、常见问题

**Q：Codex 修改代码后，中文乱码怎么办？**
A：AGENTS.md 和 eng-reviewer.toml 已经明确禁止 unicode_escape，QA Agent 也会检查这个。如果出现乱码，QA 会 REQUEST CHANGES，Engineering Agent 会重新修复。

**Q：我不想每周自动运行，怎么关掉定时触发？**
A：打开 `.github/workflows/gstack-iteration.yml`，注释掉 `schedule` 部分，只保留 `workflow_dispatch` 和 `issues` 触发。

**Q：API Key 的费用大概多少？**
A：每次完整迭代（4个Agent）使用 `o4-mini` 模型，预计消耗约 $0.05-0.15 美元（不到 1 元人民币）。每周自动运行的月费用约 $1-3。

**Q：Codex 能直接 Merge PR 吗？还是我必须手动确认？**
A：设计上 Codex 只能创建 PR，**Merge 操作保留给你**。这是安全设计——你永远是最终决策者。

**Q：如何给 Agent 下发特别任务（不走定时流程）？**
A：最简单的方式：在 GitHub 创建一个 Issue，标题写明任务，然后加上 `gstack-iterate` 标签。Engineering Agent 会把 Issue 内容纳入本次迭代的优先考量。

---

## 七、进阶：自定义迭代频率

编辑 `.github/workflows/gstack-iteration.yml` 中的 cron 表达式：

```yaml
schedule:
  - cron: '0 1 * * 1'    # 每周一 9:00（北京时间）
  # - cron: '0 1 * * *'  # 每天 9:00（高频迭代）
  # - cron: '0 1 1 * *'  # 每月1日 9:00（低频迭代）
```

---

*本系统基于 [OpenAI Codex](https://openai.com/codex/) + [Garry Tan GSTACK 框架](https://github.com/garrytan/gstack) 构建*
