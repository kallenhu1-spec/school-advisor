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
