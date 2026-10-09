"""Outbound-only Healthchecks pings with an explicit, bounded status schema."""

import json
import math
from pathlib import Path
import re
import urllib.parse
import urllib.request

PHASES = {"Starting", "Preflight", "AIO backup", "Export", "Restart", "External copy", "Retention", "Idle", "Recovery required"}
HEALTH = {"healthy", "unhealthy", "starting", "stopped", "unknown"}
ERRORS = {"NONE", "WORKFLOW_FAILED", "RECOVERY_REQUIRED", "WORKFLOW_TIMEOUT", "LOW_SPACE", "STORAGE_UNAVAILABLE", "SERVICE_UNHEALTHY", "SCHEDULER_STALLED", "STATUS_UNAVAILABLE"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Redirects are disabled")


def http_client():
    # Do not inherit ambient proxy settings or forward secret URLs to a redirect.
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def safe_payload(raw):
    """Never serialize raw state, logs, exceptions, hostnames or arbitrary strings."""
    result = {"schema": 1}
    for key in ("nextcloud", "apache"):
        value = raw.get(key)
        result[key] = value if value in HEALTH else "unknown"
    phase = raw.get("phase")
    result["phase"] = phase if phase in PHASES else "unknown"
    code = raw.get("error_code")
    result["error_code"] = code if code in ERRORS else "STATUS_UNAVAILABLE"
    for key in ("maintenance", "scheduler_alive", "workflow_active"):
        result[key] = raw.get(key) is True
    for key in ("observed_at", "last_backup", "last_copy", "export_free_gib"):
        value = raw.get(key)
        result[key] = round(value, 2) if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 10**12 else None
    return result


class Monitor:
    def __init__(self, cfg, urls=None):
        self.cfg, self.urls = cfg, urls or {}

    @classmethod
    def load(cls, root):
        path = root / "config/healthchecks.json"
        cfg = json.loads((root / "config/healthchecks.example.json").read_text())
        if path.exists():
            supplied = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(supplied, dict) or set(supplied) - set(cfg):
                raise ValueError("Invalid Healthchecks configuration fields")
            cfg.update(supplied)
        if type(cfg["enabled"]) is not bool:
            raise ValueError("Healthchecks enabled must be boolean")
        for key, low, high in (("interval_seconds", 60, 3600), ("timeout_seconds", 1, 10), ("maximum_workflow_seconds", 60, 604800)):
            if type(cfg[key]) is not int or not low <= cfg[key] <= high:
                raise ValueError("Invalid Healthchecks " + key)
        hosts = cfg["allowed_hosts"]
        if not isinstance(hosts, list) or not hosts or any(not isinstance(h, str) or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", h) for h in hosts):
            raise ValueError("Healthchecks allowed_hosts must list exact lowercase hostnames")
        if not isinstance(cfg["urls_file"], str) or not cfg["urls_file"]:
            raise ValueError("Healthchecks urls_file must be a path")
        if not cfg["enabled"]:
            return cls(cfg)
        path = Path(cfg["urls_file"])
        if not path.is_absolute():
            path = root / path
        try:
            urls = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(urls, dict) or set(urls) != {"backup", "service"}:
                raise ValueError()
            for value in urls.values():
                if not isinstance(value, str):
                    raise ValueError()
                parsed = urllib.parse.urlsplit(value)
                if (parsed.scheme != "https" or parsed.hostname not in hosts or parsed.port not in (None, 443)
                        or parsed.username or parsed.password or parsed.query or parsed.fragment
                        or not re.fullmatch(r"/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", parsed.path)
                        or any(c.isspace() for c in value)):
                    raise ValueError()
            if urls["backup"] == urls["service"]:
                raise ValueError()
        except Exception:
            raise ValueError("Invalid Healthchecks secret file; use two distinct HTTPS UUID ping URLs on allowed hosts") from None
        return cls(cfg, urls)

    def ping(self, check, event, status):
        if not self.cfg["enabled"]:
            return True
        try:
            suffix = {"success": "", "start": "/start", "fail": "/fail"}[event]
            body = json.dumps(safe_payload(status), allow_nan=False).encode("utf-8")
            request = urllib.request.Request(self.urls[check] + suffix, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with http_client().open(request, timeout=self.cfg["timeout_seconds"]) as response:
                # A 200 response can still say 'OK (not found)' or 'OK (rate limited)'.
                if response.status != 200 or response.read(64).strip() != b"OK":
                    raise ValueError()
            return True
        except Exception:
            print("Healthchecks delivery failed; no URL or response logged", flush=True)
            return False
