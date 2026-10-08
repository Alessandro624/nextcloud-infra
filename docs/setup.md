# Setup

## Requirements

- A domain you control, for example `cloud.example.com`, and access to its DNS configuration.
- Docker Engine with Compose on Linux, or Docker Desktop using Linux containers on Windows.
- Sufficient CPU, memory and storage for users, documents and backups. Start evaluation with 4 vCPU and 8 GB RAM, then measure your workload.
- A network and certificate strategy selected before deployment.

Install Docker using its [official instructions](https://docs.docker.com/engine/install/). For Windows-specific AIO requirements, consult the [AIO documentation](https://github.com/nextcloud/all-in-one#how-to-run-aio-on-windows).

## Domain and HTTPS

The supplied `compose.yml` uses the standard AIO deployment, with ports 80 and 8443 published and its administration interface bound to loopback port 8080. AIO's Apache container publishes the application HTTPS port 443 separately; keep that port available too.

For the standard publicly reachable setup, point the domain's DNS records to the host's reachable address, configure routing/firewall rules required by AIO, and ensure the domain is reachable from clients and containers. Only publish an IPv6 record if IPv6 routing works. See the [official port documentation](https://github.com/nextcloud/all-in-one#explanation-of-used-ports).

Owning a domain does not require making Nextcloud public. For LAN-only access, configure internal DNS and valid HTTPS using the [local-instance guide](https://github.com/nextcloud/all-in-one/blob/main/local-instance.md). DNS-based certificate validation and a reverse proxy require adapting this Compose file according to the [reverse-proxy guide](https://github.com/nextcloud/all-in-one/blob/main/reverse-proxy.md). The supplied file does not configure that proxy or your DNS provider.

## Start and configure

From the repository directory:

```bash
bash scripts/start.sh
```

Or on Windows:

```powershell
./windows/start.ps1
```

Open https://localhost:8080 on the host. The initial AIO interface uses a self-signed certificate. For remote Linux administration, use `ssh -L 8080:127.0.0.1:8080 operator@server` and open the same URL on your computer.

If Windows reserves port 8080, change only the host side of the management mapping, for example `127.0.0.1:18080:8080`, and use https://localhost:18080 instead. The service still requires a domain for the application.

Save the AIO password in the password manager, enter the domain in the wizard, enable Collabora, and start the application containers. Store the generated Nextcloud administrator credentials. Configure backup before importing business data.

Named Docker volumes are used by default. If a custom data directory is needed, configure `NEXTCLOUD_DATADIR` using the upstream instructions before the first installation; do not change it afterwards. Keep the master container name and volume name unchanged.

## Acceptance checks

1. Sign in through the domain with a valid HTTPS certificate.
2. Create two test users and share a folder with editing permissions.
3. Open the same DOCX and XLSX in separate browser sessions; verify simultaneous editing, saving and reopening.
4. Test representative formulas, formatting, images and comments, including downloaded files in Microsoft Office.
5. Restart application containers through AIO and verify users and files persist.
6. Complete a backup and an isolated restore before migration.

## Operations

Use `bash scripts/status.sh` or `./windows/status.ps1` for container status. These commands do not verify backup freshness or application functionality.

Before running `scripts/stop.sh` or `windows/stop.ps1`, stop the application containers through AIO. Both scripts then request confirmation before stopping the master. Never use `docker compose down -v` for routine shutdown.

For updates, first verify a recent recoverable backup, use AIO's supported update workflow, then repeat the acceptance checks. See [AIO updates](https://github.com/nextcloud/all-in-one#how-to-update-the-containers).
