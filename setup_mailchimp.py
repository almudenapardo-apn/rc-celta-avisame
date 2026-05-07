#!/usr/bin/env python3
"""
One-shot setup for the Mailchimp audience used by the «¡Avísame!» landing.

Reads .env, lists the merge fields currently configured in the audience, and
creates the ones that are missing. Idempotent — safe to re-run.

Required vars in .env:
  MAILCHIMP_API_KEY       (e.g. xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx-us15)
  MAILCHIMP_AUDIENCE_ID   (10-char hex like 5afbdde6ab)
  MAILCHIMP_DC            (datacenter prefix; auto-derived from the API key
                           suffix if not provided)
"""

import base64
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

SYSTEM_CA = "/etc/ssl/cert.pem"
TIMEOUT = 15

# FNAME and LNAME ship with every Mailchimp audience by default — only the
# four below need to be created.
REQUIRED_MERGE_FIELDS = [
    {"tag": "EVENT_ID", "name": "Event ID", "type": "text"},
    {"tag": "EVENT",    "name": "Event",    "type": "text"},
    {"tag": "GRADA_ID", "name": "Grada ID", "type": "text"},
    {"tag": "GRADA",    "name": "Grada",    "type": "text"},
]


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
    return (
        ssl.create_default_context(cafile=SYSTEM_CA)
        if Path(SYSTEM_CA).exists()
        else ssl.create_default_context()
    )


def auth_header(api_key: str) -> str:
    raw = f"anystring:{api_key}".encode("utf-8")
    return f"Basic {base64.b64encode(raw).decode('ascii')}"


def request(method: str, url: str, api_key: str, ctx: ssl.SSLContext, body=None):
    headers = {
        "Authorization": auth_header(api_key),
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except json.JSONDecodeError:
            return e.code, {}
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}")
        return 0, {}


def main() -> int:
    env = load_env(Path(__file__).with_name(".env"))
    key = env.get("MAILCHIMP_API_KEY")
    audience = env.get("MAILCHIMP_AUDIENCE_ID")
    dc = env.get("MAILCHIMP_DC")

    if not key:
        print("Missing MAILCHIMP_API_KEY in .env")
        return 1
    if not audience:
        print("Missing MAILCHIMP_AUDIENCE_ID in .env")
        return 1
    if not dc:
        if "-" in key:
            dc = key.rsplit("-", 1)[1]
            print(f"(MAILCHIMP_DC derived from API key suffix: {dc})")
        else:
            print("Missing MAILCHIMP_DC and unable to derive from key.")
            return 1

    base = f"https://{dc}.api.mailchimp.com/3.0"
    ctx = ssl_ctx()

    # Sanity check: ping
    print(f"Ping {base}/ping ...")
    status, body = request("GET", f"{base}/ping", key, ctx)
    if status != 200:
        print(f"Ping failed (HTTP {status}): {json.dumps(body, ensure_ascii=False)}")
        return 2
    print(f"  -> {body.get('health_status', 'OK')}")

    print(f"\nGET {base}/lists/{audience}/merge-fields")
    status, body = request(
        "GET", f"{base}/lists/{audience}/merge-fields?count=1000", key, ctx
    )
    if status != 200:
        print(f"Error reading merge fields (HTTP {status}):")
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return 3

    existing = {f["tag"]: f for f in body.get("merge_fields", [])}
    print(
        f"  Existing merge fields ({len(existing)}): "
        f"{', '.join(sorted(existing.keys())) or '(none)'}"
    )

    to_create = [f for f in REQUIRED_MERGE_FIELDS if f["tag"] not in existing]
    if not to_create:
        print("\nAll required merge fields already exist — nothing to do.")
        return 0

    print(f"\nCreating {len(to_create)} missing merge fields:")
    created = 0
    for f in to_create:
        label = f"{f['tag']} ({f['name']}, {f['type']})"
        print(f"  POST {label} ...", end=" ", flush=True)
        status, body = request(
            "POST",
            f"{base}/lists/{audience}/merge-fields",
            key,
            ctx,
            body={
                "tag": f["tag"],
                "name": f["name"],
                "type": f["type"],
                "required": False,
                "public": False,
            },
        )
        if status in (200, 201):
            print("OK")
            created += 1
        else:
            print(f"FAIL (HTTP {status})")
            print(f"     {json.dumps(body, ensure_ascii=False)}")

    print(f"\nDone — created {created}/{len(to_create)} merge fields.")
    return 0 if created == len(to_create) else 4


if __name__ == "__main__":
    sys.exit(main())
