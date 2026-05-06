#!/usr/bin/env python3
"""
End-to-end smoke test of the three ONEBOX endpoints we use:

  1. POST /oauth/token                                     -> access_token
  2. GET  /catalog-api/v1/sessions                         -> list of matches
  3. GET  /catalog-api/v1/sessions/{sessionId}/availability -> seat availability

Reads .env (same folder) for:
  ONEBOX_API_ENDPOINT   (token URL)
  ONEBOX_BASE_URL       (catalog API base)
  ONEBOX_CHANNEL_ID
  ONEBOX_CLIENT_ID
  ONEBOX_CLIENT_SECRET
"""

import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SYSTEM_CA = "/etc/ssl/cert.pem"  # macOS system CA bundle
TIMEOUT = 15


def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def ssl_context() -> ssl.SSLContext:
    if Path(SYSTEM_CA).exists():
        return ssl.create_default_context(cafile=SYSTEM_CA)
    return ssl.create_default_context()


def http_request(method: str, url: str, *, headers=None, body=None, ctx=None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def parse_json(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def pretty(value) -> str:
    if value is None:
        return ""
    return json.dumps(value, indent=2, ensure_ascii=False)


def step_header(n: int, title: str) -> None:
    print(f"\n{'=' * 60}\n[{n}] {title}\n{'=' * 60}")


def main() -> int:
    env = load_env(Path(__file__).with_name(".env"))
    token_url = env.get("ONEBOX_API_ENDPOINT")
    base_url = env.get("ONEBOX_BASE_URL")
    channel_id = env.get("ONEBOX_CHANNEL_ID")
    client_id = env.get("ONEBOX_CLIENT_ID")
    client_secret = env.get("ONEBOX_CLIENT_SECRET")

    required = {
        "ONEBOX_API_ENDPOINT": token_url,
        "ONEBOX_BASE_URL": base_url,
        "ONEBOX_CHANNEL_ID": channel_id,
        "ONEBOX_CLIENT_ID": client_id,
        "ONEBOX_CLIENT_SECRET": client_secret,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print(f"Faltan variables en .env: {', '.join(missing)}")
        return 1

    ctx = ssl_context()

    # ---------- 1. Authentication ----------
    step_header(1, "Authentication — POST /oauth/token")
    print(f"-> {token_url}")
    print(f"   grant_type=client_credentials  channel_id={channel_id}  client_id={client_id}  client_secret=***")

    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "channel_id": channel_id,
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    status, raw = http_request(
        "POST",
        token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        body=body,
        ctx=ctx,
    )
    parsed = parse_json(raw)
    print(f"\nHTTP {status}")
    print("Respuesta:")
    print(pretty(parsed) if parsed is not None else raw)

    access_token = parsed.get("access_token") if isinstance(parsed, dict) else None
    if status != 200 or not access_token:
        print("\nCredenciales invalidas o respuesta inesperada — no se pudo obtener access_token.")
        return 3
    print("\nCredenciales validas: access_token recibido.")

    auth_headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}

    # ---------- 2. Get sessions ----------
    step_header(2, "Sessions — GET /catalog-api/v1/sessions")
    sessions_url = f"{base_url.rstrip('/')}/catalog-api/v1/sessions"
    print(f"-> {sessions_url}")

    status, raw = http_request("GET", sessions_url, headers=auth_headers, ctx=ctx)
    parsed = parse_json(raw)
    print(f"\nHTTP {status}")
    if status != 200:
        print("Respuesta:")
        print(pretty(parsed) if parsed is not None else raw)
        return 4

    # The API may return either a bare list or an object wrapping a list — handle both.
    if isinstance(parsed, list):
        sessions = parsed
    elif isinstance(parsed, dict):
        sessions = parsed.get("sessions") or parsed.get("data") or parsed.get("items") or []
    else:
        sessions = []

    print(f"Total sesiones recibidas: {len(sessions)}")
    print("Primeras (hasta 3):")
    print(pretty(sessions[:3]))

    if not sessions:
        print("\nNo hay sesiones — no puedo probar el endpoint de disponibilidad.")
        return 0

    # ---------- 3. Get availability for the first session ----------
    first = sessions[0]
    session_id = first.get("id") or first.get("sessionId") or first.get("session_id")
    if not session_id:
        print("\nNo se ha podido extraer el id de la primera sesion. Estructura recibida:")
        print(pretty(first))
        return 0

    step_header(3, f"Availability — GET /catalog-api/v1/sessions/{session_id}/availability")
    avail_url = f"{base_url.rstrip('/')}/catalog-api/v1/sessions/{urllib.parse.quote(str(session_id))}/availability"
    print(f"-> {avail_url}")

    status, raw = http_request("GET", avail_url, headers=auth_headers, ctx=ctx)
    parsed = parse_json(raw)
    print(f"\nHTTP {status}")
    print("Respuesta:")
    print(pretty(parsed) if parsed is not None else raw)

    return 0 if status == 200 else 5


if __name__ == "__main__":
    sys.exit(main())
