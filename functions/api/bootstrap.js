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

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: withCors() });
}

export async function onRequestGet(context) {
  const db = context.env.DB;
  if (!db) {
    return json({ error: "D1 binding DB is missing" }, 500);
  }

  let row = null;
  try {
    row = await db.prepare("SELECT payload_json, updated_at FROM bootstrap_payload WHERE id = 1").first();
  } catch (e) {
    return json(
      {
        error: "D1 query failed",
        detail: String(e),
        hint: "请先在 D1 执行建表 SQL（bootstrap_payload）",
      },
      500,
    );
  }

  if (!row || !row.payload_json) {
    return json({ error: "No bootstrap payload found in D1" }, 404);
  }

  let payload;
  try {
    payload = JSON.parse(row.payload_json);
  } catch (e) {
    return json({ error: "Invalid payload_json in D1", detail: String(e) }, 500);
  }

  const out = {
    SD: Array.isArray(payload.SD) ? payload.SD : [],
    PR: payload.PR && typeof payload.PR === "object" ? payload.PR : {},
    TF: payload.TF && typeof payload.TF === "object" ? payload.TF : {},
    DN: payload.DN && typeof payload.DN === "object" ? payload.DN : {},
    updatedAt: row.updated_at || new Date().toISOString(),
  };
  return json(out, 200);
}
