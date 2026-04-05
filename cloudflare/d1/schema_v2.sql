-- schema_v2: 结构化学校数据表（替代 JSON blob）
-- 兼容 SQLite + Cloudflare D1

-- 学校主表
CREATE TABLE IF NOT EXISTS schools (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,                -- 前端显示短名
  official_name TEXT NOT NULL DEFAULT '',     -- 官方全称（来自招生简章/PDF）
  district      TEXT NOT NULL,               -- yangpu/xuhui/pudong...
  type          TEXT NOT NULL,               -- pri(民办)/pub(公办)
  tier          TEXT NOT NULL DEFAULT 'T3',  -- T1/T2/T3
  lat           REAL,
  lng           REAL,
  desc_text     TEXT NOT NULL DEFAULT '',    -- 一句话简介
  link_map      TEXT,                        -- 地图链接
  link_xhs      TEXT,                        -- 小红书关键词或链接
  link_dianping TEXT,                        -- 大众点评链接
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE(name, district)
);

-- 招生数据表（按年存储，支持历史数据）
CREATE TABLE IF NOT EXISTS admissions (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id        INTEGER NOT NULL,          -- 关联 schools.id
  year             INTEGER NOT NULL,          -- 2024/2025/2026...
  admitted         INTEGER,                   -- 录取人数
  max_lottery      INTEGER,                   -- 最大摇号人数
  rate             REAL,                      -- 中签率(%)，= admitted/max_lottery*100
  admission_source TEXT NOT NULL DEFAULT 'ai-draft',  -- official/verified/community/ai-draft
  admission_url    TEXT,                      -- 来源链接（PDF/网页）
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL,
  UNIQUE(school_id, year)
);

-- 口碑信息表（一校一条）
CREATE TABLE IF NOT EXISTS profiles (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  school_id     INTEGER NOT NULL UNIQUE,     -- 关联 schools.id，一校一条
  tag           TEXT NOT NULL DEFAULT '',     -- 分类标签
  philosophy    TEXT,                         -- 官方教育理念（来自官网/招生简章）
  path_json     TEXT NOT NULL DEFAULT '[]',   -- 升学路径 JSON 数组
  pros_json     TEXT NOT NULL DEFAULT '[]',   -- 优点 JSON 数组
  cons_json     TEXT NOT NULL DEFAULT '[]',   -- 注意点 JSON 数组
  source_level  TEXT NOT NULL DEFAULT 'ai-draft',  -- official/verified/community/ai-draft
  source_note   TEXT,                         -- 来源说明
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_schools_district ON schools(district);
CREATE INDEX IF NOT EXISTS idx_schools_type ON schools(type);
CREATE INDEX IF NOT EXISTS idx_admissions_year ON admissions(year);
