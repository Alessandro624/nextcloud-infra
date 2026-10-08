. "$PSScriptRoot/common.ps1"
Invoke-Aio ps -a
& docker ps -a --filter name=nextcloud-aio --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
if ($LASTEXITCODE -ne 0) { throw "Docker status failed ($LASTEXITCODE)." }
Write-Host 'Container status only. Verify application health and backups through AIO.'
