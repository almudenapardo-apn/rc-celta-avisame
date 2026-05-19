#!/usr/bin/env python3
"""Generates n8n-avisame-seat-alert.json (workflow B). Run once; safe to delete."""
import json
from pathlib import Path

MATCH_LEADS_JS = r"""
const VARS = $('Vars').first().json;
const avail = $('ONEBOX Availability').first().json;
const membersResp = $('Mailchimp members').first().json;
const members = (membersResp && membersResp.members) || [];

const eventId = String(VARS.watched_event_id);
const sessionId = String(VARS.watched_session_id);
const eventName = VARS.watched_event_name || '';
const purchaseUrl = String(VARS.purchase_url_template || '').replace('{sessionId}', sessionId);

const sectors = (avail && avail.sectors) || [];
const gradaAvail = {};
for (const sec of sectors) {
  let total = 0;
  for (const pt of (sec.price_types || [])) {
    const a = pt.availability || {};
    if (typeof a.available === 'number') total += a.available;
  }
  if (total > 0) gradaAvail[String(sec.id)] = { name: sec.name, available: total };
}

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

const out = [];
for (const m of members) {
  const tags = (m.tags || []).map(t => t.name);
  if (!tags.includes('event:' + eventId)) continue;
  for (const t of tags) {
    if (t.indexOf('grada:') !== 0) continue;
    const gid = t.slice(6);
    const g = gradaAvail[gid];
    if (!g) continue;
    const notifiedTag = 'notified:event-' + eventId + '-grada-' + gid;
    if (tags.includes(notifiedTag)) continue;
    const fname = (m.merge_fields || {}).FNAME || '';
    const evName = eventName || (m.merge_fields || {}).EVENT_NAME || 'tu partido';
    const subject = 'Hay entradas! ' + evName + ' - ' + g.name;
    const html =
      '<div style="font-family:Inter,system-ui,Arial,sans-serif;max-width:560px;margin:auto;color:#0A1A3F">' +
      '<div style="background:#7AB1D9;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0">' +
      '<div style="font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.9">RC Celta - Entradas</div>' +
      '<div style="font-size:24px;font-weight:800;margin-top:4px">Hay entradas!</div></div>' +
      '<div style="border:1px solid #E2E6EC;border-top:0;border-radius:0 0 8px 8px;padding:24px">' +
      '<p>Hola ' + esc(fname) + ', se acaban de liberar localidades para la grada que estas siguiendo. Corre que vuelan.</p>' +
      '<table style="width:100%;font-size:14px;border-collapse:collapse;margin:16px 0">' +
      '<tr><td style="color:#5A6478;padding:6px 0">Partido</td><td style="text-align:right;font-weight:600">' + esc(evName) + '</td></tr>' +
      '<tr><td style="color:#5A6478;padding:6px 0">Grada</td><td style="text-align:right;font-weight:600">' + esc(g.name) + '</td></tr>' +
      '<tr><td style="color:#5A6478;padding:6px 0">Disponibilidad</td><td style="text-align:right;font-weight:600">' + g.available + ' localidades</td></tr>' +
      '</table>' +
      '<p style="text-align:center;margin:24px 0"><a href="' + esc(purchaseUrl) + '" style="display:inline-block;background:#E4002B;color:#fff;padding:14px 28px;border-radius:4px;text-decoration:none;font-weight:700">Comprar entrada</a></p>' +
      '<p style="color:#5A6478;font-size:12px;margin-top:24px;border-top:1px solid #E2E6EC;padding-top:16px">Te registraste en el formulario Avisame del RC Celta. No garantiza reserva.<br>' +
      '<a href="mailto:avisame@student.ie.edu?subject=Baja%20avisos%20RC%20Celta&body=Solicito%20la%20baja%20de%20los%20avisos." style="color:#5A6478">Darme de baja</a> &middot; ' +
      '<a href="https://almudenapardo-apn.github.io/rc-celta-avisame/privacy.html" style="color:#5A6478">Politica de privacidad</a></p>' +
      '</div></div>';
    out.push({ json: {
      email: m.email_address,
      subscriber_hash: m.id,
      fname: fname,
      event_name: evName,
      grada_id: gid,
      grada_name: g.name,
      available: g.available,
      purchase_url: purchaseUrl,
      notified_tag: notifiedTag,
      subject: subject,
      html: html
    }});
  }
}
return out;
""".strip()

VARS_JS = r"""
return [{ json: {
  onebox_token_url: 'https://api.oneboxtds.net/oauth/token',
  onebox_base_url: 'https://api.oneboxtds.net',
  onebox_channel_id: '2287',
  onebox_client_id: 'seller-channel-client',
  onebox_client_secret: 'PASTE_ONEBOX_CLIENT_SECRET_FROM_ENV',
  watched_session_id: '240895',
  watched_event_id: '4587',
  watched_event_name: '* API NUMBERED EVENT',
  resend_api_key: 'PASTE_RESEND_API_KEY_FROM_ENV',
  email_from: 'onboarding@resend.dev',
  email_from_name: 'RC Celta - Avisame',
  purchase_url_template: 'https://tickets.oneboxtds.com/rccelta/select/{sessionId}'
}}];
""".strip()

