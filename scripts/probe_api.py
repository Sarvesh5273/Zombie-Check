"""Read-only access check. No API keys or personal dataset data are printed."""
import json
import os
import urllib.error
import urllib.request

key = os.environ.get("TINYFISH_API_KEY")
if not key:
    raise SystemExit("TINYFISH_API_KEY is not configured")
req = urllib.request.Request(
    "https://agent.tinyfish.ai/v1/datasets?limit=1",
    headers={"X-API-Key": key, "Accept": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=30) as response:
        body = json.load(response)
        print(json.dumps({"http_status": response.status, "response_keys": list(body), "tinyset_access": True}))
except urllib.error.HTTPError as error:
    body = json.loads(error.read().decode())
    print(json.dumps({"http_status": error.code, "error": body.get("error", {})}))
    raise SystemExit(1)

