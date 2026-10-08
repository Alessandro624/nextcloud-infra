. "$PSScriptRoot/common.ps1"
Invoke-Aio config --quiet
Invoke-Aio up -d
Write-Host 'AIO administration: https://localhost:8080 (unless the host port was changed).'
Write-Host 'Configure the domain and manage application containers through AIO.'