wf = {
  "name": "Avisame - Seat alert",
  "nodes": [
    {"parameters": {}, "id": "n-trigger", "name": "Manual Trigger",
     "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [120, 300]},
    {"parameters": {"language": "javaScript", "jsCode": VARS_JS},
     "id": "n-vars", "name": "Vars", "type": "n8n-nodes-base.code",
     "typeVersion": 2, "position": [320, 300]},
    {"parameters": {
        "method": "POST",
        "url": "={{ $('Vars').item.json.onebox_token_url }}",
        "sendBody": True, "contentType": "form-urlencoded",
        "bodyParameters": {"parameters": [
            {"name": "grant_type", "value": "client_credentials"},
            {"name": "channel_id", "value": "={{ $('Vars').item.json.onebox_channel_id }}"},
            {"name": "client_id", "value": "={{ $('Vars').item.json.onebox_client_id }}"},
            {"name": "client_secret", "value": "={{ $('Vars').item.json.onebox_client_secret }}"}
        ]}, "options": {}},
     "id": "n-onebox-auth", "name": "ONEBOX Auth",
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [520, 300]},
    {"parameters": {
        "method": "GET",
        "url": "={{ $('Vars').item.json.onebox_base_url }}/catalog-api/v1/sessions/{{ $('Vars').item.json.watched_session_id }}/availability",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "Authorization", "value": "=Bearer {{ $('ONEBOX Auth').item.json.access_token }}"},
            {"name": "Accept", "value": "application/json"}
        ]}, "options": {}},
     "id": "n-onebox-avail", "name": "ONEBOX Availability",
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [720, 300]},
    {"parameters": {
        "method": "GET",
        "url": "=https://us15.api.mailchimp.com/3.0/lists/5afbdde6ab/members?count=1000&fields=members.id,members.email_address,members.merge_fields,members.tags",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "mailchimpApi",
        "options": {}},
     "id": "n-mc-members", "name": "Mailchimp members",
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [920, 300]},
    {"parameters": {"language": "javaScript", "jsCode": MATCH_LEADS_JS},
     "id": "n-match", "name": "Match leads", "type": "n8n-nodes-base.code",
     "typeVersion": 2, "position": [1120, 300]},
    {"parameters": {
        "method": "POST",
        "url": "https://api.resend.com/emails",
        "sendHeaders": True,
        "headerParameters": {"parameters": [
            {"name": "Authorization", "value": "=Bearer {{ $('Vars').first().json.resend_api_key }}"},
            {"name": "Content-Type", "value": "application/json"}
        ]},
        "sendBody": True, "contentType": "json", "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ from: $('Vars').first().json.email_from_name + ' <' + $('Vars').first().json.email_from + '>', to: [$json.email], subject: $json.subject, html: $json.html }) }}",
        "options": {}},
     "id": "n-resend", "name": "Resend Send",
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1320, 300]},
    {"parameters": {
        "method": "POST",
        "url": "=https://us15.api.mailchimp.com/3.0/lists/5afbdde6ab/members/{{ $json.subscriber_hash }}/tags",
        "authentication": "predefinedCredentialType",
        "nodeCredentialType": "mailchimpApi",
        "sendBody": True, "contentType": "json", "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ tags: [{ name: $json.notified_tag, status: 'active' }] }) }}",
        "options": {}},
     "id": "n-mc-notified", "name": "Mailchimp notified tag",
     "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1520, 300]}
  ],
  "connections": {
    "Manual Trigger": {"main": [[{"node": "Vars", "type": "main", "index": 0}]]},
    "Vars": {"main": [[{"node": "ONEBOX Auth", "type": "main", "index": 0}]]},
    "ONEBOX Auth": {"main": [[{"node": "ONEBOX Availability", "type": "main", "index": 0}]]},
    "ONEBOX Availability": {"main": [[{"node": "Mailchimp members", "type": "main", "index": 0}]]},
    "Mailchimp members": {"main": [[{"node": "Match leads", "type": "main", "index": 0}]]},
    "Match leads": {"main": [[{"node": "Resend Send", "type": "main", "index": 0}, {"node": "Mailchimp notified tag", "type": "main", "index": 0}]]}
  },
  "settings": {},
  "pinData": {}
}

out = Path(__file__).with_name("n8n-avisame-seat-alert.json")
out.write_text(json.dumps(wf, indent=2, ensure_ascii=False))
print(f"Wrote {out.name} ({out.stat().st_size} bytes, {len(wf['nodes'])} nodes)")
