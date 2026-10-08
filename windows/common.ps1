$ErrorActionPreference = 'Stop'
$script:Root = Split-Path $PSScriptRoot -Parent
function Invoke-Aio {
    & docker compose --project-directory $script:Root -f "$script:Root/compose.yml" @args
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed ($LASTEXITCODE)." }
}
