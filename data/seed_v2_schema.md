# seed_v2.json 数据格式定义

> 版本：v2.0 | 创建日期：2026-04-02 | 状态：已确认

## 设计原则

1. **数据诚实**：每个字段都要能标注来源，没有依据的数据不放
2. **去掉主观评分**：不含 score、heat、hw、stress、ideas 等无依据字段
3. **SD + PR 合并**：一个学校一个对象，不再分两个变量
4. **中签率 = 录取数 / 最大摇号数**：只存原始数据，rate 自动算

## 完整结构

```json
{
  "version": "2.0",
  "generatedAt": "2026-04-02",
  "schools": [
    {
      "name": "民办打一外国语小学",
      "officialName": "上海民办打一外国语小学",
      "district": "yangpu",
      "type": "pri",
      "tier": "T1",
      "lat": 31.2834,
      "lng": 121.5224,
      "desc": "T1民办，英语特色，对口铁岭中学",

      "admission": {
        "rate": 43.9,
        "rateYear": 2025,
        "admitted": 151,
        "maxLottery": 344,
        "admissionSource": "official",
        "admissionUrl": "https://www.shyp.gov.cn/...pdf"
      },

      "profile": {
        "tag": "双语国际·杨浦民办T1",
        "philosophy": "让每一个孩子拥有国际视野",
        "path": ["铁岭中学", "民办初中"],
        "pros": ["英语环境好", "升学路径清晰"],
        "cons": ["摇号竞争激烈", "课业偏重"],
        "sourceLevel": "ai-draft",
        "sourceNote": "AI生成，待真实来源核实"
      },

      "links": {
        "map": null,
        "xhs": "民办打一外国语小学 口碑",
        "dianping": null
      }
    }
  ],

  "TF": {},
  "DN": {}
}
```

## 字段说明

### 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `name` | string | Y | 前端显示的短名 |
| `officialName` | string | Y | 官方全称（来自招生简章/PDF） |
| `district` | string | Y | 区域 code（yangpu/xuhui/pudong 等） |
| `type` | string | Y | `pri`（民办）/ `pub`（公办） |
| `tier` | string | Y | 梯队：T1 / T2 / T3 |
| `lat` | number | N | 纬度 |
| `lng` | number | N | 经度 |
| `desc` | string | N | 一句话简介 |

### admission（招生数据）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `rate` | number\|null | N | 中签率（%），= admitted / maxLottery * 100 |
| `rateYear` | number | Y* | 中签率对应的年份，与 admitted/maxLottery 同年 |
| `admitted` | number\|null | N | 该年录取人数 |
| `maxLottery` | number\|null | N | 该年最大摇号人数 |
| `admissionSource` | string | Y* | 来源级别：official / verified / community / ai-draft |
| `admissionUrl` | string\|null | N | 来源链接（官方 PDF 或网页） |

> *当 admitted 和 maxLottery 都为 null 时，整个 admission 可以为 null

### profile（口碑信息）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `tag` | string | N | 分类标签（我们自定义，如"双语国际·杨浦民办T1"） |
| `philosophy` | string\|null | N | 学校官方教育理念（来自官网/招生简章） |
| `path` | string[] | N | 升学路径（可查证的对口/直升学校） |
| `pros` | string[] | N | 优点 |
| `cons` | string[] | N | 注意点 |
| `sourceLevel` | string | Y | 口碑来源级别：official / verified / community / ai-draft |
| `sourceNote` | string | N | 来源说明 |

### links（外部链接）

| 字段 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `map` | string\|null | N | 地图链接 |
| `xhs` | string\|null | N | 小红书搜索关键词或链接 |
| `dianping` | string\|null | N | 大众点评链接 |

## 来源级别定义

| 级别 | 含义 | 前端展示 |
|------|------|---------|
| `official` | 学校官网、教育局文件、招生简章 | ✅ 官方来源 |
| `verified` | 有据可查的第三方整理 | 🔵 已核实 |
| `community` | 真实家长帖子，有原帖链接 | 🟠 社区口碑 |
| `ai-draft` | AI 生成，未经核实 | ⚠️ 仅供参考 |

## 与 v1（seed.json）的对应关系

| v1 字段 | v2 字段 | 备注 |
|---------|---------|------|
| SD[0] name | `name` | |
| SD[1] district | `district` | |
| SD[2] type | `type` | |
| SD[3] rateLow | `admission.rate` | 只保留单值 |
| SD[4] rateHigh | 删除 | |
| SD[5] score | 删除 | 无依据 |
| SD[6] desc | `desc` | |
| SD[7] lat | `lat` | |
| SD[8] lng | `lng` | |
| SD[9] heat | 删除 | 无依据 |
| SD[10] tier | `tier` | |
| SD[11] admitted | `admission.admitted` | |
| SD[12] maxLottery | `admission.maxLottery` | |
| PR.philosophy | `profile.philosophy` | 原 slogan |
| PR.hw | 删除 | 无依据 |
| PR.stress | 删除 | 无依据 |
| PR.ideas | 删除 | 无依据 |

## 迁移策略

1. 新数据先写入 `data/seed_v2.json`，不动 `data/seed.json`
2. 按区逐批填充，第一批：杨浦区
3. 用户人工确认后，再替换正式数据
4. 前端用 adapter 函数兼容 v1/v2 格式
