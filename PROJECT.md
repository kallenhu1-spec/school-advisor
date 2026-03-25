# 上海幼升小择校助手 — 项目说明书

## 项目概述

**项目名称**：上海幼升小择校助手（Shanghai Primary School Advisor）  
**项目类型**：前后端分离（静态前端 + Python API + SQLite）  
**GitHub 仓库**：`https://github.com/kallenhu1-spec/primary-school-advisor`  
**线上地址**：`https://kallenhu1-spec.github.io/school-advisor/`  
**主文件**：`index.html`（当前稳定版入口，版本号见 `VERSION.json`）

---

## 项目目标

帮助上海家长在幼升小阶段进行择校决策，功能包括：
- 根据户籍/区域/偏好生成专属择校策略
- 按梯队/区域/公民办类型筛选学校
- 展示各学校的中签率、口碑、升学路径等详细信息
- 提供关键时间节点（报名、摇号、录取）提醒
- 提供内参指南（择校步骤、材料清单）

---

## 技术架构

**技术栈**：HTML + CSS + JavaScript（前端） + Python 标准库 HTTP Server（后端） + SQLite（数据层）  
**外部库**：Chart.js（内联，用于中签率雷达图/柱状图）  
**存储**：`localStorage`（前端表单状态） + SQLite（服务端学校数据）  
**部署**：可静态部署前端 + 独立部署后端 API（本地默认 `127.0.0.1:8787`）

### 文件结构

```
primary-school-advisor/
├── index.html                          # 主文件，即线上版本
├── school-advisor-v8.0.0-latest.html  # 最新稳定版备份
├── school-advisor-v7.6-latest.html    # 历史版本（保留）
├── school-advisor-v7.6-20260322-1.html  # 带日期的版本快照
├── VERSION.json                        # 当前发布版本元数据
├── backend/                            # 后端 API + 数据脚本
├── data/                               # SQLite 数据库与种子数据
├── versions/                           # 历史版本存档
│   ├── CHANGELOG.md                   # 版本变更日志
│   ├── v8.0.0-20260326.html
│   └── v7.6-pre-hongkou.html
└── PROJECT.md                         # 本文件
```

---

## 核心数据结构

`index.html` 内嵌了完整的学校数据和口碑 Profile，以 JavaScript 对象形式存储。

### 学校数据（`schools` 数组）

每所学校的字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 学校名称 |
| `district` | string | 所在区（徐汇/长宁/静安/黄浦/普陀/杨浦/闵行/浦东/虹口） |
| `type` | string | `pub`（公办）或 `pri`（民办） |
| `tier` | string | `T1`/`T2`/`T3`（梯队） |
| `rate` | number/string | 中签率（0-1 之间的小数，或 "全录" 等字符串） |
| `status` | string | `超额`/`全录`/`正常` |
| `mapUrl` | string | 高德地图搜索链接 |
| `xhsUrl` | string | 小红书搜索链接 |

### 学校口碑（`profiles` 对象）

Key 为学校名，Value 包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `philosophy` | string | 教育理念 |
| `homework` | number | 作业压力星级（1-5） |
| `path` | string[] | 升学路径（标签数组） |
| `pros` | string[] | 优点列表 |
| `cons` | string[] | 注意事项/缺点列表 |

---

## 主要功能模块

### Tab 1：我的择校
- **表单输入**：户籍情况、所在区域、教育偏好（双语/传统/均衡）、对口公办质量
- **策略生成**：点击"生成策略"后输出个性化推荐（前3所推荐卡片 + 策略说明横幅）
- **学校列表**：可按梯队（T1/T2/T3）、状态（超额/全录）、区域、类型筛选
- **学校详情**：点击展开，显示口碑 Profile（理念/作业压力/升学路径/优缺点）
- **操作按钮**：高德导航（搜索模式）、小红书口碑

### Tab 2：关键时间
- 按月份分组的时间节点（3月/4月/5月/8月）
- 含 💡 小提示
- 注明"以 2025 为参考"免责说明

### Tab 3：内参指南
- 择校步骤总览
- 报名材料清单（户籍/居住证等）

### 其他 UI 功能
- **表单记忆**：`localStorage` 保存筛选状态，刷新后自动恢复
- **手机端适配**：`@media (max-width: 768px)` 时隐藏表格，显示卡片式列表
- **小红书跳转**：微信内提示复制关键词，其他环境直接跳转
- **localStorage 重置**：右上角显示"🔄 重新填写"按钮

