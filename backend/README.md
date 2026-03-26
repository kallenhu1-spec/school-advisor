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

## 本地后台（审核台）
启动后访问：

`http://127.0.0.1:8787/admin/`

可完成：
- 编辑 `config/sources.json` 数据源配置
- 触发自动采集（按数据源类型）
- 导入提案到待审核队列
- 批量通过 / 批量驳回提案
- 学校列表可视化筛选（区 / 梯队 / 公民办）
- 点击学校查看详情（含 SD + PR + TF 聚合信息）
- Excel 上传导入学校数据（.xlsx）
- 支持在学校列表直接调整梯队，并一键推送到前台数据

## API
- `GET /api/health`
- `GET /api/bootstrap`
- `PUT /api/bootstrap`（整包更新）
- `GET /api/admin/sources`
- `PUT /api/admin/sources`
- `POST /api/admin/collect/run`
- `GET /api/admin/proposals?status=pending|approved|rejected|all`
- `POST /api/admin/proposals/import`
- `POST /api/admin/proposals/review`
- `GET /api/policy-events`
- `GET /api/admin/schools?district=&tier=&type=&q=`
- `GET /api/admin/school-detail?name=学校名`
- `POST /api/admin/schools/import-xlsx`
- `POST /api/admin/schools/tier-batch-update`
- `POST /api/admin/schools/push-changes`（梯队调整+删校统一推送）

`PUT /api/bootstrap` 请求体格式：
```json
{
  "SD": [],
  "PR": {},
  "TF": {},
  "DN": {}
}
```
