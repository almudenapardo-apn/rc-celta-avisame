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

async function getSessions(token) {
  const base = env.ONEBOX_BASE_URL.replace(/\/$/, "");
  const url = `${base}/catalog-api/v1/sessions`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`Sessions failed: HTTP ${res.status}`);
  const data = await res.json();
  if (Array.isArray(data)) return data;
  return data.sessions || data.data || data.items || [];
}

function pickEventName(session, fallback) {
  if (!session) return fallback;
  const event = session.event || {};
  const t = event.texts && event.texts.title;
  // event.name is the canonical event title (e.g. "RC Celta - Real Madrid").
  // Fall back to localized texts.title and finally session.name.
  return (
    event.name ||
    (t && (t["es-ES"] || t["en-US"])) ||
    session.name ||
    fallback
  );
}

function pickEventSubtitle(session) {
  if (!session) return "";
  const t = session.event && session.event.texts && session.event.texts.subtitle;
  return (t && (t["es-ES"] || t["en-US"])) || "";
}

const ES_MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

function fmtDateES(iso) {
  if (!iso) return "";
  // Parse the wall-clock components from the ISO string so we display the
  // venue's local time regardless of the machine's timezone.
  const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return iso;
  const [, y, mo, d, h, mi] = m;
  const day = parseInt(d, 10);
  const month = ES_MONTHS[parseInt(mo, 10) - 1] || mo;
  return `${day} ${month} ${y}, ${h}:${mi}`;
}

function fmtPriceRange(min, max) {
  const f = (v) => `${Number.isInteger(v) ? v : (Math.round(v * 100) / 100)} €`;
  if (min == null && max == null) return "";
  if (max == null || min === max) return f(min);
  if (min == null) return f(max);
  return `${f(min)} – ${f(max)}`;
}

function fmtIntES(n) {
  if (n == null) return "—";
  // Use thin-thousand grouping for Spanish style: "14.372"
  return Number(n).toLocaleString("es-ES");
}

function pickStatus(available) {
  return available > 0
    ? { cls: "status--on-sale", label: "On sale" }
    : { cls: "status--sold-out", label: "Agotado" };
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

function rewriteFormDataset(html, eventId, eventName) {
  const re = /<form\s+id="avisame-form"[^>]*>/i;
  if (!re.test(html)) {
    throw new Error('Could not find <form id="avisame-form"> in landing.html');
  }
  const tag =
    `<form id="avisame-form" class="card"` +
    ` data-event-id="${escapeHtml(eventId)}"` +
    ` data-event-name="${escapeHtml(eventName)}"` +
    ` novalidate>`;
  return html.replace(re, tag);
}

const ICON_CALENDAR = `<svg class="match-info__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>`;
const ICON_PIN = `<svg class="match-info__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>`;
const ICON_PRICE = `<svg class="match-info__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>`;

function rewriteMatchInfo(html, info) {
  const re = /([ \t]*)<section\s+id="match-info"[^>]*>[\s\S]*?<\/section>/i;
  if (!re.test(html)) {
    throw new Error('Could not find <section id="match-info"> in landing.html');
  }
  const baseIndent = (html.match(re) || ["", "      "])[1];
  const i1 = baseIndent + "  ";
  const i2 = baseIndent + "    ";
  const i3 = baseIndent + "      ";

  const venueLine = [info.venueName, info.venueCity].filter(Boolean).join(", ");
  const dateLine = fmtDateES(info.dateStart);
  const priceLine = fmtPriceRange(info.priceMin, info.priceMax);
  const statusInfo = pickStatus(info.available);

  let rows = "";
  if (dateLine) {
    rows += `${i2}<li class="match-info__row">\n${i3}${ICON_CALENDAR}\n${i3}<span>${escapeHtml(dateLine)}</span>\n${i2}</li>\n`;
  }
  if (venueLine) {
    rows += `${i2}<li class="match-info__row">\n${i3}${ICON_PIN}\n${i3}<span>${escapeHtml(venueLine)}</span>\n${i2}</li>\n`;
  }
  if (priceLine) {
    rows += `${i2}<li class="match-info__row">\n${i3}${ICON_PRICE}\n${i3}<span>${escapeHtml(priceLine)}</span>\n${i2}</li>\n`;
  }

  const total = info.total || 0;
  const available = info.available || 0;
  const pct = total > 0 ? Math.round((available / total) * 100) : 0;
  const availLabel = total > 0
    ? `${fmtIntES(available)} / ${fmtIntES(total)} (${pct}%)`
    : "Sin datos de aforo";

  const subtitleHtml = info.subtitle
    ? `${i2}<p class="match-info__subtitle">${escapeHtml(info.subtitle)}</p>\n`
    : "";

  const block =
    `${baseIndent}<section id="match-info" class="card match-info">\n` +
    `${i1}<header class="match-info__head">\n` +
    `${i2}<div>\n` +
    subtitleHtml +
    `${i2}  <h2 class="match-info__title">${escapeHtml(info.title)}</h2>\n` +
    `${i2}</div>\n` +
    `${i2}<span class="match-info__status ${statusInfo.cls}">${escapeHtml(statusInfo.label)}</span>\n` +
    `${i1}</header>\n` +
    `${i1}<ul class="match-info__rows">\n` +
    rows +
    `${i1}</ul>\n` +
    `${i1}<div class="match-info__avail">\n` +
    `${i2}<div class="match-info__avail-head">\n` +
    `${i2}  <span>Disponibilidad</span>\n` +
    `${i2}  <strong>${escapeHtml(availLabel)}</strong>\n` +
    `${i2}</div>\n` +
    `${i2}<div class="match-info__avail-bar"><span style="width:${pct}%"></span></div>\n` +
    `${i1}</div>\n` +
    `${baseIndent}</section>`;

  return html.replace(re, block);
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

  console.log(`Fetching /sessions to look up event metadata...`);
  const allSessions = await getSessions(token);
  const watched = allSessions.find((s) => String(s.id) === String(sessionId));
  const eventName = pickEventName(watched, avail.name || "Partido");
  console.log(`Event: id=${sessionId}, name="${eventName}"`);

  const venue = (watched && watched.venue) || {};
  const venueLocation = venue.location || {};
  const date = (watched && watched.date) || {};
  const price = (watched && watched.price) || {};
  const availability = avail.availability || {};

  const matchInfo = {
    title: eventName,
    subtitle: pickEventSubtitle(watched),
    dateStart: date.start,
    venueName: venue.name || "",
    venueCity: venueLocation.city || "",
    priceMin: (price.min || {}).value,
    priceMax: (price.max || {}).value,
    total: availability.total,
    available: availability.available,
  };

  let html = fs.readFileSync(LANDING_PATH, "utf8");
  html = rewriteSelect(html, sectors);
  html = rewriteFormDataset(html, sessionId, eventName);
  html = rewriteMatchInfo(html, matchInfo);
  fs.writeFileSync(LANDING_PATH, html);

  console.log(
    `Baked ${sectors.length} sectors + match info` +
    ` (${matchInfo.venueName}${matchInfo.venueCity ? ", " + matchInfo.venueCity : ""},` +
    ` ${fmtDateES(matchInfo.dateStart)},` +
    ` ${matchInfo.available}/${matchInfo.total} libres) into landing.html.`
  );
})().catch((err) => {
  console.error(`Error: ${err.message}`);
  process.exit(1);
});
