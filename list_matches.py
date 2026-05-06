#!/usr/bin/env python3
"""
Authenticate with ONEBOX and list all matches (sessions) on our channel.
Prints the total count and the name of the first match.

Reads .env in the same folder.
"""

import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SYSTEM_CA = "/etc/ssl/cert.pem"


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
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read())["access_token"]


def get_sessions(env: dict, token: str, ctx: ssl.SSLContext):
    url = f"{env['ONEBOX_BASE_URL'].rstrip('/')}/catalog-api/v1/sessions"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        data = json.loads(resp.read())
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("sessions") or data.get("data") or data.get("items") or []
    return []


def match_name(session: dict) -> str:
    """Pick the most human-readable name for a match."""
    event = session.get("event") or {}
    texts = event.get("texts") or {}
    title = texts.get("title") or {}
    return (
        title.get("es-ES")
        or title.get("en-US")
        or event.get("name")
        or session.get("name")
        or "(sin nombre)"
    )


def main() -> int:
    env = load_env(Path(__file__).with_name(".env"))
    ctx = ssl.create_default_context(cafile=SYSTEM_CA) if Path(SYSTEM_CA).exists() else ssl.create_default_context()

    try:
        token = get_token(env, ctx)
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError) as e:
        print(f"Auth fallida: {e}")
        return 1

    try:
        sessions = get_sessions(env, token, ctx)
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        print(f"No se pudieron obtener las sesiones: {e}")
        return 2

    print(f"Partidos disponibles en el canal: {len(sessions)}")
    if sessions:
        print(f"Primer partido: {match_name(sessions[0])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
