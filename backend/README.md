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

## 结构化运营数据导入（推荐）
当运营产出 `schools_structured_v1.jsonl` 后，可先转换为提案再导入审核队列：

```bash
python3 backend/tools/structured_to_proposals.py \
  --input data/curation/schools_structured_v1.jsonl \
  --output data/curation/proposals_from_structured.json \
  --source data-curator:structured-v1

curl http://127.0.0.1:8787/api/admin/proposals/import \
  -H "Content-Type: application/json" \
  -d @data/curation/proposals_from_structured.json
```

说明：
- 转换脚本会生成以下提案类型：`patch_school_fields`、`patch_pr_fields`、`patch_tf_fields`
- `patch_*` 为字段级 merge，不会整条覆盖旧数据，便于新旧对比后再审核通过

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
- 学校列表支持展示 `2025录取数`、`2025最大摇号数`、`参考信息来源网址`
- 点击学校查看详情（含 SD + PR + TF 聚合信息）
- Excel 上传导入学校数据（.xlsx）
- 支持在学校列表直接调整梯队，并一键推送到前台数据
- 支持小红书链接半自动抓取并入待审核（审核通过后自动写入学校字段）
- 支持一键“发布到线上”（写回 `data/seed.json` 并执行 git push 到线上仓库）

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
- `POST /api/admin/xhs/collect-proposals`（小红书链接抓取 -> 生成待审核提案）
- `POST /api/admin/publish-online`（本地后台一键发布到线上仓库）
- `GET /api/admin/publish-online/status?taskId=...`（查询发布任务分步骤进度）

`SD` 学校数组支持扩展字段（可选）：
- 下标 `11`: `2025录取数`（整数）
- 下标 `12`: `2025最大摇号数`（整数）
- 下标 `13`: `参考信息来源网址`（字符串）

`PUT /api/bootstrap` 请求体格式：
```json
{
  "SD": [],
  "PR": {},
  "TF": {},
  "DN": {}
}
```
