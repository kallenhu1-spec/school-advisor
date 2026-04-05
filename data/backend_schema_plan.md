# Backend Schema 改造方案（对齐 seed_v2）

> 产出：review-eng | 日期：2026-04-02 | 状态：规划中，待确认

---

## 1. 现状分析

### 1.1 当前 SQLite 表结构（本地 backend/server.py）

| 表 | 用途 | 问题 |
|---|------|------|
| `datasets` | 存 SD/PR/TF/DN 四个大 JSON blob（id=1 单行） | **整坨 JSON**，无法按学校查询/更新 |
| `proposals` | 待审核变更队列 | 可保留 |
| `policy_events` | 政策事件 | 可保留 |
| `school_evidence` | 学校证据缓存 | 可保留 |

### 1.2 当前 D1 表结构（cloudflare/d1/schema.sql）

| 表 | 用途 |
|---|------|
| `bootstrap_payload` | 也是整坨 JSON blob（id=1 单行） |
| `school_evidence_cache` | 同上 |

### 1.3 核心问题

- **数据全部塞在一个 JSON 字段里**，每次读写都是全量替换
- SD 是位置数组（`row[0]` 是名字，`row[5]` 是评分...），极脆弱
- 无法按区、按学校、按字段粒度更新
- 来源级别无处存储

---

## 2. 新表设计（对齐 seed_v2_schema.md）

### 2.1 `schools` — 学校主表

```sql
CREATE TABLE IF NOT EXISTS schools (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,                -- 前端显示短名
  official_name TEXT NOT NULL DEFAULT '',     -- 官方全称（来自PDF）
  district      TEXT NOT NULL,               -- yangpu/xuhui/pudong...
  type          TEXT NOT NULL,               -- pri/pub
  tier          TEXT NOT NULL DEFAULT 'T3',  -- T1/T2/T3
  lat           REAL,
  lng           REAL,
  desc_text     TEXT NOT NULL DEFAULT '',    -- 一句话简介

  -- 外部链接
  link_map      TEXT,                        -- 地图链接
  link_xhs      TEXT,                        -- 小红书关键词或链接
  link_dianping TEXT,                        -- 大众点评链接

  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,

  UNIQUE(name, district)
);
```

**设计说明：**
- `name + district` 联合唯一，防止不同区同名学校冲突
- `desc_text` 而非 `desc`，避免 SQL 保留字
- 坐标 `lat/lng` 用 REAL 类型，D1 和 SQLite 都支持

### 2.2 `admissions` — 招生数据表（按年存储）

```sql
CREATE TABLE IF NOT EXISTS admissions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id        INTEGER NOT NULL REFERENCES schools(id),
  year             INTEGER NOT NULL,          -- 2025, 2026...
  admitted         INTEGER,                   -- 录取人数
  max_lottery      INTEGER,                   -- 最大摇号人数
  rate             REAL,                      -- 中签率（%），自动算
  admission_source TEXT NOT NULL DEFAULT 'ai-draft',  -- official/verified/community/ai-draft
  admission_url    TEXT,                      -- 来源链接（PDF/网页）
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL,

  UNIQUE(school_id, year)
);
```

**设计说明：**
- **按年一行**，天然支持历史数据（2024、2025、2026...）
- `rate` 冗余存储但由写入逻辑自动算（`admitted / max_lottery * 100`），查询时不需要再算
- seed_v2.json 里的 `admission.rateYear` 对应这里的 `year`

### 2.3 `profiles` — 口碑信息表

```sql
CREATE TABLE IF NOT EXISTS profiles (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id     INTEGER NOT NULL REFERENCES schools(id),
  tag           TEXT NOT NULL DEFAULT '',     -- 分类标签
  philosophy    TEXT,                         -- 官方教育理念
  path_json     TEXT NOT NULL DEFAULT '[]',   -- 升学路径 JSON 数组
  pros_json     TEXT NOT NULL DEFAULT '[]',   -- 优点 JSON 数组
  cons_json     TEXT NOT NULL DEFAULT '[]',   -- 注意点 JSON 数组
  source_level  TEXT NOT NULL DEFAULT 'ai-draft',  -- official/verified/community/ai-draft
  source_note   TEXT,                         -- 来源说明
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,

  UNIQUE(school_id)
);
```

