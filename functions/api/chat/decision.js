function withCors(headers = {}) {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,PUT,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    ...headers,
  };
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: withCors({ "Content-Type": "application/json; charset=utf-8" }),
  });
}

const MODEL_PRICING_CNY_PER_M = {
  "qwen-turbo": { in: 0.3, out: 0.6 },
  "qwen-turbo-latest": { in: 0.3, out: 0.6 },
  "qwen-plus": { in: 0.8, out: 2.0 },
  "qwen-plus-latest": { in: 0.8, out: 2.0 },
  "qwen-max": { in: 2.4, out: 9.6 },
  "qwen-max-latest": { in: 2.4, out: 9.6 },
  "qwen3.5-flash": { in: 0.2, out: 2.0 },
};

function utcDayKey() {
  return new Date().toISOString().slice(0, 10);
}

function parseNum(v, dft) {
  const n = Number(v);
  return Number.isFinite(n) ? n : dft;
}

function estimatedTokensFromText(text) {
  const t = toStr(text);
  if (!t) return 0;
  // Conservative estimate for mixed Chinese/English content.
  return Math.ceil(t.length * 0.7);
}

function estimatePromptTokens(messages, profile, schoolHints) {
  let total = 380; // system + scaffolding reserve
  total += estimatedTokensFromText(JSON.stringify(profile || {}));
  total += estimatedTokensFromText(JSON.stringify(schoolHints || []));
  safeArray(messages).forEach((m) => {
    total += estimatedTokensFromText(m.content);
  });
  return total;
}

function calcCostCNY(model, promptTokens, completionTokens) {
  const p = MODEL_PRICING_CNY_PER_M[model] || MODEL_PRICING_CNY_PER_M["qwen-turbo-latest"];
  const inCost = (Math.max(0, promptTokens) * p.in) / 1_000_000;
  const outCost = (Math.max(0, completionTokens) * p.out) / 1_000_000;
  return inCost + outCost;
}

function pickClientKey(req) {
  const ip =
    req.headers.get("CF-Connecting-IP") ||
    toStr(req.headers.get("X-Forwarded-For")).split(",")[0] ||
    "unknown";
  return `ip:${toStr(ip).trim().slice(0, 64) || "unknown"}`;
}

async function ensureUsageTables(db) {
  if (!db) return;
  await db
    .prepare(
      "CREATE TABLE IF NOT EXISTS chat_budget(day_key TEXT PRIMARY KEY, spent_usd REAL NOT NULL DEFAULT 0, updated_at TEXT NOT NULL)",
    )
    .run();
  await db
    .prepare(
      "CREATE TABLE IF NOT EXISTS chat_usage(day_key TEXT NOT NULL, client_key TEXT NOT NULL, used_count INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, PRIMARY KEY(day_key, client_key))",
    )
    .run();
}

async function readDailySpent(db, dayKey) {
  if (!db) return 0;
  const row = await db.prepare("SELECT spent_usd FROM chat_budget WHERE day_key = ?").bind(dayKey).first();
  return row && Number.isFinite(Number(row.spent_usd)) ? Number(row.spent_usd) : 0;
}

async function readClientUsed(db, dayKey, clientKey) {
  if (!db) return 0;
  const row = await db
    .prepare("SELECT used_count FROM chat_usage WHERE day_key = ? AND client_key = ?")
    .bind(dayKey, clientKey)
    .first();
  return row && Number.isFinite(Number(row.used_count)) ? Number(row.used_count) : 0;
}

async function addUsage(db, dayKey, clientKey, addCount, addUsd) {
  if (!db) return;
  const now = new Date().toISOString();
  await db
    .prepare(
      "INSERT INTO chat_usage(day_key, client_key, used_count, updated_at) VALUES(?, ?, ?, ?) ON CONFLICT(day_key, client_key) DO UPDATE SET used_count = chat_usage.used_count + excluded.used_count, updated_at = excluded.updated_at",
    )
    .bind(dayKey, clientKey, Math.max(0, addCount), now)
    .run();
  await db
    .prepare(
      "INSERT INTO chat_budget(day_key, spent_usd, updated_at) VALUES(?, ?, ?) ON CONFLICT(day_key) DO UPDATE SET spent_usd = chat_budget.spent_usd + excluded.spent_usd, updated_at = excluded.updated_at",
    )
    .bind(dayKey, Math.max(0, addUsd), now)
    .run();
}

