// Pricing offers for the Startup Talks page, one per client code.
// GET  /api/config?code=ABC → that client's offer (public)
// GET  /api/config          → public offer, or { locked: true } when codes are required
// POST /api/config          → admin actions (needs x-admin-password header)
// Storage: Turso (connect it from the Vercel project's Storage tab).

const crypto = require("crypto");

const DEFAULT_ROW = "_default"; // template offer + public offer
const SETTINGS_ROW = "_settings"; // page-wide settings

const OFFER_FIELDS = {
  clientName: "string",
  offerLabel: "string",
  originalPrice: "number",
  offerPrice: "number",
  validTill: "string",
  advancePercent: "number",
  deliveryDays: "number",
  bonus1: "string",
  bonus2: "string",
  bonus2Note: "string",
};

const SETTINGS_FIELDS = {
  requireCode: "boolean",
  followers: "string",
  reach: "string",
  whatsapp: "string",
  whatsappMessage: "string",
};

const CODE_RE = /^[A-Z0-9-]{3,32}$/;

function env(suffix) {
  if (process.env[`TURSO_${suffix}`]) return process.env[`TURSO_${suffix}`];
  const k = Object.keys(process.env).find(k => k.endsWith(`TURSO_${suffix}`));
  return k && process.env[k];
}

function turso() {
  const url = env("DATABASE_URL");
  const token = env("AUTH_TOKEN");
  if (!url || !token) return null;
  const base = url.replace(/^libsql:\/\//, "https://");
  return async (...stmts) => {
    const r = await fetch(`${base}/v2/pipeline`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        requests: [
          ...stmts.map(([sql, args = []]) => ({
            type: "execute",
            stmt: { sql, args: args.map(v => ({ type: "text", value: String(v) })) },
          })),
          { type: "close" },
        ],
      }),
    });
    if (!r.ok) throw new Error(`Turso ${r.status}`);
    const j = await r.json();
    return j.results.slice(0, stmts.length).map(x => {
      if (x.type === "error") throw new Error(x.error.message);
      const res = x.response.result;
      const cols = res.cols.map(c => c.name);
      return res.rows.map(row => Object.fromEntries(row.map((c, i) => [cols[i], c.value])));
    });
  };
}

let ready = null;
function schema(db) {
  ready ||= db([
    "CREATE TABLE IF NOT EXISTS pricing_offers (code TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at INTEGER NOT NULL)",
  ]).catch(e => { ready = null; throw e; });
  return ready;
}

async function getRows(db, codes) {
  const [rows] = await db([`SELECT code, data FROM pricing_offers WHERE code IN (${codes.map(() => "?").join(",")})`, codes]);
  return Object.fromEntries(rows.map(r => [r.code, JSON.parse(r.data)]));
}

function passwordOk(given) {
  const want = process.env.ADMIN_PASSWORD;
  if (!want || typeof given !== "string") return false;
  const a = crypto.createHash("sha256").update(given).digest();
  const b = crypto.createHash("sha256").update(want).digest();
  return crypto.timingSafeEqual(a, b);
}

function clean(body, fields) {
  const out = {};
  for (const [k, type] of Object.entries(fields)) {
    if (!(k in body)) continue;
    let v = body[k];
    if (type === "number") {
      v = Number(v);
      if (!Number.isFinite(v) || v < 0 || v > 10_000_000) throw new Error(`${k} must be a valid number`);
    } else if (type === "boolean") {
      v = !!v;
    } else {
      v = String(v).trim().slice(0, 300);
    }
    out[k] = v;
  }
  if (out.advancePercent > 100) throw new Error("Advance % must be 0–100");
  return out;
}

const normCode = c => String(c || "").trim().toUpperCase();

async function publicGet(req, res, db) {
  const code = normCode(req.query.code);
  if (!db) return res.status(200).json(code ? { error: "not_found" } : {});
  await schema(db);
  const rows = await getRows(db, [DEFAULT_ROW, SETTINGS_ROW, ...(code ? [code] : [])]);
  const settings = rows[SETTINGS_ROW] || {};
  const base = rows[DEFAULT_ROW] || {};
  delete base.clientName;
  if (code) {
    if (!rows[code]) return res.status(404).json({ error: "not_found" });
    return res.status(200).json({ ...settings, ...base, ...rows[code], code });
  }
  if (settings.requireCode ?? true) return res.status(200).json({ ...settings, locked: true });
  return res.status(200).json({ ...settings, ...base });
}

async function admin(req, res, db) {
  const body = req.body || {};
  if (body.action === "verify") return res.status(200).json({ ok: true, storage: !!db });
  if (!db) return res.status(503).json({ error: "Storage not connected. Connect Turso to this Vercel project (Storage tab), then redeploy." });
  await schema(db);

  if (body.action === "list") {
    const [rows] = await db(["SELECT code, data, updated_at FROM pricing_offers ORDER BY updated_at DESC"]);
    const all = Object.fromEntries(rows.map(r => [r.code, JSON.parse(r.data)]));
    const offers = rows
      .filter(r => r.code !== DEFAULT_ROW && r.code !== SETTINGS_ROW)
      .map(r => ({ code: r.code, updatedAt: Number(r.updated_at), ...all[r.code] }));
    return res.status(200).json({ defaults: all[DEFAULT_ROW] || {}, settings: all[SETTINGS_ROW] || {}, offers });
  }

  if (body.action === "save") {
    const isDefault = body.code === DEFAULT_ROW, isSettings = body.code === SETTINGS_ROW;
    const code = isDefault || isSettings ? body.code : normCode(body.code);
    if (!isDefault && !isSettings && !CODE_RE.test(code))
      return res.status(400).json({ error: "Code must be 3–32 letters, numbers or dashes" });
    const data = clean(body.data || {}, isSettings ? SETTINGS_FIELDS : OFFER_FIELDS);
    if (body.create) {
      const existing = await getRows(db, [code]);
      if (existing[code]) return res.status(409).json({ error: `Code ${code} already exists` });
    }
    await db(["INSERT INTO pricing_offers (code, data, updated_at) VALUES (?, ?, ?) ON CONFLICT(code) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
      [code, JSON.stringify(data), Date.now()]]);
    return res.status(200).json({ code, ...data });
  }

  if (body.action === "delete") {
    const code = normCode(body.code);
    await db(["DELETE FROM pricing_offers WHERE code = ?", [code]]);
    return res.status(200).json({ ok: true });
  }

  return res.status(400).json({ error: "Unknown action" });
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const db = turso();
  try {
    if (req.method === "GET") return await publicGet(req, res, db);
    if (req.method === "POST") {
      if (!passwordOk(req.headers["x-admin-password"])) return res.status(401).json({ error: "Wrong password" });
      return await admin(req, res, db);
    }
    res.setHeader("Allow", "GET, POST");
    return res.status(405).json({ error: "Method not allowed" });
  } catch (e) {
    return res.status(500).json({ error: e.message || "Server error" });
  }
};
