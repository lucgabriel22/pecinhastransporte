$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& docker compose stop
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel parar os bancos.' }
Write-Output 'Bancos parados. Os volumes e seus dados foram preservados.'
