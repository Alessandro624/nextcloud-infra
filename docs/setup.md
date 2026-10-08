# Setup

## Requirements

- Windows: Docker Desktop with Linux containers and Python 3 available as `python`. Linux: Docker Engine, Compose and Python 3.
- Tailscale installed directly on the Docker host and each client, signed in with access to the host.
- Tailscale MagicDNS and HTTPS enabled; Serve provides an enablement link if needed.
- Available ports and enough disk/RAM for your workload. Keep the host awake during testing.

Use [Docker's installation guide](https://docs.docker.com/engine/install/) on Linux. Run Docker commands with suitable permissions; use `sudo bash scripts/start.sh` if required.

## Configure and start

1. Optionally copy `config/backup.example.json` to `config/backup.json` to choose [backup storage](backup.md). Then copy `.env.example` to `.env` if you want to edit settings before startup. Otherwise the start script creates it.
2. Keep `AIO_BIND_IP` and `APACHE_IP_BINDING` at `127.0.0.1` for host-based Tailscale Serve.
3. Run the commands for your platform from the repository directory:

| Windows PowerShell | Linux |
| --- | --- |
| `./windows/start.ps1` | `bash scripts/start.sh` |
| `./windows/tailscale.ps1` | `bash scripts/tailscale.sh` |

| Setting | Default | Purpose |
| --- | --- | --- |
| `AIO_PORT` | `18080` | Local HTTPS administration |
| `APACHE_PORT` | `11000` | HTTP backend used by Serve |
| `SKIP_DOMAIN_VALIDATION` | `true` | Bypass public reachability checks for private access |

Shell variables override `.env`. The backend port belongs to AIO's Apache container, not the master.

1. Open [AIO administration](https://localhost:18080), accepting its initial self-signed certificate. Save the AIO password.
2. Enter the hostname printed by Serve, without `https://` or a path. Enable Collabora; leave Talk and other unnecessary services disabled.
3. Start application containers and wait until ready. Save the separate Nextcloud administrator credentials.
4. Open Nextcloud using the Tailscale HTTPS URL. Serve will not reach the backend until the application containers are running.

Serve uses the host's root HTTPS route. Check existing routes before replacing another service. A custom domain or public access requires a different proxy/certificate setup.

## Troubleshooting and shutdown

- Status: `./windows/status.ps1` or `bash scripts/status.sh`; forwarding: `tailscale serve status`.
- Port unavailable: change `.env`, rerun startup. For backend changes, stop applications through AIO first, restart them afterwards and rerun the Serve helper.
- Office/connectivity failure: check hostname resolution and HTTPS access from containers as well as browsers. Skipping domain validation does not fix networking.
- Shutdown: stop applications through AIO, then run the platform's `stop` script. Never use `down -v` for routine shutdown.
- Disable the Serve HTTPS route with `tailscale serve --https=443 off`. Stopping AIO alone does not remove it.

References: [AIO reverse proxy](https://github.com/nextcloud/all-in-one/blob/main/reverse-proxy.md), [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve).
