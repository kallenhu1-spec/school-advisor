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
    return json({ ok: false, error: "D1 binding DB is missing" }, 500);
  }
  let row = null;
  try {
    row = await db.prepare("SELECT updated_at FROM bootstrap_payload WHERE id = 1").first();
  } catch (e) {
    return json(
      {
        ok: false,
        error: "D1 query failed",
        detail: String(e),
        hint: "请先在 D1 执行建表 SQL（bootstrap_payload）",
      },
      500,
    );
  }
  return json(
    {
      ok: true,
      hasPayload: Boolean(row),
      updatedAt: row ? row.updated_at : null,
      runtime: "cloudflare-pages-functions",
    },
    200,
  );
}
