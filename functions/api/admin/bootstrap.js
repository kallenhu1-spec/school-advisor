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

function validatePayload(payload) {
  if (!payload || typeof payload !== "object") return "payload 必须是对象";
  if (!Array.isArray(payload.SD)) return "payload.SD 必须是数组";
  if (!payload.PR || typeof payload.PR !== "object" || Array.isArray(payload.PR)) return "payload.PR 必须是对象";
  if (!payload.TF || typeof payload.TF !== "object" || Array.isArray(payload.TF)) return "payload.TF 必须是对象";
  if (!payload.DN || typeof payload.DN !== "object" || Array.isArray(payload.DN)) return "payload.DN 必须是对象";
  return "";
}

function authorized(req, token) {
  if (!token) return false;
  const auth = req.headers.get("Authorization") || "";
  const m = auth.match(/^Bearer\s+(.+)$/i);
  if (!m) return false;
  return m[1].trim() === token.trim();
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: withCors() });
}

export async function onRequestPost(context) {
  const db = context.env.DB;
  const token = context.env.PUBLISH_TOKEN || "";
  if (!db) return json({ error: "D1 binding DB is missing" }, 500);
  if (!authorized(context.request, token)) return json({ error: "Unauthorized" }, 401);

  let payload;
  try {
    payload = await context.request.json();
  } catch {
    return json({ error: "请求体不是合法 JSON" }, 400);
  }
  const err = validatePayload(payload);
  if (err) return json({ error: err }, 400);

  const now = new Date().toISOString();
  await db
    .prepare(
      "INSERT INTO bootstrap_payload(id, payload_json, updated_at) VALUES(1, ?, ?) ON CONFLICT(id) DO UPDATE SET payload_json=excluded.payload_json, updated_at=excluded.updated_at",
    )
    .bind(JSON.stringify(payload), now)
    .run();

  return json(
    {
      ok: true,
      updatedAt: now,
      counts: {
        schools: payload.SD.length,
        profiles: Object.keys(payload.PR || {}).length,
        tuition: Object.keys(payload.TF || {}).length,
      },
    },
    200,
  );
}
