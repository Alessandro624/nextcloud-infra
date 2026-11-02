# Private homepage

Follow [setup](../../docs/homepage-setup.md). Render into ignored `backup/` or another private output directory; publish only the resulting HTML file through Tailscale Serve.

The template uses local inline icons/styles, no analytics or remote assets. URLs are HTTPS roots supplied explicitly. The renderer rejects credentials/query strings and escapes HTML. Edit the template for branding; do not add secrets. Application links do not grant authorization.

The Forgejo card is optional: omit `--forgejo` for a Nextcloud-only portal.
