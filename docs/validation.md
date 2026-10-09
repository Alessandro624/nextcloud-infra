# End-to-end validation

Use this checklist on a **dedicated test installation**: Windows/Docker Desktop as the source, Ubuntu/VirtualBox as the restore target. For a permanent server, follow [setup](setup.md) and skip cleanup.

Run from the repository root. **Windows** blocks are PowerShell; **Ubuntu** blocks run over SSH. Stop on any command error. Use only disposable data and keep passwords outside Git.

## 1. Prepare the source

Install Docker Desktop, Python 3, Tailscale, VirtualBox and rclone.

**Windows:**

```powershell
$repo = (Get-Location).Path
$vmName = 'Nextcloud-Backup-Validation'
$externalRoot = 'E:\Nextcloud-Backup-Test' # Dedicated folder on your disk/NAS.
$remoteRoot = 'offsite:nextcloud-test'     # Dedicated remote test prefix.
python --version
rclone version
python -m unittest discover -s tests -v
docker compose config --quiet
docker desktop start
docker info --format '{{.OSType}}'
```

Expect passing tests and Docker OS `linux`.

```powershell
if (-not (Test-Path config/backup.json)) {
    Copy-Item config/backup.example.json config/backup.json
}
Get-Content config/backup.json
./windows/start.ps1
./windows/tailscale.ps1
```