**设计说明：**
- 一个学校一条 profile（1:1），用 UNIQUE 约束
- `path/pros/cons` 是变长数组，用 JSON 字符串存储（SQLite JSON1 扩展和 D1 都支持）
- `source_level` 标注整条 profile 的来源级别

### 2.4 保留已有表

| 表 | 处理 |
|---|------|
| `datasets` | **保留但降级为兼容层**——v1 前端仍从这里读 bootstrap JSON |
| `proposals` | 保留不动 |
| `policy_events` | 保留不动 |
| `school_evidence` | 保留不动 |

---

## 3. D1（Cloudflare）兼容性

| 考虑点 | 方案 |
|--------|------|
| SQL 语法 | 只用 SQLite 兼容语法，D1 原生支持 |
| JSON 函数 | `json_extract()` 两边都支持，但只用于读取，不依赖 JSON 写入 |
| 自增 ID | `AUTOINCREMENT` 两边都支持 |
| 外键 | D1 支持但默认不强制，本地 SQLite 需 `PRAGMA foreign_keys = ON`。**建议：应用层保证一致性，不依赖外键约束** |
| 迁移 | D1 和本地用同一份 `schema_v2.sql`，通过版本号字段判断是否需要 migrate |

**schema 文件结构：**
```
cloudflare/d1/schema.sql       -- 现有 v1（保留）
cloudflare/d1/schema_v2.sql    -- 新增 v2（schools + admissions + profiles）
backend/tools/migrate_v2.py    -- 本地 SQLite 迁移脚本
```

---

## 4. 数据迁移方案

### 4.1 迁移脚本需求：`backend/tools/migrate_v1_to_v2.py`

**输入：** `data/seed.json`（v1 格式）
**输出：** `data/seed_v2.json`（v2 格式）+ 写入 SQLite 新表

**迁移逻辑：**

```
对于 seed.json 中每个 SD 条目（位置数组）：
  1. 提取字段 → 写入 schools 表
  2. 如有 admitted/maxLottery → 写入 admissions 表（year=2025）
  3. 如 PR 中有对应口碑 → 写入 profiles 表
  4. 删除 score/heat/hw/stress/ideas 等无依据字段
  5. 所有 profile 的 source_level 默认标为 'ai-draft'
```

**字段映射（完整）：**

| seed.json v1 | → | schools 表 |
|---|---|---|
| `SD[i][0]` | → | `name` |
| `SD[i][1]` | → | `district` |
| `SD[i][2]` | → | `type` |
| `SD[i][6]` | → | `desc_text` |
| `SD[i][7]` | → | `lat` |
| `SD[i][8]` | → | `lng` |
| `SD[i][10]` | → | `tier` |
| `SD[i][3]`（rateLow，取单值） | → | `admissions.rate` |
| `SD[i][11]` | → | `admissions.admitted` |
| `SD[i][12]` | → | `admissions.max_lottery` |
| `PR[name].tag` | → | `profiles.tag` |
| `PR[name].slogan` | → | `profiles.philosophy` |
| `PR[name].path` | → | `profiles.path_json` |
| `PR[name].pros` | → | `profiles.pros_json` |
| `PR[name].cons` | → | `profiles.cons_json` |
| `SD[i][5]`（score） | → | 丢弃 |
| `SD[i][9]`（heat） | → | 丢弃 |
| `PR[name].hw` | → | 丢弃 |
| `PR[name].stress` | → | 丢弃 |
| `PR[name].ideas` | → | 丢弃 |

### 4.2 执行顺序（安全迁移）

