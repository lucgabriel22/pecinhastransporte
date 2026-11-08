$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent $PSScriptRoot
$pastaLogs = Join-Path $raizProjeto '.logs'
New-Item -ItemType Directory -Force -Path $pastaLogs | Out-Null
Start-Transcript -Path (Join-Path $pastaLogs 'instalar-wsl.log') -Append | Out-Null
try {
    & winget install --id Microsoft.WSL --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 3010) {
        $pacoteWsl = Get-AppxPackage -Name MicrosoftCorporationII.WindowsSubsystemForLinux -ErrorAction SilentlyContinue
        if (-not $pacoteWsl) { throw "A instalacao do WSL retornou codigo $LASTEXITCODE. Consulte o log." }
    }
    Write-Output 'Instalacao do WSL processada. Reinicie o Windows para ativar os recursos ja habilitados.'
} finally {
    Stop-Transcript | Out-Null
}
