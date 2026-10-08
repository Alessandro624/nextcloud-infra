# Setup

This deployment uses Tailscale installed directly on the Docker host. Tailscale Serve provides private HTTPS access to Nextcloud through the host's `*.ts.net` hostname. A purchased domain is not required. AIO administration stays local.

## Requirements

- Docker Desktop with Linux containers on Windows, or Docker Engine and Compose on Linux.
- Tailscale installed on the host and each test client, signed in with access to the host.
- MagicDNS and HTTPS certificates enabled in the Tailscale admin console. Serve prompts you to enable HTTPS if necessary.
- Available host ports: 18080 for administration and 11000 for the application backend by default.
- Sufficient resources; start evaluation with 4 vCPU and 8 GB RAM and measure your workload.

The Linux Tailscale helper also requires Python 3. Internet access is needed for image downloads, certificate provisioning and Tailscale coordination.

## 1. Configure the environment

On Windows, from the repository directory:

```powershell
Copy-Item .env.example .env
```

On Linux:

```bash
cp .env.example .env
```

Only copy the template if `.env` does not already exist. The start scripts do this automatically when it is missing. Edit `.env` before starting:

| Setting | Default | Purpose |
| --- | --- | --- |
| `AIO_BIND_IP` | `127.0.0.1` | Host address for the administration interface |
| `AIO_PORT` | `18080` | Host HTTPS administration port |
| `APACHE_IP_BINDING` | `127.0.0.1` | Host address for the HTTP application backend |
| `APACHE_PORT` | `11000` | Backend port used by Tailscale Serve |
| `SKIP_DOMAIN_VALIDATION` | `true` | Skip the public reachability check for this private deployment |

Keep both bind addresses on loopback for this setup. The Tailscale helper requires `APACHE_IP_BINDING=127.0.0.1`. Compose shell environment variables take precedence over `.env`; helpers use the resolved Compose configuration too.

Do not add the backend port to the master's port mappings: AIO publishes it on its Apache container. The domain is configured through the AIO wizard, not `.env`. Skipping domain validation does not fix DNS or certificate problems.

## 2. Start the AIO master

Windows:

```powershell
./windows/start.ps1
```

Linux:

```bash
bash scripts/start.sh
```

Open the printed administration endpoint, https://localhost:18080 by default. Its initial self-signed certificate is expected. Save the AIO password in your password manager.

If Windows reserves a chosen port, select another free host port in `.env` and rerun start. Port 8080 was unavailable during the initial test on this PC, which is why the default is 18080.

## 3. Configure Tailscale Serve

Install Tailscale, sign in and reopen the terminal if the command is not found. Check `tailscale status`, then run:

```powershell
./windows/tailscale.ps1
```

Or on Linux:

```bash
bash scripts/tailscale.sh
```

The helper runs `tailscale serve --bg http://127.0.0.1:<APACHE_PORT>`. Follow any HTTPS enablement link from Tailscale and rerun if required. It configures the root HTTPS route on this device; use a dedicated device hostname if another application already occupies that route. It does not enable Funnel or public Internet access.

Read the HTTPS URL from `tailscale serve status`, for example `https://your-pc.your-tailnet.ts.net`. Enter only the hostname in the AIO wizard. The backend will not respond until AIO has started its application containers.

## 4. Complete AIO setup

Enter the Tailscale hostname, enable Collabora and start the application containers. Leave optional services such as Talk disabled for the initial file/Office test; they may publish additional ports. Store the generated Nextcloud credentials separately from the AIO administration password.

Open the Tailscale HTTPS URL, including when testing from the server PC. Named Docker volumes store application data. Configure a custom `NEXTCLOUD_DATADIR` only before first installation, following upstream instructions.

## 5. Connect another person

Invite the tester to your tailnet or share the host through Tailscale's supported device-sharing workflow. Ensure access policy permits HTTPS to this device. Have them install Tailscale, accept the invitation and connect. Create a separate Nextcloud user and share a test folder with that user.

Give the tester the Tailscale HTTPS application URL. The loopback AIO administration URL is not their login URL. Your host must remain awake with Docker and Tailscale running.

## 6. Acceptance checks

1. Open Nextcloud through its Tailscale URL from both devices with a valid certificate.
2. Upload, download, rename, delete and recover test files; check permissions.
3. Open the same DOCX and XLSX in separate user sessions; check simultaneous edits, saving and reopening.
4. Validate representative formulas, formatting and images, including downloaded files in Microsoft Office.
5. Restart applications through AIO and verify persistence.
6. Complete a backup and isolated restore before importing business data.

## Diagnostics and operations

Use `./windows/status.ps1` or `bash scripts/status.sh` for container state. Use `tailscale serve status` for the forwarding target. These are not backup or end-to-end health checks.

If the backend cannot be reached, check its published port after AIO has started Apache. If Office or callbacks fail, verify that the Tailscale hostname resolves and is reachable from the AIO containers, not just from the Windows browser. Docker Desktop's VM networking may require additional DNS/routing configuration. Do not treat skipped domain validation as evidence that networking works.

After changing the backend port, stop application containers through AIO, recreate the master using the start script, restart the applications through AIO and rerun the Tailscale helper. Check the actual Apache port mapping. Changing `.env` alone does not reconfigure running containers or Serve.

Before using a stop script, stop the application containers through AIO; the script then stops only the master. Serve remains configured and resumes after a host restart. To disable this HTTPS route, use `tailscale serve --https=443 off`. Never use `docker compose down -v` for routine shutdown.

Use AIO's update workflow after verifying a recent recoverable backup. Moving to public HTTPS or a custom domain requires revisiting the proxy and certificate configuration; it is not just an environment variable change.

## References

- [AIO reverse proxy](https://github.com/nextcloud/all-in-one/blob/main/reverse-proxy.md)
- [AIO local instance](https://github.com/nextcloud/all-in-one/blob/main/local-instance.md)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [AIO on Windows](https://github.com/nextcloud/all-in-one#how-to-run-aio-on-windows)
