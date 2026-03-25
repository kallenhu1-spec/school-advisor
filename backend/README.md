# 后端数据服务（SQLite + Python）

## 目录说明
- `server.py`：提供 API（`/api/bootstrap` 等）
- `tools/extract_embedded_data.py`：从旧 HTML 提取 `SD/PR/TF/DN`
- `tools/seed_db.py`：把提取数据写入 SQLite

## 初始化
```bash
python3 backend/tools/extract_embedded_data.py
python3 backend/tools/seed_db.py
```

## 日常更新数据（推荐）
准备一个包含 `SD/PR/TF/DN` 的 JSON 文件后执行：
```bash
python3 backend/tools/update_bootstrap.py --file /你的路径/new-data.json
```

## 启动 API
```bash
python3 backend/server.py --host 127.0.0.1 --port 8787
```

## API
- `GET /api/health`
- `GET /api/bootstrap`
- `PUT /api/bootstrap`（整包更新）

`PUT /api/bootstrap` 请求体格式：
```json
{
  "SD": [],
  "PR": {},
  "TF": {},
  "DN": {}
}
```
