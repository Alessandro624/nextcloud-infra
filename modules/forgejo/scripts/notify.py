import json, re, sys, urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Redirect disabled")


try:
    check, event = sys.argv[1:]
    if check not in ("backup", "service") or event not in ("start", "success", "fail"):
        raise ValueError("Invalid event")
    urls = json.loads(Path("/etc/forgejo-backup/healthchecks.secret").read_text())
    if set(urls) != {"backup", "service"} or urls["backup"] == urls["service"]:
        raise ValueError("Distinct check URLs required")
    for url in urls.values():
        if not re.fullmatch(r"https://hc-ping\.com/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", url):
            raise ValueError("Invalid check URL")
    suffix = {"start": "/start", "success": "", "fail": "/fail"}[event]
    body = json.dumps({"component": "forgejo", "check": check, "event": event}).encode()
    req = urllib.request.Request(urls[check] + suffix, data=body, headers={"Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(req, timeout=5) as response:
        if response.status != 200 or response.read(64).strip() != b"OK":
            raise ValueError("Ping rejected")
except Exception:
    print("Monitoring delivery failed; details suppressed", file=sys.stderr)
    sys.exit(1)
