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

const ENABLE_1V1_DECISION = false; // 线上下线开关：false=下线（保留代码）
const MAX_EVIDENCE_SCHOOLS = 3;
const MAX_EVIDENCE_PER_QUERY = 3;
const EVIDENCE_TTL_HOURS = 36;

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

function estimatePromptTokens(messages, profile, schoolHints, evidencePack) {
  let total = 380; // system + scaffolding reserve
  total += estimatedTokensFromText(JSON.stringify(profile || {}));
  total += estimatedTokensFromText(JSON.stringify(schoolHints || []));
  total += estimatedTokensFromText(JSON.stringify(evidencePack || []));
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

async function ensureEvidenceTables(db) {
  if (!db) return;
  await db
    .prepare(
      "CREATE TABLE IF NOT EXISTS school_evidence_cache(id INTEGER PRIMARY KEY AUTOINCREMENT, school_name TEXT NOT NULL, query_text TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL, snippet TEXT NOT NULL DEFAULT '', source_type TEXT NOT NULL DEFAULT 'web', published_at TEXT, fetched_at TEXT NOT NULL, UNIQUE(school_name, query_text, url))",
    )
    .run();
}

function evidenceQueryTemplates(schoolName) {
  const q = toStr(schoolName).trim();
  if (!q) return [];
  return [
    `${q} 校长`,
    `${q} 开放日 体验`,
    `${q} 作业`,
    `${q} 理念`,
  ];
}

function normalizeEvidenceItem(item, queryText) {
  const o = safeObj(item);
  const title = toStr(o.title || o.name).trim();
  const url = toStr(o.url || o.link).trim();
  if (!title || !url) return null;
  const snippet = toStr(o.snippet || o.summary || o.description).trim();
  const sourceType = toStr(o.source_type || o.source || "web").trim() || "web";
  const publishedAt = toStr(o.published_at || o.date || o.publish_time).trim() || null;
  return {
    queryText,
    title: title.slice(0, 180),
    url: url.slice(0, 800),
    snippet: snippet.slice(0, 400),
    sourceType: sourceType.slice(0, 40),
    publishedAt,
  };
}

async function fetchEvidenceByQuery(env, queryText) {
  const endpoint = toStr(env?.EVIDENCE_SEARCH_ENDPOINT).trim();
  if (!endpoint) return [];
  const apiKey = toStr(env?.EVIDENCE_SEARCH_API_KEY).trim();
  // Expected response shape:
  // { results: [{ title, url, snippet, source_type, published_at }] }
  // Also supports: { items: [...] } or { data: [...] }.
  const url = `${endpoint.replace(/\/$/, "")}?q=${encodeURIComponent(queryText)}&top=${MAX_EVIDENCE_PER_QUERY}`;
  const headers = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
  const res = await fetch(url, { headers });
  if (!res.ok) throw new Error(`evidence search HTTP ${res.status}`);
  const data = await res.json();
  const rows = safeArray(data?.results || data?.items || data?.data);
  return rows
    .map((x) => normalizeEvidenceItem(x, queryText))
    .filter(Boolean)
    .slice(0, MAX_EVIDENCE_PER_QUERY);
}

async function saveEvidenceRows(db, schoolName, rows) {
  if (!db || !rows.length) return;
  const now = new Date().toISOString();
  for (const r of rows) {
    try {
      await db
        .prepare(
          "INSERT INTO school_evidence_cache(school_name, query_text, title, url, snippet, source_type, published_at, fetched_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(school_name, query_text, url) DO UPDATE SET title = excluded.title, snippet = excluded.snippet, source_type = excluded.source_type, published_at = excluded.published_at, fetched_at = excluded.fetched_at",
        )
        .bind(
          schoolName,
          r.queryText,
          r.title,
          r.url,
          r.snippet || "",
          r.sourceType || "web",
          r.publishedAt,
          now,
        )
        .run();
    } catch {}
  }
}

async function readCachedEvidence(db, schoolName) {
  if (!db) return [];
  const rows = await db
    .prepare(
      "SELECT query_text, title, url, snippet, source_type, published_at, fetched_at FROM school_evidence_cache WHERE school_name = ? AND fetched_at >= datetime('now', ?) ORDER BY fetched_at DESC LIMIT 24",
    )
    .bind(schoolName, `-${EVIDENCE_TTL_HOURS} hours`)
    .all();
  return safeArray(rows?.results).map((r) => ({
    queryText: toStr(r.query_text),
    title: toStr(r.title),
    url: toStr(r.url),
    snippet: toStr(r.snippet),
    sourceType: toStr(r.source_type) || "web",
    publishedAt: toStr(r.published_at) || null,
    fetchedAt: toStr(r.fetched_at),
  }));
}

function rankEvidenceRows(rows) {
  return safeArray(rows)
    .filter((r) => toStr(r.url) && toStr(r.title))
    .sort((a, b) => {
      const as = toStr(a.sourceType) === "official" ? 2 : 1;
      const bs = toStr(b.sourceType) === "official" ? 2 : 1;
      if (bs !== as) return bs - as;
      return toStr(b.fetchedAt).localeCompare(toStr(a.fetchedAt));
    })
    .slice(0, 8);
}

async function collectSchoolEvidence({ env, db, schoolHints }) {
  const schools = safeArray(schoolHints).slice(0, MAX_EVIDENCE_SCHOOLS);
  const out = [];
  for (const s of schools) {
    const schoolName = toStr(s?.name).trim();
    if (!schoolName) continue;
    let merged = [];
    const queries = evidenceQueryTemplates(schoolName);
    if (queries.length) {
      for (const q of queries) {
        try {
          const fetched = await fetchEvidenceByQuery(env, q);
          if (fetched.length) {
            await saveEvidenceRows(db, schoolName, fetched);
            merged = merged.concat(
              fetched.map((x) => ({ ...x, fetchedAt: new Date().toISOString() })),
            );
          }
        } catch {}
      }
    }
    if (!merged.length) {
      try {
        merged = await readCachedEvidence(db, schoolName);
      } catch {}
    }
    out.push({
      schoolName,
      evidence: rankEvidenceRows(merged),
    });
  }
  return out;
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
  const oneLiner = `这批候选校里，没有“绝对最好”，当前更像是“高确定性”和“高能力培养”两类路径的取舍。`;
  return {
    reply:
      `我先给你一版可执行的1v1评估草案。\n` +
      `家庭画像：${profileBrief(profile)}。\n` +
      `${schoolText}\n${oneLiner}`,
    structured: {
      next_questions: [
        "你的首要目标更偏向升学确定性，还是长期能力（表达/问题定义/创造）？",
        "可接受单程通勤上限和年预算区间分别是多少？",
        "孩子目前的自主性与抗压水平更接近高、中、低哪一档？",
      ],
      candidate_schools: schools,
      paths: [
        { name: "保守", summary: "优先入学确定性与家庭执行稳定性。" },
        { name: "均衡", summary: "在能力培养与录取把握之间做平衡。" },
        { name: "冲刺", summary: "优先教育模式高匹配，接受更高不确定性。" },
      ],
      risk_alerts: ["当前为本地草案，关键证据与课堂样本仍不足，结论需核验。"],
      action_items: ["补充开放日课堂观察、作业样本、家长连续反馈后再定最终志愿。"],
      assessment: {
        one_liner: oneLiner,
        school_portrait: `${district}候选校呈现“确定性优先”和“能力培养优先”两种教育模式，需按家庭目标二选一或做分层组合。`,
        comparison_conclusion: "当前更建议先做目标分层，再做学校排序，不建议直接按总分下结论。",
        key_evidence: ["已有区域候选与基础画像", "缺少课堂样本与连续家长反馈", "缺少AI学习方法落地证据"],
        advantages: ["可快速生成冲稳保候选", "能提炼家庭约束并给出下一步动作"],
        risks: ["证据链不足时误判风险高", "宣传口径与真实执行可能存在偏差"],
        family_fit_advice: "若家庭重确定性，优先保守/均衡路径；若家庭能承接试错且孩子自主性强，可保留冲刺位。",
        confidence: { level: "medium", score: 0.56, reason: "当前仅有基础画像与有限证据，未完成课堂机制核验。" },
        missing_info: ["作业与评价样本", "真实课堂观察", "高年级升学压力下理念是否变形"],
        six_layers: {
          goal_layer: "候选校目标存在差异：部分偏升学确定性，部分偏综合能力。",
          mechanism_layer: "缺少课程结构与评价rubric实证，机制判断置信度中低。",
          ai_integration_layer: "尚未见到AI进入学习方法层的稳定证据。",
          cognitive_layer: "表达与项目能力培养潜力待核验，当前无法给强结论。",
          constraints_layer: "入学不确定性、通勤与家庭投入是主要现实约束。",
          family_fit_layer: "适配取决于家庭对确定性与能力培养的权重分配。",
        },
      },
      school_reports: schools.map((s) => ({
        school: s.name,
        advantages: ["具备基础画像，可进入候选池。"],
        concerns: ["缺少课堂与作业证据，需核验真实执行。"],
        judgement: "先纳入对比，再根据证据强度决定去留。",
        scores: {
          respect_individuality: 7,
          homework_pressure_fit: 7,
          sports_health: 7,
          creativity_teaching: 7,
        },
      })),
      evidence_chain: [],
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
      // r[11]=录取数, r[12]=最大摇号数（可选扩展字段）
      admission: Number.isFinite(Number(r[11])) ? Number(r[11]) : null,
      maxLottery: Number.isFinite(Number(r[12])) && Number(r[12]) > 0 ? Number(r[12]) : null,
      name: toStr(r[0]),
      type: r[2] === "pub" ? "公办" : r[2] === "pri" ? "民办" : "未知",
      tier: toStr(r[10]) || "未知",
      lottery:
        Number.isFinite(Number(r[11])) && Number.isFinite(Number(r[12])) && Number(r[12]) > 0
          ? `${Math.round((Number(r[11]) * 1000) / Number(r[12])) / 10}%`
          : typeof r[3] === "number" && r[3] > 0
            ? `${r[3]}%`
            : "站内暂无中签率",
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

function tryParseJsonObject(raw) {
  const txt = toStr(raw).trim();
  if (!txt) return null;
  try {
    return JSON.parse(txt);
  } catch {}
  const start = txt.indexOf("{");
  const end = txt.lastIndexOf("}");
  if (start >= 0 && end > start) {
    try {
      return JSON.parse(txt.slice(start, end + 1));
    } catch {}
  }
  return null;
}

function normalizeStructured(structured, schoolHints) {
  const s = safeObj(structured);
  const assessment = safeObj(s.assessment);
  const out = {
    next_questions: safeArray(s.next_questions).map(toStr).filter(Boolean).slice(0, 1),
    candidate_schools: safeArray(s.candidate_schools).slice(0, 8),
    paths: safeArray(s.paths).slice(0, 5),
    risk_alerts: safeArray(s.risk_alerts).map(toStr).filter(Boolean).slice(0, 6),
    action_items: safeArray(s.action_items).map(toStr).filter(Boolean).slice(0, 6),
    assessment: {
      one_liner: toStr(assessment.one_liner).trim(),
      school_portrait: toStr(assessment.school_portrait).trim(),
      comparison_conclusion: toStr(assessment.comparison_conclusion).trim(),
      key_evidence: safeArray(assessment.key_evidence).map(toStr).filter(Boolean).slice(0, 6),
      advantages: safeArray(assessment.advantages).map(toStr).filter(Boolean).slice(0, 6),
      risks: safeArray(assessment.risks).map(toStr).filter(Boolean).slice(0, 6),
      family_fit_advice: toStr(assessment.family_fit_advice).trim(),
      confidence: {
        level: toStr(safeObj(assessment.confidence).level || "medium"),
        score: Number.isFinite(Number(safeObj(assessment.confidence).score))
          ? Math.max(0, Math.min(1, Number(safeObj(assessment.confidence).score)))
          : 0.5,
        reason: toStr(safeObj(assessment.confidence).reason).trim(),
      },
      missing_info: safeArray(assessment.missing_info).map(toStr).filter(Boolean).slice(0, 8),
      six_layers: {
        goal_layer: toStr(safeObj(assessment.six_layers).goal_layer).trim(),
        mechanism_layer: toStr(safeObj(assessment.six_layers).mechanism_layer).trim(),
        ai_integration_layer: toStr(safeObj(assessment.six_layers).ai_integration_layer).trim(),
        cognitive_layer: toStr(safeObj(assessment.six_layers).cognitive_layer).trim(),
        constraints_layer: toStr(safeObj(assessment.six_layers).constraints_layer).trim(),
        family_fit_layer: toStr(safeObj(assessment.six_layers).family_fit_layer).trim(),
      },
    },
    school_reports: safeArray(s.school_reports).slice(0, 6),
    evidence_chain: safeArray(s.evidence_chain).slice(0, 12),
  };
  if (!out.candidate_schools.length) {
    out.candidate_schools = safeArray(schoolHints).slice(0, 5);
  }
  return out;
}

async function callQwenCompatible({ apiKey, model, baseUrl, messages, profile, schoolHints, evidencePack }) {
  const latestUserText = messages.length ? messages[messages.length - 1].content : "";
  const advisorSkill = inferAdvisorSkill(latestUserText);
  const systemPrompt =
    "你是一个面向中国家庭的择校决策助手。核心任务是基于学校信息、家庭约束与孩子画像，降低决策不确定性，而不是生成宣传文案。\n" +
    "你不是学校宣传官，不是泛教育评论员，也不是只会按分数排序的工具。\n" +
    "行为原则：适配优先；机制优先于口号；先证据后结论；不确定就明确标注；判断克制、结构化。\n" +
    "请重点评估：教育目标层、学习机制层、AI整合层、认知能力层、现实约束层、家庭适配层。\n" +
    "回答顺序强制：先直接给结论和建议，再给依据；不要一上来连续提问。\n" +
    "如关键信息缺失，最多提出1个澄清问题，且放在回复末尾。\n" +
    `本轮技能流：${advisorSkill}。\n` +
    "只输出 JSON，不要 markdown，不要额外解释。\n" +
    "JSON 顶层必须包含：reply, structured。\n" +
    "structured 必须包含：next_questions, candidate_schools, paths, risk_alerts, action_items, assessment, school_reports, evidence_chain。\n" +
    "assessment 必须包含：one_liner, school_portrait, comparison_conclusion, key_evidence[], advantages[], risks[], family_fit_advice, confidence{level,score,reason}, missing_info[], six_layers{goal_layer,mechanism_layer,ai_integration_layer,cognitive_layer,constraints_layer,family_fit_layer}。\n" +
    "school_reports 每项包含：school, advantages[], concerns[], judgement, scores(respect_individuality/homework_pressure_fit/sports_health/creativity_teaching)。\n" +
    "evidence_chain 每项包含：school, claim, source_type, title, url, snippet。\n" +
    "禁止给“最好/第一名”绝对结论；证据不足时必须写“需核验”。\n";

  const userPrompt =
    `家庭画像: ${profileBrief(profile)}\n` +
    `区域候选学校: ${JSON.stringify(schoolHints, null, 2)}\n` +
    `可用证据包: ${JSON.stringify(evidencePack || [], null, 2)}\n` +
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
  const out = tryParseJsonObject(raw);
  if (!out) throw new Error("Qwen invalid JSON response");
  return {
    reply: toStr(out.reply) || "我先给你一个初步建议：先明确硬约束，再做冲稳保分层。",
    structured: normalizeStructured(out.structured, schoolHints),
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
  if (!ENABLE_1V1_DECISION) {
    return json(
      {
        ok: false,
        code: "feature_disabled",
        reply: "1v1 决策顾问暂时下线，功能迭代完成后会重新开放。",
      },
      410,
    );
  }

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
  let evidencePack = [];

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
    return json(
      {
        ok: false,
        code: "llm_unavailable",
        reply: "当前模型未配置，暂时无法完成这次1v1分析。请配置 API Key 后重试。",
      },
      503,
    );
  }

  try {
    await ensureUsageTables(context.env.DB);
    await ensureEvidenceTables(context.env.DB);
    evidencePack = await collectSchoolEvidence({
      env: context.env,
      db: context.env.DB,
      schoolHints,
    });
  } catch (e) {
    return json(
      {
        ok: false,
        code: "llm_unavailable",
        reply: "当前模型服务暂时不可用，请稍后重试。",
        error: String(e),
      },
      503,
    );
  }

  try {
    const used = await readClientUsed(context.env.DB, dayKey, clientKey);
    if (used >= freePerDay) {
      return json(
        {
          ok: false,
          code: "quota_exceeded",
          reply: `今日1v1对话次数已达上限（${freePerDay}次），请明天再试或提升额度。`,
          quota: { freePerDay, used, dayKey },
        },
        429,
      );
    }
    const spent = await readDailySpent(context.env.DB, dayKey);
    // Preflight estimate to avoid overspending.
    const estimatedPrompt = estimatePromptTokens(messages, profile, schoolHints, evidencePack);
    const estimatedCompletion = 650;
    const preflightCost = calcCostCNY(model, estimatedPrompt, estimatedCompletion);
    if (spent + preflightCost > dailyBudgetCNY) {
      return json(
        {
          ok: false,
          code: "budget_exceeded",
          reply: `今日AI预算已达上限（¥${dailyBudgetCNY.toFixed(2)}/天），请稍后再试。`,
          budget: { dayKey, spentCNY: Number(spent.toFixed(6)), dailyBudgetCNY },
        },
        429,
      );
    }
  } catch (e) {
    return json(
      {
        ok: false,
        code: "llm_unavailable",
        reply: "当前模型服务暂时不可用，请稍后重试。",
        error: String(e),
      },
      503,
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
      evidencePack,
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
    return json(
      {
        ok: false,
        code: "llm_unavailable",
        reply: "当前模型连接暂时不可用，请重试一次。",
        error: String(e),
      },
      503,
    );
  }
}
