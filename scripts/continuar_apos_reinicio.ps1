param([switch]$SomenteBancos)
$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $raizProjeto

$dockerExecutavel = $null
$desktopExecutavel = $null
foreach ($pastaDocker in @("$env:LOCALAPPDATA/Programs/DockerDesktop", 'C:/Program Files/Docker/Docker')) {
    $candidatoDesktop = Join-Path $pastaDocker 'Docker Desktop.exe'
    if (Test-Path -LiteralPath $candidatoDesktop) {
        $desktopExecutavel = $candidatoDesktop
        $dockerExecutavel = Join-Path $pastaDocker 'resources/bin/docker.exe'
        break
    }
}
if (-not $desktopExecutavel) {
    & winget install --id Docker.DockerDesktop --exact --source winget --silent --accept-package-agreements --accept-source-agreements --disable-interactivity --override 'install --user --quiet --accept-license --backend=wsl-2 --no-windows-containers'
    if ($LASTEXITCODE -ne 0) { throw 'A instalacao Docker ainda nao foi concluida. Consulte .logs e os requisitos do WSL 2.' }
    foreach ($pastaDocker in @("$env:LOCALAPPDATA/Programs/DockerDesktop", 'C:/Program Files/Docker/Docker')) {
        $candidatoDesktop = Join-Path $pastaDocker 'Docker Desktop.exe'
        if (Test-Path -LiteralPath $candidatoDesktop) {
            $desktopExecutavel = $candidatoDesktop
            $dockerExecutavel = Join-Path $pastaDocker 'resources/bin/docker.exe'
            break
        }
    }
}
if (-not $desktopExecutavel) { throw 'Docker Desktop nao encontrado depois da instalacao.' }
Start-Process -FilePath $desktopExecutavel -WindowStyle Hidden
Write-Output 'Aguardando Docker Desktop. Se ele solicitar atualizacao do WSL, conclua essa etapa na janela do Docker.'
$dockerPronto = $false
for ($tentativa = 0; $tentativa -lt 60; $tentativa++) {
    & $dockerExecutavel info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $dockerPronto = $true; break }
    Start-Sleep -Seconds 3
}
if (-not $dockerPronto) { throw 'Docker nao ficou pronto. Confira a janela do Docker Desktop e execute este script novamente.' }
& (Join-Path $PSScriptRoot 'configurar.ps1')
if ($SomenteBancos) {
    & (Join-Path $PSScriptRoot 'iniciar.ps1') -SomenteBancos
} else {
    & (Join-Path $PSScriptRoot 'iniciar.ps1')
}
