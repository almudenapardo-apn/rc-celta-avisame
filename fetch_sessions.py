#!/usr/bin/env python3
"""
Fetch all sessions on the configured ONEBOX channel, enrich each with its
availability snapshot, and write a slim sessions.json used by
onebox-sessions-cards.html.

Re-run any time you want fresh data:
    python3 fetch_sessions.py
"""

import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SYSTEM_CA = "/etc/ssl/cert.pem"
TIMEOUT = 15


def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def ssl_ctx() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=SYSTEM_CA) if Path(SYSTEM_CA).exists() else ssl.create_default_context()


def get_token(env: dict, ctx: ssl.SSLContext) -> str:
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "channel_id": env["ONEBOX_CHANNEL_ID"],
        "client_id": env["ONEBOX_CLIENT_ID"],
        "client_secret": env["ONEBOX_CLIENT_SECRET"],
    }).encode("utf-8")
    req = urllib.request.Request(
        env["ONEBOX_API_ENDPOINT"],
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        return json.loads(r.read())["access_token"]


def get_json(url: str, token: str, ctx: ssl.SSLContext):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
        return json.loads(r.read())


def pick_image(images) -> str | None:
    """Best-effort pick of an event image URL across the messy multilingual structure."""
    if not isinstance(images, dict):
        return None
    main = images.get("main")
    if isinstance(main, dict):
        for key in ("es-ES", "en-US", "ca-ES"):
            if main.get(key):
                return main[key]
        for v in main.values():
            if v:
                return v
    landscape = images.get("landscape")
    if isinstance(landscape, list):
        for item in landscape:
            if isinstance(item, dict):
                for key in ("es-ES", "en-US", "ca-ES"):
                    if item.get(key):
                        return item[key]
                for v in item.values():
                    if v:
                        return v
    return None


def slim(session: dict, avail: dict) -> dict:
    event = session.get("event") or {}
    texts = event.get("texts") or {}
    title = (texts.get("title") or {})
    subtitle = (texts.get("subtitle") or {})
    venue = session.get("venue") or {}
    location = venue.get("location") or {}
    date = session.get("date") or {}
    price = session.get("price") or {}
    pmin = (price.get("min") or {}).get("value")
    pmax = (price.get("max") or {}).get("value")
    a = avail.get("availability") or {}
    return {
        "id": session.get("id"),
        "title": title.get("es-ES") or title.get("en-US") or event.get("name") or session.get("name") or "(sin titulo)",
        "subtitle": subtitle.get("es-ES") or subtitle.get("en-US") or "",
        "image": pick_image(event.get("images")),
        "date_start": date.get("start"),
        "date_end": date.get("end"),
        "venue_name": venue.get("name") or "",
        "venue_city": location.get("city") or "",
        "price_min": pmin,
        "price_max": pmax,
        "currency": "EUR",
        "total_seats": a.get("total"),
        "available_seats": a.get("available"),
        "session_type": session.get("name"),
    }


def main() -> int:
    env = load_env(Path(__file__).with_name(".env"))
    required = ["ONEBOX_API_ENDPOINT", "ONEBOX_BASE_URL", "ONEBOX_CHANNEL_ID", "ONEBOX_CLIENT_ID", "ONEBOX_CLIENT_SECRET"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        print(f"Missing env vars: {', '.join(missing)}")
        return 1

    ctx = ssl_ctx()
    print("Authenticating...")
    token = get_token(env, ctx)

    base = env["ONEBOX_BASE_URL"].rstrip("/")
    print("Fetching /sessions...")
    raw = get_json(f"{base}/catalog-api/v1/sessions", token, ctx)
    sessions = raw if isinstance(raw, list) else (raw.get("sessions") or raw.get("data") or raw.get("items") or [])

    out = []
    for i, s in enumerate(sessions, 1):
        sid = s.get("id")
        try:
            avail = get_json(f"{base}/catalog-api/v1/sessions/{sid}/availability", token, ctx)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print(f"  [{i}/{len(sessions)}] availability for {sid}: {e}")
            avail = {}
        out.append(slim(s, avail))
        print(f"  [{i}/{len(sessions)}] {sid}  {out[-1]['title'][:40]:40}  total={out[-1]['total_seats']} avail={out[-1]['available_seats']}")

    target = Path(__file__).with_name("sessions.json")
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\nWrote {target.name} with {len(out)} matches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