---

## 数据覆盖范围

- **学校总数**：约 170+ 所（覆盖上海 9 个区）
- **有口碑 Profile 的学校**：约 169 所（全覆盖）
- **数据来源**：2025 年实际摇号结果（知乎/搜狐等公开整理），部分数据以 2025 为参考
- **已有区域**：徐汇、长宁、静安、黄浦、普陀、杨浦、闵行、浦东、虹口

---

## 版本历史（简要）

| 版本 | 日期 | 主要变更 |
|------|------|---------|
| v1-v3 | 2026-03-18 | 初版，修复 Chart.js 渲染 bug 和中文编码问题 |
| v4 | 2026-03-18 | 更新为 2025 真实摇号数据，学校扩充至 50 所，加高德导航 |
| v5 | 2026-03-18 | 学校详情面板（19 所），小红书口碑跳转 |
| v6 | 2026-03-18 | 区域/类型筛选，数据修正，扩至 45 校 |
| v7.0 | 2026-03-18 | 三 Tab 结构（我的择校/关键时间/内参指南），52 所学校，梯队字段 |
| v7.4 | 2026-03-19 | 手机端适配，图标修复，高德改为搜索模式 |
| v7.5 | 2026-03-19 | 口碑按钮 bug 修复，localStorage 表单记忆，口碑 Profile 全覆盖（169 所） |
| v7.6 | 2026-03-19 | 推荐卡片样式统一，展开按钮优化，路线策略差异化，大众点评搜索词优化 |
| v7.6+ | 2026-03-22 | 补充虹口区学校数据，更新 12 所学校中签率为 2025 真实数据 |

**当前稳定版**：v8.0.0（文件：`index.html`）

---

## 已知问题 & 待办

- [ ] v8 版本（三 Tab 重构 + 时间轴改进）开发中断，`v8_css.css` 和 `v8_js.js` 已存档备用
- [ ] 部分学校（星河湾浦东、闵行协和等）2025 中签率尚未确认，暂用估算值
- [ ] 小红书跳转在沙箱环境无法测试，依赖真实设备验证
- [ ] 每日政策监控 cron job（搜索上海幼升小政策更新）已设置，Job ID: `976fcf7f-d258-4746-bcbd-81f3d35370b8`

---

## 维护指南（给 Claude Code）

### 如何更新学校数据

推荐流程（v8.0.0+）：
1. 准备包含 `SD/PR/TF/DN` 的 JSON 文件
2. 执行 `python3 backend/tools/update_bootstrap.py --file /path/to/new-data.json`
3. 重启后端 API，前端刷新后自动读取新数据

兼容流程（不推荐）：
1. 在 `index.html` 中搜索 `var SD=`，找到学校数组
2. 按照现有格式添加或修改学校条目
3. 对应更新 `var PR=`、`var TF=`、`var DN=` 等结构
4. 修改前先把当前 `index.html` 复制到 `versions/` 目录存档（文件名格式：`vX.Y.Z-YYYYMMDD[-rN].html`）

### 如何部署更新

1. 修改 `index.html`
2. `git add index.html && git commit -m "描述本次变更"`
3. `git push origin master`
4. GitHub Pages 自动从 master 分支的 `index.html` 部署，通常 1-2 分钟生效

### 版本存档规范

- 每次发布前，将当前 `index.html` 复制到 `versions/vX.Y-YYYYMMDD[-rN].html`
- 同步更新 `versions/CHANGELOG.md`

### 编码注意事项

⚠️ **重要**：HTML 文件内 JavaScript 代码块中的中文字符，**必须直接写 UTF-8 字符串，禁止用 Python 的 `unicode_escape` 或 `&#XXXXX;` 数字实体**，否则会导致中文乱码（历史上 v8 版本因此问题回退）。

### CSS 结构提示

- 桌面端学校列表：`#school-table`（HTML table）
- 手机端学校列表：`#school-cards`（卡片式 div）
- 两者通过 `@media (max-width: 768px)` 切换显示，同时通过 JS `showTab()` 和 `renderTable()` 控制显隐
- 推荐卡片区域：`.rec-cards-grid`（桌面端网格布局）

---

## 联系 & 背景

- 本项目由 KK（OpenClaw AI 助手）为晓妍构建，始于 2026 年 3 月 18 日
- 数据基于 2025 年上海幼升小实际摇号结果
- 如数据需要更新，参考各区教育局官网及 vsxue.com 等择校社区信息