function toStr(v) {
  return typeof v === "string" ? v : "";
}

function safeArray(v) {
  return Array.isArray(v) ? v : [];
}

function safeObj(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}

function trimMessages(messages) {
  return safeArray(messages)
    .map((m) => ({
      role: toStr(m?.role) === "assistant" ? "assistant" : "user",
      content: toStr(m?.content).trim(),
    }))
    .filter((m) => m.content)
    .slice(-12);
}

function inferDistrictLabel(code) {
  const m = {
    pudong: "浦东新区",
    minhang: "闵行区",
    xuhui: "徐汇区",
    changning: "长宁区",
    jingan: "静安区",
    huangpu: "黄浦区",
    putuo: "普陀区",
    yangpu: "杨浦区",
    hongkou: "虹口区",
    jiading: "嘉定区",
    qingpu: "青浦区",
  };
  return m[code] || code || "未提供";
}

function profileBrief(profile) {
  const p = safeObj(profile);
  const f = safeArray(p.focus).filter(Boolean);
  return `户籍=${toStr(p.household) || "未提供"}；区域=${inferDistrictLabel(toStr(p.district))}；意向=${toStr(p.intentType) || "未提供"}；关注=${f.join("/") || "未提供"}`;
}

function buildLocalDraft(input, profile, schoolHints) {
  const district = inferDistrictLabel(toStr(profile?.district));
  const schools = safeArray(schoolHints).slice(0, 4);
  const schoolText = schools.length
    ? `你所在区域候选（示例）: ${schools.map((s) => s.name).join("、")}。`
    : "当前未读取到区域候选学校，我会先按通用框架梳理。";
  return {
    reply:
      `我先给你一版可执行的1v1决策梳理。\n` +
      `家庭画像：${profileBrief(profile)}。\n` +
      `${schoolText}\n` +
      `建议按三步走：先定硬约束（户籍/预算/通勤）→再定偏好权重（学业强度/双语/升学路径）→最后做冲稳保三档志愿。` +
      `\n如果你愿意，我下一轮可以直接输出“3所主推+2所备选”的清单和理由。`,
    structured: {
      next_questions: [
        "你更希望孩子走体制内中考路线，还是保留国际路线？",
        "可接受单程通勤上限是多少分钟？",
        "能接受的年预算区间大概是多少？",
      ],
      candidate_schools: schools,
      paths: [
        { name: "保守", summary: "优先高确定性入学，控制通勤和成本。" },
        { name: "均衡", summary: "兼顾录取概率、学校口碑和家庭投入强度。" },
        { name: "冲刺", summary: "争取头部学校，接受更高不确定性与投入。" },
      ],
      risk_alerts: [
        "民办摇号不确定性高，需准备公办兜底。",
        "若偏好高强度路线，要提前评估孩子和家庭承压。",
      ],
    },
  };
}

function districtSchoolHints(payload, districtCode) {
  const sd = safeArray(payload?.SD);
  if (!districtCode) return [];
  return sd
    .filter((r) => Array.isArray(r) && r[1] === districtCode)
    .slice(0, 10)
    .map((r) => ({
      name: toStr(r[0]),
      type: r[2] === "pub" ? "公办" : r[2] === "pri" ? "民办" : "未知",
      tier: toStr(r[10]) || "未知",
      lottery: typeof r[3] === "number" ? `${r[3]}%` : "待确认",
    }));
}

async function loadBootstrapFromD1(db) {
  if (!db) return null;
  try {
    const row = await db.prepare("SELECT payload_json FROM bootstrap_payload WHERE id = 1").first();
    if (!row || !row.payload_json) return null;
    return JSON.parse(row.payload_json);
  } catch {
    return null;
  }
}

function inferAdvisorSkill(userText) {
  const q = toStr(userText);
  if (/对比|比较|A\/B|AB|vs/i.test(q)) return "学校对比分析";
  if (/路径|保守|均衡|冲刺|路线/i.test(q)) return "家庭路径建议";
  return "1v1决策梳理";
}

