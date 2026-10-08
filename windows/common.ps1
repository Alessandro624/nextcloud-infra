$ErrorActionPreference = 'Stop'
$script:Root = Split-Path $PSScriptRoot -Parent
function Get-TailscaleExecutable {
    $command = Get-Command tailscale.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    foreach ($directory in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA)) {
        if ([string]::IsNullOrWhiteSpace($directory)) { continue }
        $candidate = Join-Path $directory 'Tailscale/tailscale.exe'
        if (Test-Path -LiteralPath $candidate -PathType Leaf) { return $candidate }
    }
    throw 'Tailscale CLI was not found in PATH or the standard installation directories. Install Tailscale or add the directory containing tailscale.exe to PATH.'
}
function Invoke-Aio {
    & docker compose --project-directory $script:Root -f "$script:Root/compose.yml" @args
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed ($LASTEXITCODE)." }
}
function Get-AioSettings {
    $config = ((Invoke-Aio config --format json) -join "`n") | ConvertFrom-Json
    $service = $config.services.'nextcloud-aio-mastercontainer'
    $binding = $service.ports | Where-Object { $_.target -eq 8080 } | Select-Object -First 1
    $address = $binding.host_ip
    if ($address -in @('0.0.0.0', '::', '127.0.0.1', '::1')) { $address = 'localhost' }
    if ($address.Contains(':')) { $address = "[$address]" }
    [pscustomobject]@{
        AdminUrl = "https://${address}:$($binding.published)"
        ApachePort = $service.environment.APACHE_PORT
        ApacheBindIp = $service.environment.APACHE_IP_BINDING
    }
}