Initially select `source_type=volume`, `source=nextcloud_aio_backupdir`, `copy_type=none`. Open [AIO](https://localhost:18080), save its password, enter the Tailscale hostname, enable Collabora and start applications.

Open the Tailscale HTTPS URL, create two Nextcloud users and share a folder. Create DOCX/XLSX files containing `BACKUP TEST 1`. Verify simultaneous editing, permissions, saving and reopening.

## 2. Test the volume backup

In AIO set the backup destination to `nextcloud_aio_backupdir`, save the Borg password, create a backup and run its integrity check. Stop applications through AIO and wait for Borg to finish.

```powershell
docker stop nextcloud-aio-mastercontainer
python scripts/backup.py export
$volumeExport = 'Paste the completed export directory printed above'
python scripts/backup.py verify --export "$volumeExport"
```

Expect `SHA-256 verified`. Preserve this export and password until the entire test passes.

## 3. Test the host-folder backup

```powershell
New-Item -ItemType Directory -Force 'C:\Nextcloud-Backup-Test' | Out-Null
$cfg = Get-Content config/backup.json -Raw | ConvertFrom-Json
$cfg.source_type = 'path'
$cfg.source = '/run/desktop/mnt/host/c/Nextcloud-Backup-Test'
$cfg | ConvertTo-Json | Set-Content config/backup.json
python scripts/backup.py prepare
docker start nextcloud-aio-mastercontainer
```

In AIO expand backup options, select **Reset backup location**, then enter `/run/desktop/mnt/host/c/Nextcloud-Backup-Test`. JSON changes alone do not change AIO's destination. Save the password now displayed; do not assume it is unchanged.

Start applications, add `BACKUP TEST 2` to the documents, create a backup and check integrity. Confirm `C:\Nextcloud-Backup-Test\borg` exists. Stop applications, wait for Borg, then:

```powershell
docker stop nextcloud-aio-mastercontainer
python scripts/backup.py export
$folderExport = 'Paste the new completed export directory'
python scripts/backup.py verify --export "$folderExport"
$generation = Split-Path "$folderExport" -Leaf
```

## 4. Copy to external storage

### Disk or NAS

Confirm `$externalRoot` refers to the intended connected device, not an accidental local mount-point directory.

```powershell
New-Item -ItemType Directory -Force "$externalRoot" | Out-Null
$cfg.copy_type = 'local'
$cfg.copy_destination = $externalRoot
$cfg | ConvertTo-Json | Set-Content config/backup.json
python scripts/backup.py copy --export "$folderExport"
python scripts/backup.py verify --export (Join-Path $externalRoot $generation)
```

A second copy to the same generation must fail with `Destination generation already exists`.

### rclone remote

Run `rclone config`, create `offsite` for your provider and complete authentication. Keep rclone credentials outside Git.

```powershell
rclone listremotes
rclone lsd offsite:
$cfg.copy_type = 'rclone'
$cfg.copy_destination = $remoteRoot
$cfg | ConvertTo-Json | Set-Content config/backup.json
python scripts/backup.py copy --export "$folderExport"
rclone lsf "$remoteRoot/$generation"
```

Expect `aio-backup.tar`, `aio-backup.tar.sha256` and `COPY-VERIFIED.txt`.

## 5. Recover from the external copy

Use a fresh directory, not the local export:

```powershell
$recovered = Join-Path $repo "backup\recovered-$generation"
if (Test-Path "$recovered") { throw 'Choose an unused recovery directory' }
rclone copy "$remoteRoot/$generation" "$recovered" --immutable
if ($LASTEXITCODE -ne 0) { throw 'Download failed' }
python scripts/backup.py verify --export "$recovered"
```

For disk/NAS recovery, replace the rclone command with `Copy-Item -LiteralPath (Join-Path $externalRoot $generation) -Destination "$recovered" -Recurse`, then verify. Restore separately from each destination if claiming both are validated.

### Prepare Ubuntu

Download an Ubuntu Server ISO from [Ubuntu releases](https://releases.ubuntu.com/24.04/). Verify `Get-FileHash PATH_TO_ISO -Algorithm SHA256` against the matching official `SHA256SUMS` entry.

Create `$vmName` in VirtualBox with its **own** 80 GB dynamic disk, 4 CPUs, 4 GB RAM initially and NAT networking. Increase resources for larger backups. Install Ubuntu, enable OpenSSH, use `test1` below or substitute your username. Do not install Nextcloud/Docker snaps. Shut down and detach the ISO.

```powershell
$vbox = 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe'
& $vbox modifyvm $vmName --natpf1 'ssh,tcp,127.0.0.1,2222,,22'
& $vbox modifyvm $vmName --natpf1 'aio,tcp,127.0.0.1,28080,,18080'
docker desktop stop
```

Start the VM in VirtualBox, then `ssh -p 2222 test1@127.0.0.1`. If this port has an old SSH host key, verify it belonged to your deleted test VM before removing it with `ssh-keygen -R '[127.0.0.1]:2222'`.

**Ubuntu:** install Docker from its official repository. Check [upstream instructions](https://docs.docker.com/engine/install/ubuntu/) if using a different Ubuntu release.

```bash
sudo apt update
sudo apt install -y python3 curl ca-certificates
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo docker run --rm hello-world
curl -fsSL https://tailscale.com/install.sh -o /tmp/install-tailscale.sh
less /tmp/install-tailscale.sh
sudo sh /tmp/install-tailscale.sh
sudo tailscale up
```

Review the installer before running it. Complete Tailscale sign-in and permit access to the VM.

### Transfer and restore

In **Windows**, keep the earlier variables or restore their actual values in a new terminal:

```powershell
Set-Location "$repo"
git archive --format=tar --output=backup/repo-validation.tar HEAD
scp -P 2222 backup/repo-validation.tar test1@127.0.0.1:/home/test1/
scp -P 2222 "$recovered\aio-backup.tar" "$recovered\aio-backup.tar.sha256" test1@127.0.0.1:/home/test1/
```

**Ubuntu:**

```bash
cd /home/test1
sha256sum -c aio-backup.tar.sha256
mkdir nextcloud-infra
tar -xf repo-validation.tar -C nextcloud-infra
sudo mkdir -p /mnt/restore-backup
sudo tar -xf aio-backup.tar -C /mnt/restore-backup
cd nextcloud-infra
cp .env.example .env
sed -i 's/^AIO_BIND_IP=.*/AIO_BIND_IP=0.0.0.0/' .env
sudo bash scripts/start.sh
sudo bash scripts/tailscale.sh
```

Open [restore AIO](https://localhost:28080), choose **Restore former AIO instance from backup**, enter `/mnt/restore-backup` and the folder backup's Borg password, then restore.

The backup retains the source hostname. Follow [restore: hostname change](restore.md#if-the-tailscale-hostname-changed) to edit AIO's `configuration.json`, restart through AIO and check Nextcloud's `config.php` settings if old references remain. Use the VM's Tailscale hostname, not the original PC's.

### Pass criteria

On PC and phone, verify the restored accounts, `BACKUP TEST 2` contents, shares and simultaneous DOCX/XLSX editing. Create and verify a new backup in the VM; reset its destination if the restored Windows path is invalid on Linux.

## 6. Remove the disposable test

**Destructive: this deletes test data and backup copies. Skip this section on a machine you want to keep.** Do not run system-wide Docker prune or remove whole buckets, accounts or shared drives.

### VM and Tailscale

Inside the **test VM**, stop applications through AIO, then:

```bash
sudo tailscale serve --https=443 off
sudo tailscale logout
sudo shutdown -h now
```

In **Windows**, inspect the VM and its attached disks. Continue only if it is powered off and every attached disk belongs exclusively to this test:

```powershell
& $vbox showvminfo $vmName
# After checking the displayed paths and confirming the VM is disposable:
& $vbox unregistervm $vmName --delete
```

Delete the VM's stale device entry from the Tailscale admin console. Remove only the downloaded test ISO/checksum files if no other VM uses them.

Disable the PC's Serve route only if it was created for this test:

```powershell
& 'C:\Program Files\Tailscale\tailscale.exe' serve status
& 'C:\Program Files\Tailscale\tailscale.exe' serve --https=443 off
```

Keep Tailscale installed and connected if used elsewhere.

### Source Docker resources

Start Docker Desktop. These names are reserved for the test AIO installation: **do not run this against a retained/production AIO instance**. Review the lists before confirming.

```powershell
docker desktop start
docker context show # Must be the intended local Docker Desktop context.
$containers = @(docker ps -a --format '{{.Names}}' | Where-Object { $_ -match '^nextcloud-aio-' -or $_ -eq 'nextcloud-infra-backup-export' })
$volumes = @(docker volume ls --format '{{.Name}}' | Where-Object { $_ -match '^nextcloud_aio_' })
$images = @(docker image ls --format '{{.Repository}}:{{.Tag}}' | Where-Object { $_ -match '^ghcr.io/nextcloud-releases/(aio-|all-in-one:)' })
$containers
$volumes
$images
if ((Read-Host 'Type DELETE TEST to remove the listed resources') -cne 'DELETE TEST') { throw 'Cancelled' }
foreach ($item in $containers) { docker rm -f $item; if ($LASTEXITCODE -ne 0) { throw 'Container removal failed' } }
foreach ($item in $volumes) { docker volume rm $item; if ($LASTEXITCODE -ne 0) { throw 'Volume removal failed' } }
if (@(docker network ls --format '{{.Name}}') -contains 'nextcloud-aio') { docker network rm nextcloud-aio }
foreach ($item in $images) { docker image rm $item; if ($LASTEXITCODE -ne 0) { throw 'Image is still in use; inspect before proceeding' } }
```

### Export files and external copies

Delete only the test generation on external storage, after checking the preview:

```powershell
rclone delete "$remoteRoot/$generation" --dry-run
# Only after verifying the preview points to this test generation:
rclone delete "$remoteRoot/$generation" --interactive
```

Repeat for any other generations created by this test. Keep the provider account and unrelated backups. If `offsite` was created solely for testing, remove its configuration with `rclone config delete offsite` and revoke its provider authorization when no longer needed.

For local files, list exact absolute targets. Review resolved paths before deleting; remove only dedicated test directories. Restore `$repo`, `$externalRoot` and `$generation` if using a new terminal.

```powershell
$targets = @(
    (Join-Path $repo 'backup'),
    'C:\Nextcloud-Backup-Test',
    (Join-Path $externalRoot $generation)
)
foreach ($target in $targets) {
    if (-not (Test-Path -LiteralPath $target)) { continue }
    $resolved = (Resolve-Path -LiteralPath $target).Path
    if ($resolved -eq [IO.Path]::GetPathRoot($resolved) -or $resolved -eq $repo) { throw 'Unsafe target' }
    Get-Item -LiteralPath $resolved
    if ((Get-Item -LiteralPath $resolved).Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { throw 'Inspect linked directory manually' }
    if (@(Get-ChildItem -LiteralPath $resolved -Recurse -Force -Attributes ReparsePoint).Count) { throw 'Inspect nested links manually' }
    if ((Read-Host "Type DELETE to remove only $resolved") -ceq 'DELETE') {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
Set-Location "$repo"
Remove-Item -LiteralPath '.env','config/backup.json' -ErrorAction SilentlyContinue
```

If `backup/` contains anything unrelated, delete individual test generations instead. Remove any additional test downloads/exports from their exact paths. Keep `.env.example`, `config/backup.example.json` and the repository.

### Final check

```powershell
docker ps -a --format '{{.Names}}'
docker volume ls --format '{{.Name}}'
& $vbox list vms
git status --short
```

Confirm only unrelated Docker/VM resources and repository files remain. Stop Docker Desktop with `docker desktop stop` if it is not needed elsewhere. Delete test-only passwords from your password manager only after deciding no test backup needs to remain recoverable.
