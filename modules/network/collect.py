"""Read-only Linux network inventory and bounded DNS/connection observation."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=int, default=600, help="Observation seconds, 60..7200")
    parser.add_argument("--output", type=Path, required=True, help="New output directory; must not already exist")
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        parser.error("Run on the Debian host with sudo python3")
    if not 60 <= args.duration <= 7200:
        parser.error("duration must be 60..7200 seconds")
    # Make sbin tools visible even when the interactive user's PATH omitted them.
    os.environ["PATH"] = "/usr/sbin:/usr/bin:/sbin:/bin"
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    owner = (int(os.environ.get("SUDO_UID", "0")), int(os.environ.get("SUDO_GID", "0")))
    os.chown(output, *owner)
    os.umask(0o077)
    errors = []

    def stream(name):
        file = (output / name).open("w", encoding="utf-8")
        os.fchown(file.fileno(), *owner)
        return file

    def capture(name, command):
        with stream(name) as file:
            if not shutil.which(command[0]):
                file.write("Tool unavailable: " + command[0] + "\n")
                errors.append(name + ": tool unavailable")
                return
            try:
                result = subprocess.run(command, stdout=file, stderr=subprocess.PIPE, text=True, timeout=30)
                if result.returncode:
                    errors.append(f"{name}: exit {result.returncode}: {result.stderr[:1500]}")
            except subprocess.TimeoutExpired:
                errors.append(name + ": timed out")

    started = datetime.now(timezone.utc).isoformat()
    commands = {
        "addresses.txt": ["ip", "-br", "address"],
        "routes-v4.txt": ["ip", "-4", "route", "show", "table", "all"],
        "routes-v6.txt": ["ip", "-6", "route", "show", "table", "all"],
        "ufw.txt": ["ufw", "status", "verbose"],
        "nftables.txt": ["nft", "list", "ruleset"],
        "iptables-v4.txt": ["iptables-save"],
        "iptables-v6.txt": ["ip6tables-save"],
        "docker-version.txt": ["docker", "version", "--format", "{{.Server.Version}}"],
        "containers.txt": ["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}"],
        "docker-networks.txt": ["docker", "network", "ls"],
        "aio-network.txt": [
            "docker",
            "network",
            "inspect",
            "nextcloud-aio",
            "--format",
            "{{json .IPAM.Config}} {{json .Options}} {{range .Containers}}{{.Name}}={{.IPv4Address}},{{.IPv6Address}} {{end}}",
        ],
        "listeners.txt": ["ss", "-lntup"],
        "connections-before.txt": ["conntrack", "-L"],
        "tailscale-version.txt": ["tailscale", "version"],
        "tailscale-serve.txt": ["tailscale", "serve", "status"],
        "tailscale-funnel.txt": ["tailscale", "funnel", "status"],
        "time-service.txt": ["timedatectl", "timesync-status"],
        "resolver-status.txt": ["resolvectl", "status"],
        "networkmanager-dns.txt": ["nmcli", "-f", "GENERAL.DEVICE,IP4.DNS,IP6.DNS", "device", "show"],
    }
    for name, command in commands.items():
        capture(name, command)
    with stream("resolv.conf.txt") as file:
        file.write(Path("/etc/resolv.conf").read_text())
    # Deliberately avoid full docker inspect, Tailscale prefs and environment dumps.
    with stream("services.txt") as file:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                "nextcloud-automation.service",
                "forgejo-bot.service",
                "forgejo-backup.service",
                "systemd-timesyncd.service",
                "chrony.service",
                "--no-pager",
                "--property=Id,User,Group,ActiveState,Result",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        file.write(result.stdout)

    import resource

    def cap_output():
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))

    children = []
    files = []
    for name, command in (
        ("connections-events", ["conntrack", "-E", "-o", "timestamp"]),
        ("dns-events", ["tcpdump", "-i", "any", "-nn", "-l", "-s", "512", "port 53"]),
    ):
        if not shutil.which(command[0]):
            errors.append(name + ": optional tool unavailable; no installation performed")
            continue
        out, err = stream(name + ".txt"), stream(name + "-errors.txt")
        files.extend((out, err))
        children.append((name, subprocess.Popen(command, stdout=out, stderr=err, preexec_fn=cap_output)))
    print(f"Observing for {args.duration}s. Output: {output}", flush=True)
    print("Exercise services from another device; record activity times. Ctrl+C stops collection safely.", flush=True)
    deadline = time.monotonic() + args.duration
    try:
        with stream("sockets.txt") as file:
            while time.monotonic() < deadline:
                file.write("\n" + datetime.now(timezone.utc).isoformat() + "\n")
                file.flush()
                subprocess.run(["ss", "-ntup"], stdout=file, stderr=subprocess.DEVNULL, timeout=10)
                time.sleep(min(30, max(0, deadline - time.monotonic())))
    except KeyboardInterrupt:
        errors.append("Observation ended early by operator")
    finally:
        for name, process in children:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            else:
                errors.append(f"{name}: collector exited early ({process.returncode}); inspect its error file, including output cap")
        for file in files:
            file.close()
        with stream("collection.json") as file:
            json.dump(
                {"started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(), "requested_seconds": args.duration, "errors": errors, "firewall_modified": False}, file, indent=2
            )
    print("Collection complete; review collection.json for missing data. No firewall changes were made.", flush=True)


if __name__ == "__main__":
    main()
