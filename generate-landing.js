#!/usr/bin/env node
/**
 * generate-landing.js
 *
 * Reads ONEBOX credentials from .env, fetches the availability of one match,
 * and rewrites the <select id="grada"> in landing.html so its <option> list
 * reflects the real sectors (price_types) returned by the API.
 *
 * Usage:
 *   node generate-landing.js                 # uses session 240895
 *   node generate-landing.js 617439          # any other session id
 *   ONEBOX_SESSION_ID=617439 node generate-landing.js
 *
 * Requires Node 18+ (uses native fetch).
 */

const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const ENV_PATH = path.join(ROOT, ".env");
const LANDING_PATH = path.join(ROOT, "landing.html");
const DEFAULT_SESSION_ID = "240895";

function loadEnv(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const out = {};
  for (const raw of fs.readFileSync(filePath, "utf8").split("\n")) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const eq = line.indexOf("=");
    const key = line.slice(0, eq).trim();
    let val = line.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    out[key] = val;
  }
  return out;
}

const env = { ...loadEnv(ENV_PATH), ...process.env };
const required = [
  "ONEBOX_API_ENDPOINT",
  "ONEBOX_BASE_URL",
  "ONEBOX_CHANNEL_ID",
  "ONEBOX_CLIENT_ID",
  "ONEBOX_CLIENT_SECRET",
];
const missing = required.filter((k) => !env[k]);
if (missing.length) {
  console.error(`Missing env vars: ${missing.join(", ")}`);
  process.exit(1);
}

const sessionId =
  process.argv[2] || env.ONEBOX_SESSION_ID || DEFAULT_SESSION_ID;

async function getToken() {
  const body = new URLSearchParams({
    grant_type: "client_credentials",
    channel_id: env.ONEBOX_CHANNEL_ID,
    client_id: env.ONEBOX_CLIENT_ID,
    client_secret: env.ONEBOX_CLIENT_SECRET,
  });
  const res = await fetch(env.ONEBOX_API_ENDPOINT, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Accept: "application/json",
    },
    body,
  });
  if (!res.ok) throw new Error(`Auth failed: HTTP ${res.status}`);
  const json = await res.json();
  if (!json.access_token) throw new Error("No access_token in auth response");
  return json.access_token;
}

async function getAvailability(token, id) {
  const base = env.ONEBOX_BASE_URL.replace(/\/$/, "");
  const url = `${base}/catalog-api/v1/sessions/${encodeURIComponent(id)}/availability`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`Availability failed: HTTP ${res.status}`);
  return res.json();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

function rewriteSelect(html, sectors) {
  // Match the existing <select id="grada"...>...</select> and capture indent.
  const re =
    /([ \t]*)<select\s+id="grada"[^>]*>([\s\S]*?)<\/select>/i;
  const match = html.match(re);
  if (!match) {
    throw new Error('Could not find <select id="grada"> in landing.html');
  }
  const baseIndent = match[1] || "          ";
  const innerIndent = baseIndent + "  ";

  const placeholder = `${innerIndent}<option value="" disabled selected>Selecciona una grada</option>`;
  const options = sectors
    .map(
      (s) =>
        `${innerIndent}<option value="${escapeHtml(s.id)}">${escapeHtml(s.name)}</option>`
    )
    .join("\n");

  const replacement =
    `${baseIndent}<select id="grada" name="grada" required>\n` +
    `${placeholder}\n` +
    `${options}\n` +
    `${baseIndent}</select>`;

  return html.replace(re, replacement);
}

(async () => {
  console.log(`Authenticating with ONEBOX...`);
  const token = await getToken();

  console.log(`Fetching availability for session ${sessionId}...`);
  const avail = await getAvailability(token, sessionId);

  const rawSectors = Array.isArray(avail.sectors) ? avail.sectors : [];
  const sectors = rawSectors
    .filter((s) => s && s.id != null && s.name)
    .map((s) => ({ id: s.id, name: s.name }));

  if (!sectors.length) {
    throw new Error("No sectors found in availability response.");
  }

  const before = fs.readFileSync(LANDING_PATH, "utf8");
  const after = rewriteSelect(before, sectors);
  fs.writeFileSync(LANDING_PATH, after);

  console.log(`Baked ${sectors.length} sectors into landing.html.`);
})().catch((err) => {
  console.error(`Error: ${err.message}`);
  process.exit(1);
});