```
1. 创建 schema_v2 的空表（schools/admissions/profiles）
2. 运行 migrate_v1_to_v2.py，同时产出：
   - SQLite 新表数据
   - data/seed_v2.json 文件
3. 人工核对 seed_v2.json（先看杨浦区 20 所）
4. 确认后，新的 API 端点从新表读数据
5. 旧的 /api/bootstrap 端点保持不变，仍从 datasets 表读 v1 格式
```

---

## 5. 前端 Adapter 方案

### 5.1 思路：后端做适配，前端不改

前端当前依赖 `var SD=` 和 `var PR=` 两个全局变量。最安全的方式是**在 API 层做格式转换**，而不是改前端。

**`/api/bootstrap` 端点改造：**

```python
def _get_bootstrap_payload():
    # 检测是否有 v2 表数据
    if _has_v2_data():
        # 从 schools/admissions/profiles 表组装成 v1 格式返回
        return _build_v1_from_v2_tables()
    else:
        # 兜底：从 datasets 表读旧 JSON
        return _get_legacy_payload()
```

**`_build_v1_from_v2_tables()` 的输出格式：**

```json
{
  "SD": [
    ["民办打一外国语小学", "yangpu", "pri", 43.9, 43.9, 0, "T1民办...", 31.28, 121.52, "normal", "T1", 151, 344]
  ],
  "PR": {
    "民办打一外国语小学": {
      "tag": "...", "slogan": "...", "path": [...], "pros": [...], "cons": [...]
    }
  },
  "TF": {},
  "DN": {}
}
```

这样前端零改动，但后端已经在用结构化表了。

### 5.2 新增 v2 API（给未来新前端用）

```
GET /api/v2/schools?district=yangpu     → 返回 seed_v2 格式的学校列表
GET /api/v2/schools/:name               → 返回单校完整信息（含 admission + profile）
GET /api/v2/schools/:name/admissions    → 返回该校历年招生数据
```

这些 v2 端点在新前端、管理后台、1v1 Chat 中使用。

---

## 6. 需要新增的文件清单

| 文件 | 用途 |
|------|------|
| `cloudflare/d1/schema_v2.sql` | D1 + SQLite 通用的 v2 建表语句 |
| `backend/tools/migrate_v1_to_v2.py` | v1→v2 迁移脚本（seed.json → seed_v2.json + SQLite） |
| `data/seed_v2.json` | 新格式数据文件（先空，按区逐批填入） |
| `data/seed_v2_schema.md` | 已创建 ✅ |

### 不改的文件

| 文件 | 原因 |
|------|------|
| `data/seed.json` | v1 数据不动，保留兼容 |
| `index.html` 前端 | 通过 API adapter 兼容，不改前端代码 |
| `.github/workflows/*` | 禁止修改 |

---

## 7. 实施优先级

| 顺序 | 任务 | 依赖 |
|:----:|------|------|
| 1 | 写 `schema_v2.sql` 建表语句 | 无 |
| 2 | 写 `migrate_v1_to_v2.py` 迁移脚本 | 依赖 1 |
| 3 | 跑迁移，产出 `seed_v2.json` | 依赖 2 |
| 4 | **人工确认杨浦区 20 所数据** | 依赖 3 |
| 5 | 改 `backend/server.py`：新增 v2 API + bootstrap adapter | 依赖 4 确认后 |
| 6 | 改 `admin/index.html`：管理台对接 v2 API | 依赖 5 |
| 7 | 同步 `cloudflare/d1/schema_v2.sql` | 与 5 并行 |

---

## 8. 传递给 QA 的验证点

迁移完成后，请 QA 重点验证：

1. **数据完整性**：v1 的 170+ 所学校在 v2 中一所不少
2. **中签率计算**：`rate = admitted / max_lottery * 100`，精度到小数点后两位
3. **前端兼容**：`/api/bootstrap` 返回的 v1 格式与迁移前完全一致（diff 比较）
4. **来源标注**：所有 profile 默认为 `ai-draft`，不能有冒充 `official` 的
5. **杨浦区抽查**：20 所学校的 name/district/type/tier/admitted/maxLottery 逐字段核对
