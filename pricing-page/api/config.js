// Live pricing config for the Startup Talks page.
// GET  /api/config          → current config (public)
// POST /api/config          → save config (needs x-admin-password header)
// Storage: Upstash Redis (connect it from the Vercel project's Storage tab).

const crypto = require("crypto");

const KEY = "startuptalks:pricing:config";

const FIELDS = {
  offerLabel: "string",
  originalPrice: "number",
  offerPrice: "number",
  validTill: "string",
  advancePercent: "number",
  deliveryDays: "number",
  bonus1: "string",
  bonus2: "string",
  bonus2Note: "string",
  followers: "string",
  reach: "string",
  whatsapp: "string",
  whatsappMessage: "string",
};

function redis() {
  const url = process.env.KV_REST_API_URL || process.env.UPSTASH_REDIS_REST_URL;
  const token = process.env.KV_REST_API_TOKEN || process.env.UPSTASH_REDIS_REST_TOKEN;
  if (!url || !token) return null;
  return async (...cmd) => {
    const r = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(cmd),
    });
    const j = await r.json();
    if (j.error) throw new Error(j.error);
    return j.result;
  };
}

function passwordOk(given) {
  const want = process.env.ADMIN_PASSWORD;
  if (!want || typeof given !== "string") return false;
  const a = crypto.createHash("sha256").update(given).digest();
  const b = crypto.createHash("sha256").update(want).digest();
  return crypto.timingSafeEqual(a, b);
}

function clean(body) {
  const out = {};
  for (const [k, type] of Object.entries(FIELDS)) {
    if (!(k in body)) continue;
    let v = body[k];
    if (type === "number") {
      v = Number(v);
      if (!Number.isFinite(v) || v < 0 || v > 10_000_000) throw new Error(`${k} must be a valid number`);
    } else {
      v = String(v).trim().slice(0, 300);
    }
    out[k] = v;
  }
  if (out.advancePercent > 100) throw new Error("advancePercent must be 0–100");
  return out;
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  const db = redis();

  if (req.method === "GET") {
    if (!db) return res.status(200).json({});
    try {
      const raw = await db("GET", KEY);
      return res.status(200).json(raw ? JSON.parse(raw) : {});
    } catch {
      return res.status(200).json({});
    }
  }

  if (req.method === "POST") {
    if (!passwordOk(req.headers["x-admin-password"])) return res.status(401).json({ error: "Wrong password" });
    const body = req.body || {};
    if (body.verify) return res.status(200).json({ ok: true, storage: !!db });
    if (!db) return res.status(503).json({ error: "Storage not connected. Connect Upstash Redis in the Vercel project → Storage tab, then redeploy." });
    try {
      const cfg = clean(body);
      await db("SET", KEY, JSON.stringify(cfg));
      return res.status(200).json(cfg);
    } catch (e) {
      return res.status(400).json({ error: e.message });
    }
  }

  res.setHeader("Allow", "GET, POST");
  return res.status(405).json({ error: "Method not allowed" });
};
