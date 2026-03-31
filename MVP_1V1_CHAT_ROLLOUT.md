# 1v1 决策顾问上线清单（最小可用版）

## 你现在已经有的能力

- 页面新增了第三个入口：`💬 1v1决策`
- 已新增 API：`POST /api/chat/decision`
- 若未配置大模型 Key，会自动走本地兜底草案，不会白屏
- 对话会自动带入家长在「我的择校」里已填写的画像

---

## 你只需要确认这 4 件事

1. 是否使用千问（DashScope）作为首发模型（推荐：是）
2. 默认模型是否用 `qwen-turbo-latest`（推荐：是，成本低、速度快）
3. 是否先不上用户登录（推荐：是，先验证转化）
4. 是否先不上长期会话记忆（推荐：是，仅本地浏览器保存最近对话）

---

## 上线动作（10-20 分钟）

1. 在 Cloudflare Pages 设置环境变量：
   - `DASHSCOPE_API_KEY`
   - 可选 `QWEN_MODEL`（默认 `qwen-turbo-latest`）
   - 可选 `DASHSCOPE_BASE_URL`（默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`）
   - 可选 `CHAT_FREE_PER_IP_PER_DAY`（建议 `3`）
   - 可选 `CHAT_DAILY_BUDGET_CNY`（建议 `35`）
   - 可选 `CHAT_MAX_ROUNDS`（建议 `8`）
2. 推送当前仓库代码到 Cloudflare 绑定分支
3. 打开线上页面，进入 `💬 1v1决策` 发送一条测试消息
4. 验证接口返回：
   - 有 Key 时：`mode=qwen`
   - 无 Key 时：`mode=local-fallback`
   - 免费次数用完：返回 `mode=local-fallback` 且 `note` 提示额度已达上限
   - 日预算接近上限：返回 `mode=local-fallback` 且 `note` 提示预算降级

---

## 建议的下一步（你确认后我可继续做）

1. 增加「顾问结论卡片」导出（便于家长转发给家人）
2. 增加「对比模式」固定模板（学校 A/B/C 维度打分）
3. 增加「留资闭环」：对话后引导预约 1v1 咨询