async function callQwenCompatible({ apiKey, model, baseUrl, messages, profile, schoolHints }) {
  const latestUserText = messages.length ? messages[messages.length - 1].content : "";
  const advisorSkill = inferAdvisorSkill(latestUserText);
  const systemPrompt =
    "你是“上海幼升小1v1择校顾问”，请用中文输出 JSON，不要输出 markdown。\n" +
    "你的核心目标：给家长可执行、可落地、带风险提示的建议，避免空泛表述。\n" +
    `本轮技能流：${advisorSkill}。\n` +
    "输出规则：\n" +
    "1) 先提炼家庭硬约束：户籍/预算/通勤/路线偏好。\n" +
    "2) 只基于已给数据做建议；不确定信息必须写“需核验”。\n" +
    "3) 必须输出冲稳保三档路径。\n" +
    "4) 语气克制，不做“保证录取”类承诺。\n" +
    "5) JSON 顶层必须包含：reply, structured。\n" +
    "6) structured 必须包含：next_questions, candidate_schools, paths, risk_alerts, action_items。\n";

  const userPrompt =
    `家庭画像: ${profileBrief(profile)}\n` +
    `区域候选学校: ${JSON.stringify(schoolHints, null, 2)}\n` +
    "请基于以上信息回复。";

  const payload = {
    model,
    response_format: { type: "json_object" },
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: userPrompt },
      ...messages.map((m) => ({ role: m.role, content: m.content })),
    ],
    temperature: 0.4,
    max_tokens: 650,
  };

  const endpoint = `${baseUrl.replace(/\/$/, "")}/chat/completions`;
  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`Qwen error: HTTP ${res.status} ${detail.slice(0, 200)}`);
  }
  const data = await res.json();
  const raw = toStr(data?.choices?.[0]?.message?.content);
  if (!raw) throw new Error("Qwen empty response");
  const out = JSON.parse(raw);
  return {
    reply: toStr(out.reply) || "我先给你一个初步建议：先明确硬约束，再做冲稳保分层。",
    structured: safeObj(out.structured),
    modelUsed: toStr(data?.model) || model,
    usage: {
      promptTokens: Number(data?.usage?.prompt_tokens || 0),
      completionTokens: Number(data?.usage?.completion_tokens || 0),
    },
  };
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: withCors() });
}

