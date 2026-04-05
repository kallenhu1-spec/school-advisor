# 上海幼升小择校助手 — Claude Code 项目指令

## 项目概述

帮助上海家长进行幼升小择校决策的产品，当前版本 v8.0.1。
- **线上地址**：https://kallenhu1-spec.github.io/school-advisor/
- **主文件**：`index.html`（单文件架构，含全部前端逻辑+数据）
- **学校数据**：170+ 所学校，覆盖上海 9 个区
- **技术栈**：HTML + CSS + JavaScript + Chart.js（内联）
- **后端**：Python 标准库 HTTP Server + SQLite（本地默认 127.0.0.1:8787）

## 数据质量原则（强制）

> 这个产品帮助真实家长做择校决策，数据诚实是底线。

- 口碑数据（`var PR=`）大部分是 AI 生成的草稿，前端展示时必须附带免责说明
- 中签率数据必须标注年份（`rateYear`）和是否为估算值（`rateEstimated`）
- 涉及数据修改时，必须同时更新 `dataSource` 来源字段
- 来源级别：`official`（官方）> `verified`（已核实）> `community`（社区）> `ai-draft`（AI草稿）
- 禁止把 `ai-draft` 数据当成真实数据展示，必须有 ⚠️ 标注
- 禁止自行编造来源链接（url 不确定就填 null）

## 编码规范（违反则视为 bug）

1. HTML 内 JS 中的中文必须直接写 UTF-8 字符串，**禁止** `unicode_escape` 或 `&#XXXXX;` 数字实体
2. commit message 用中文，格式：`{类型}({范围}): {描述}`
3. 禁止修改 `.github/workflows/` 下的任何文件
4. 禁止删除任何学校数据条目（只能新增或修改）

## 版本管理

- 修改 `index.html` 前必须先存档到 `versions/vX.Y.Z-YYYYMMDD.html`
- 同步更新 `VERSION.json`
- 版本号规则：bug fix → patch +1，新功能 → minor +1，架构重构 → major +1（需人工确认）
- 在 `versions/CHANGELOG.md` 追加变更记录

## 核心数据结构

- `var SD=` — 学校数据数组（name/district/type/tier/rate/status/mapUrl/xhsUrl）
- `var PR=` — 口碑 Profile 对象（philosophy/homework/path/pros/cons）
- `var TF=` — 梯队分类
- `var DN=` — 区域映射

## 文件分工（多会话并行时遵守）

- **前端开发**：只改 `index.html`、`versions/`、`VERSION.json`
- **数据工作**：只改 `data/`、`backend/`、`scripts/`
- 两条线通过 `data/curation/` 下的 JSONL 文件对接

## 商业目标（决策参考）

- 核心用户：上海幼升小家长（每年约 18 万+家庭）
- 商业模型：免费工具 + 付费 AI 咨询服务
- 当前优先级：1v1 AI Chat 上线 > 付费引导 > 微信生态 > 性能优化

## 测试检查清单

每次修改后必须验证：
- 中文显示正常（无乱码、无 `\u` 转义、无 `&#` 实体）
- 手机端布局正确（#school-table 桌面显示，#school-cards 手机显示）
- 筛选功能正常（梯队/区域/类型）
- 策略生成可用
- Chart.js 图表渲染正常
- localStorage 表单记忆正常
- SD/PR/TF/DN 数据条目一致性

## 可用的审查命令

本项目配置了 GSTACK 多角色审查流程，可通过 slash commands 触发：
- `/review-ceo` — CEO 战略视角审查
- `/review-design` — UX/UI 设计审查 + AI Slop 检测
- `/review-eng` — 工程代码审查 + 实施
- `/review-qa` — 质量验证 + 风险检查
- `/data-curator` — 数据采集、清洗、结构化

推荐流程：CEO → Design → Engineering（实施改动） → QA（验证后 approve）
