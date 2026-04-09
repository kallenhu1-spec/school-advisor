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

const RAW_BASE = "https://raw.githubusercontent.com/kallenhu1-spec/school-advisor/main/data";
const SUPPLEMENTAL_SEED_V2_FILES = ["seed_v2_baoshan.json", "seed_v2_songjiang.json", "seed_v2_fengxian.json"];

function normalizeSchoolName(name) {
  return String(name || "")
    .replace(/\s+/g, "")
    .replace(/[（(]\s*小学部\s*[）)]/g, "小学部");
}

function schoolToSdRow(school) {
  const s = school && typeof school === "object" ? school : {};
  const admission = s.admission && typeof s.admission === "object" ? s.admission : {};
  const admitted = Number.isFinite(Number(admission.admitted)) ? Number(admission.admitted) : null;
  const maxLottery = Number.isFinite(Number(admission.maxLottery)) ? Number(admission.maxLottery) : null;
  const tier = String(s.tier || "T3").trim().toUpperCase() || "T3";
  const recommend = tier === "T1" ? 5 : tier === "T2" ? 4 : 3;
  return [
    normalizeSchoolName(s.name || s.officialName || ""),
    String(s.district || "").trim(),
    String(s.type || "").trim(),
    null,
    null,
    recommend,
    String(s.desc || "").trim(),
    s.lat ?? null,
    s.lng ?? null,
    admitted !== null && maxLottery !== null ? "hot" : "normal",
    tier,
    admitted,
    maxLottery,
    admission.admissionUrl ? String(admission.admissionUrl).trim() : null,
  ];
}

async function fetchJson(url) {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function mergeSupplementalPayload(base, supplemental) {
  const out = {
    SD: Array.isArray(base?.SD) ? [...base.SD] : [],
    PR: base?.PR && typeof base.PR === "object" && !Array.isArray(base.PR) ? { ...base.PR } : {},
    TF: base?.TF && typeof base.TF === "object" && !Array.isArray(base.TF) ? { ...base.TF } : {},
    DN: base?.DN && typeof base.DN === "object" && !Array.isArray(base.DN) ? { ...base.DN } : {},
    updatedAt: base?.updatedAt || null,
  };
  const seen = new Set(out.SD.filter((r) => Array.isArray(r) && r.length).map((r) => normalizeSchoolName(r[0])));
  for (const school of Array.isArray(supplemental?.schools) ? supplemental.schools : []) {
    const row = schoolToSdRow(school);
    const key = normalizeSchoolName(row[0]);
    if (!key || seen.has(key)) continue;
    out.SD.push(row);
    seen.add(key);
    if (school?.profile && typeof school.profile === "object") {
      out.PR[key] = school.profile;
    }
    if (school?.links && typeof school.links === "object" && school.links.xhs && !out.PR[key]?.xhs) {
      out.PR[key] = { ...(out.PR[key] || {}), xhs: school.links.xhs };
    }
  }
  return out;
}

async function loadBootstrapPayload(context) {
  const db = context.env.DB;
  let base = null;
  if (db) {
    try {
      const row = await db.prepare("SELECT payload_json, updated_at FROM bootstrap_payload WHERE id = 1").first();
      if (row && row.payload_json) {
        const payload = JSON.parse(row.payload_json);
        base = {
          SD: Array.isArray(payload.SD) ? payload.SD : [],
          PR: payload.PR && typeof payload.PR === "object" && !Array.isArray(payload.PR) ? payload.PR : {},
          TF: payload.TF && typeof payload.TF === "object" && !Array.isArray(payload.TF) ? payload.TF : {},
          DN: payload.DN && typeof payload.DN === "object" && !Array.isArray(payload.DN) ? payload.DN : {},
          updatedAt: row.updated_at || new Date().toISOString(),
        };
      }
    } catch (e) {
      base = { error: "D1 query failed", detail: String(e) };
    }
  }

  const supplemental = await fetchJson(`${RAW_BASE}/seed_v2_city_shanghai.json`);
  const supplementalDistricts = [];
  for (const file of SUPPLEMENTAL_SEED_V2_FILES) {
    const payload = await fetchJson(`${RAW_BASE}/${file}`);
    if (payload) supplementalDistricts.push(payload);
  }

  let out = base && !base.error ? base : null;
  if (!out || !Array.isArray(out.SD) || out.SD.length === 0) {
    if (supplemental) {
      out = {
        SD: Array.isArray(supplemental.SD) ? supplemental.SD : [],
        PR: supplemental.PR && typeof supplemental.PR === "object" && !Array.isArray(supplemental.PR) ? supplemental.PR : {},
        TF: supplemental.TF && typeof supplemental.TF === "object" && !Array.isArray(supplemental.TF) ? supplemental.TF : {},
        DN: supplemental.DN && typeof supplemental.DN === "object" && !Array.isArray(supplemental.DN) ? supplemental.DN : {},
        updatedAt: supplemental.updatedAt || new Date().toISOString(),
      };
    } else {
      out = { SD: [], PR: {}, TF: {}, DN: {}, updatedAt: new Date().toISOString() };
    }
  }

  for (const districtPayload of supplementalDistricts) {
    out = mergeSupplementalPayload(out, districtPayload);
  }

  return out;
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: withCors() });
}

export async function onRequestGet(context) {
  const payload = await loadBootstrapPayload(context);
  return json(payload, 200);
}
