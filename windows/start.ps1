. "$PSScriptRoot/common.ps1"
if (-not (Test-Path "$Root/.env")) { Copy-Item "$Root/.env.example" "$Root/.env" }
Invoke-Aio config --quiet
$settings = Get-AioSettings
& python "$Root/scripts/backup.py" prepare
if ($LASTEXITCODE -ne 0) { throw 'Backup storage preparation failed. Python 3 is required.' }
Invoke-Aio up -d
Write-Host "AIO administration: $($settings.AdminUrl)"
Write-Host 'Run windows/tailscale.ps1, then enter its HTTPS hostname in the AIO wizard.'
