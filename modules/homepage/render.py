"""Render a static portal with explicitly supplied HTTPS service URLs."""

import argparse
import html
import re
from pathlib import Path
from urllib.parse import urlsplit


def https_url(value):
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
            and parsed.path in ("", "/")
            and parsed.port != 0
            and not any(c.isspace() or ord(c) < 32 for c in value)
        )
    except ValueError:
        valid = False
    if not valid:
        raise argparse.ArgumentTypeError("Use an HTTPS root URL without credentials, query or fragment")
    return value.rstrip("/") + "/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nextcloud", required=True, type=https_url)
    parser.add_argument("--forgejo", type=https_url)
    parser.add_argument("--output", type=Path, default=Path("index.html"))
    args = parser.parse_args()
    page = Path(__file__).with_name("index.template.html").read_text(encoding="utf-8")
    page = page.replace("{{NEXTCLOUD_URL}}", html.escape(args.nextcloud, quote=True))
    if args.forgejo:
        page = page.replace("{{FORGEJO_URL}}", html.escape(args.forgejo, quote=True))
    else:
        page = re.sub(r'<a class="card" href="\{\{FORGEJO_URL\}\}".*?</a>', "", page, flags=re.S)
    with args.output.open("x", encoding="utf-8") as target:
        target.write(page)
    print(f"Created {args.output}")


if __name__ == "__main__":
    main()
