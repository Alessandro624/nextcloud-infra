. "$PSScriptRoot/common.ps1"
$tailscaleExecutable = Get-TailscaleExecutable
$settings = Get-AioSettings
if ($settings.ApacheBindIp -ne '127.0.0.1') {
    throw 'This helper requires APACHE_IP_BINDING=127.0.0.1 for host-based Tailscale Serve.'
}
$status = (& $tailscaleExecutable status --json) -join "`n"
if ($LASTEXITCODE -ne 0) { throw 'Unable to read Tailscale status.' }
$status = $status | ConvertFrom-Json
if ($status.BackendState -ne 'Running') { throw 'Connect Tailscale and sign in first.' }
& $tailscaleExecutable serve --bg "http://127.0.0.1:$($settings.ApachePort)"
if ($LASTEXITCODE -ne 0) { throw 'Tailscale Serve failed. Follow its HTTPS enablement instructions and retry.' }
& $tailscaleExecutable serve status
if ($LASTEXITCODE -ne 0) { throw 'Unable to read Tailscale Serve status.' }
Write-Host 'Enter the displayed hostname in AIO, without https:// or a path.'
Write-Host 'The backend becomes available after you start the application containers in AIO.'
