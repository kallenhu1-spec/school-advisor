---
name: PDF数据采集SOP
description: data-curator采集流程：先拿所有区PDF → 阅读PDF提取正规学校名 → 再逐校提取最大录取数
type: feedback
---

data-curator 的数据采集必须按以下顺序执行：
1. 先把所有区的官方PDF都拿到手
2. 阅读PDF，提取正规的官方学校名
3. 再逐校找到最大录取数字

**Why:** 之前自动提取只拿到每个PDF最后一行数据，效果很差。必须逐步、逐校提取。
**How to apply:** 每次跑 data-curator 时提醒这个顺序，不要跳步。
