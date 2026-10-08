. "$PSScriptRoot/common.ps1"
Write-Host 'Stop application containers through AIO before stopping the master.'
$answer = Read-Host 'Application containers stopped? Type STOP to continue'
if ($answer -cne 'STOP') { throw 'Shutdown cancelled.' }
Invoke-Aio stop