export async function onRequestPost(context) {
  let body;
  try {
    body = await context.request.json();
  } catch {
    return json({ error: "请求体不是合法 JSON" }, 400);
  }

  const messages = trimMessages(body?.messages);
  if (!messages.length) {
    return json({ error: "messages 不能为空" }, 400);
  }

  const profile = safeObj(body?.profile);
  const bootstrap = await loadBootstrapFromD1(context.env.DB);
  const schoolHints = districtSchoolHints(bootstrap, toStr(profile?.district));

  const apiKey =
    toStr(context.env.DASHSCOPE_API_KEY) ||
    toStr(context.env.QWEN_API_KEY) ||
    toStr(context.env.OPENAI_API_KEY);
  const model =
    toStr(context.env.QWEN_MODEL) ||
    toStr(context.env.DASHSCOPE_MODEL) ||
    toStr(context.env.OPENAI_MODEL) ||
    "qwen-turbo-latest";
  const baseUrl = toStr(context.env.DASHSCOPE_BASE_URL) || "https://dashscope.aliyuncs.com/compatible-mode/v1";
  const freePerDay = Math.max(1, parseNum(context.env.CHAT_FREE_PER_IP_PER_DAY, 3));
  const dailyBudgetCNY =
    parseNum(context.env.CHAT_DAILY_BUDGET_CNY, NaN) > 0
      ? parseNum(context.env.CHAT_DAILY_BUDGET_CNY, 35)
      : Math.max(1, parseNum(context.env.CHAT_DAILY_BUDGET_USD, 5) * 7.2);
  const roundsLimit = Math.max(4, parseNum(context.env.CHAT_MAX_ROUNDS, 8));
  const dayKey = utcDayKey();
  const clientKey = pickClientKey(context.request);

  if (messages.length > roundsLimit * 2) {
    const sliced = messages.slice(-roundsLimit * 2);
    messages.length = 0;
    sliced.forEach((m) => messages.push(m));
  }

  if (!apiKey) {
    const draft = buildLocalDraft(messages[messages.length - 1].content, profile, schoolHints);
    return json(
      {
        ok: true,
        mode: "local-fallback",
        modelUsed: "local-rule-based",
        ...draft,
        note: "未配置 DASHSCOPE_API_KEY（或 QWEN_API_KEY），当前返回本地草案。",
      },
      200,
    );
  }

  try {
    await ensureUsageTables(context.env.DB);
  } catch (e) {
    const draft = buildLocalDraft(messages[messages.length - 1].content, profile, schoolHints);
    return json(
      {
        ok: true,
        mode: "local-fallback",
        modelUsed: "local-rule-based",
        ...draft,
        note: `成本保护表初始化失败，已降级本地草案：${String(e)}`,
      },
      200,
    );
  }

  try {
    const used = await readClientUsed(context.env.DB, dayKey, clientKey);
    if (used >= freePerDay) {
      const draft = buildLocalDraft(messages[messages.length - 1].content, profile, schoolHints);
      return json(
        {
          ok: true,
          mode: "local-fallback",
          modelUsed: "local-rule-based",
          ...draft,
          note: `今日深度对话次数已达上限（${freePerDay}次），已切换节省模式。`,
          quota: { freePerDay, used, dayKey },
        },
        200,
      );
    }
    const spent = await readDailySpent(context.env.DB, dayKey);
    // Preflight estimate to avoid overspending.
    const estimatedPrompt = estimatePromptTokens(messages, profile, schoolHints);
    const estimatedCompletion = 650;
    const preflightCost = calcCostCNY(model, estimatedPrompt, estimatedCompletion);
    if (spent + preflightCost > dailyBudgetCNY) {
      const draft = buildLocalDraft(messages[messages.length - 1].content, profile, schoolHints);
      return json(
        {
          ok: true,
          mode: "local-fallback",
          modelUsed: "local-rule-based",
          ...draft,
          note: `今日AI预算已接近上限（¥${dailyBudgetCNY.toFixed(2)}/天），已自动降级到本地建议。`,
          budget: { dayKey, spentCNY: Number(spent.toFixed(6)), dailyBudgetCNY },
        },
        200,
      );
    }
  } catch (e) {
    const draft = buildLocalDraft(messages[messages.length - 1].content, profile, schoolHints);
    return json(
      {
        ok: true,
        mode: "local-fallback",
        modelUsed: "local-rule-based",
        ...draft,
        note: `读取成本状态失败，已降级本地草案：${String(e)}`,
      },
      200,
    );
  }

  try {
    const out = await callQwenCompatible({
      apiKey,
      model,
      baseUrl,
      messages,
      profile,
      schoolHints,
    });
    const actualCost = calcCostCNY(model, out.usage.promptTokens, out.usage.completionTokens);
    await addUsage(context.env.DB, dayKey, clientKey, 1, actualCost);
    const usedNow = await readClientUsed(context.env.DB, dayKey, clientKey);
    const spentNow = await readDailySpent(context.env.DB, dayKey);
    return json(
      {
        ok: true,
        mode: "qwen",
        reply: out.reply,
        structured: out.structured,
        modelUsed: out.modelUsed,
        usage: {
          promptTokens: out.usage.promptTokens,
          completionTokens: out.usage.completionTokens,
          estimatedCostCNY: Number(actualCost.toFixed(6)),
        },
        quota: { freePerDay, used: usedNow, dayKey },
        budget: { dailyBudgetCNY, spentCNY: Number(spentNow.toFixed(6)), dayKey },
      },
      200,
    );
  } catch (e) {
    const draft = buildLocalDraft(messages[messages.length - 1].content, profile, schoolHints);
    return json(
      {
        ok: true,
        mode: "local-fallback",
        modelUsed: "local-rule-based",
        ...draft,
        note: `Qwen 调用失败，已降级本地草案：${String(e)}`,
      },
      200,
    );
  }
}
