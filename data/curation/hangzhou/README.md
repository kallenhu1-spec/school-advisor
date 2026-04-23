# 杭州学校数据工作流

这个目录用于沉淀杭州分站的固定数据生产流程，目标不是一次性手工补数据，而是按“全名单 -> 基础信息 -> 招生信息 -> 学校画像 -> QA”五步反复更新。

## 推荐顺序

1. 先跑官方目录抽取，产出 `school_master_list_hangzhou.jsonl`
2. 再合并进 `data/seed_v2_city_hangzhou.json`
3. 只对热门学校补 `officialUrl / tuition / admission`
4. 最后补学校画像，统一标成“AI总结”
5. 每次更新后跑 `python3 backend/tools/check_hangzhou_seed.py`

## 关键字段优先级

### P0 必须有

- `officialName`
- `district`
- `type`
- `address`
- `sourceUrl`
- `basicInfoSourceLevel`

### P1 上线前尽量有

- `phone`
- `officialUrl`
- `schoolStage`
- `isNineYear`

### P2 招生季补

- `tuition`
- `admissionPlan`
- `admissionUrl`
- `lotteryData`

### P3 体验增强

- `profile`
- `xhs`
- `dianpingSearchName`

## 本轮约束

- 基础信息优先使用官方目录页
- 学校画像缺失时不要造假，用前端兜底展示
- `ai-draft` 只用于画像，不用于基础身份字段

## 夜班自动上班

仓库已预留杭州夜班自动值守工作流：

- 工作流文件：`.github/workflows/hangzhou-night-shift.yml`
- 主控脚本：`scripts/run_hangzhou_night_shift.sh`
- 主Agent计划脚本：`backend/tools/plan_hangzhou_night_shift.py`

默认会在北京时间每 2 小时自动运行一轮，当前时段为：

- 09:30
- 11:30
- 13:30
- 15:30
- 17:30
- 19:30
- 21:30
- 23:30
- 01:30
- 03:30
- 05:30
- 07:30

每次夜班会完成：

1. 重建杭州 seed
2. 跑 QA 检查
3. 由主Agent生成当天工作计划
4. 给仓库创建/更新一条 `night-shift-report` 日报

若希望 data-curator 也自动补数，需要：

- 配置 `OPENAI_API_KEY` secret
- 配置仓库变量 `AUTO_DATA_CURATOR=true`

建议：

- 先只开 QA + 主Agent计划，观察 2-3 天
- 再开启 `AUTO_DATA_CURATOR=true` 进入全自动补数
