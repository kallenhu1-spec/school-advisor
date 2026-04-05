# Data-Curator 执行与上线 Runbook

## 目标
`data-curator` 默认只做“学校数据生产”：把任务 E（官方口径）和任务 D（结构化字段）整合成一条链路，产出可导入后台的结构化结果与 `seed_v2` 产物。

## 前置条件（联网）

1. `data-curator` agent 需启用可联网沙箱（当前配置为 `workspace-write`）。
2. 本机执行脚本需可访问外网（任务 E 需要下载官方 PDF）。
3. 安装依赖：`pypdf`（任务 E PDF 解析用）。

推荐先验证：
```bash
python3 backend/tools/task_e_extract_official.py --help
```

## 阶段 1：官方口径抽取（E）
1. 检索关键词：`2025年上海市民办小学“报名志愿”电脑随机录取名单`
2. 下载各区官方 PDF，记录到：
   - `data/curation/official_pdf_index_2025.json`
3. 逐 PDF 抽取区名、学校名、2025录取数，产出：
   - `data/curation/official_admission_extract_2025.jsonl`

`official_admission_extract_2025.jsonl` 每行示例：
```json
{"district":"minhang","schoolName":"交通大学闵行实验学校小学部","admission2025":128,"pdfUrl":"https://...pdf","pageHint":"p3","reviewerNote":"人工复核通过"}
```

## 阶段 2：结构化字段产出（D）
按 `data-curator.toml` 任务 D 的结构，每行一个学校 JSON，产出：
- `data/curation/schools_structured_v1.jsonl`

## 阶段 2.5：seed_v2 融合产物（E + D 合并）

把 `seed.json` 基础数据 + 任务 E 官方抽取 + 任务 D 结构化结果融合成 `seed_v2` 文件：

```bash
python3 backend/tools/build_seed_v2_district.py \
  --district yangpu \
  --seed-v1 data/seed.json \
  --official data/curation/official_admission_extract_2025.jsonl \
  --structured data/curation/schools_structured_v1.jsonl \
  --output data/seed_v2_yangpu.json
```

产出文件：
- `data/seed_v2_{district}.json`
- `data/seed_v2_school_{name}.json`
- `data/seed_v2_city_{city}.json`

要求：
- 每个字段都要有：`value/currentLevel/targetLevel/origin/method/links`
- `links` 至少 1 条（无则 `{"label":"待补充","url":""}`）

## 阶段 3：导入后台（先不覆盖正式数据）
推荐先导入“待审核”而不是直接覆盖：
1. 把结构化产出转换为后台提案格式（`proposals`）：
```bash
python3 backend/tools/structured_to_proposals.py \
  --input data/curation/schools_structured_v1.jsonl \
  --output data/curation/proposals_from_structured.json \
  --source data-curator:structured-v1
```
2. 调用：
   - `POST /api/admin/proposals/import`

导入示例：
```bash
curl http://127.0.0.1:8788/api/admin/proposals/import \
  -H "Content-Type: application/json" \
  -d @data/curation/proposals_from_structured.json
```
3. 在后台审核队列中查看与筛选

## 阶段 4：新旧对比确认
对每校关键字段做对比：
- `schoolName/district/schoolType/tier`
- `admission2025/maxLottery2025/lotteryRange`
- `desc/philosophy/hwStress/path/pros/cons/tuition`

确认点：
- 是否提升 `currentLevel -> targetLevel`
- 来源链接是否可访问
- 冲突字段是否有 reviewerNote

## 阶段 5：批量替换与发布
1. 审核通过后批量应用
2. 检查后台详情页展示（字段 + 来源 + target/current）
3. 发布线上：
   - `POST /api/admin/publish-online`
4. 用线上页面抽查 10 所学校（含 T1/T2/T3）

## 一键流水线（推荐）

可用单命令串联任务 E -> D -> proposals -> seed_v2：

```bash
python3 backend/tools/run_data_curator_pipeline.py \
  --scope district \
  --district yangpu \
  --index data/curation/official_pdf_index_2025.json \
  --official-output data/curation/official_admission_extract_2025.jsonl \
  --structured-input data/curation/schools_structured_v1.jsonl \
  --proposals-output data/curation/proposals_from_structured.json \
  --seed-v2-output data/seed_v2_yangpu.json
```

新增一个学校（单校模式）：
```bash
python3 backend/tools/run_data_curator_pipeline.py \
  --scope school \
  --school-name "上海师范大学附属杨浦滨江实验小学" \
  --structured-input data/curation/schools_structured_v1.jsonl
```

新增一个城市（城市模式，默认产全量）：
```bash
python3 backend/tools/run_data_curator_pipeline.py \
  --scope city \
  --city shanghai
```

只重建 `seed_v2`（跳过联网抓取 task E）：
```bash
python3 backend/tools/run_data_curator_pipeline.py \
  --scope district \
  --district yangpu \
  --skip-task-e
```

## 回滚
若发布后异常：
1. 使用上一次 `bootstrap` 快照回滚
2. 恢复上一批审核通过前的数据包
3. 记录异常字段与来源链接问题，退回运营修正
