# CHANGELOG

## v8.0.0 (2026-03-26)
- 架构升级为前后端分离：前端页面从 API 获取 `SD/PR/TF/DN` 数据
- 新增后端服务：`backend/server.py`（`/api/bootstrap`、`/api/schools`）
- 新增 SQLite 数据库：`data/school_advisor.db`
- 新增数据维护脚本：
  - `backend/tools/extract_embedded_data.py`
  - `backend/tools/seed_db.py`
  - `backend/tools/update_bootstrap.py`
- 新增发布规范文件：`VERSION.json`
- 版本发布文件：
  - 入口：`index.html`
  - 最新：`school-advisor-v8.0.0-latest.html`
  - 快照：`versions/v8.0.0-20260326.html`

## v7.6 (历史)
- 旧版以 `school-advisor-v7.6-latest.html` 为主文件
- 该文件保留用于历史回溯，不再作为最新版本命名
