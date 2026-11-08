param([switch]$SomenteBancos)
$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $raizProjeto
$pythonProjeto = Join-Path $raizProjeto '.venv/Scripts/python.exe'

if (-not (Test-Path -LiteralPath $pythonProjeto) -or -not (Test-Path -LiteralPath '.env')) {
    throw 'Execute .\scripts\configurar.ps1 primeiro.'
}

$dockerComando = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerComando) {
    foreach ($candidato in @("$env:LOCALAPPDATA/Programs/DockerDesktop/resources/bin/docker.exe", 'C:/Program Files/Docker/Docker/resources/bin/docker.exe')) {
        if (Test-Path -LiteralPath $candidato) { $dockerComando = Get-Item -LiteralPath $candidato; break }
    }
}
if (-not $dockerComando) { throw 'Docker nao encontrado. Conclua sua instalacao e abra o Docker Desktop.' }
$dockerExecutavel = if ($dockerComando.Source) { $dockerComando.Source } else { $dockerComando.FullName }
& $dockerExecutavel info --format '{{.ServerVersion}}'
if ($LASTEXITCODE -ne 0) { throw 'O mecanismo Docker nao esta pronto. Abra o Docker Desktop e confira o WSL 2.' }

& $dockerExecutavel compose up -d --wait --wait-timeout 300
if ($LASTEXITCODE -ne 0) { throw 'Os bancos nao ficaram prontos. Consulte docker compose ps e docker compose logs.' }
& $pythonProjeto -m scripts.inicializar
if ($LASTEXITCODE -ne 0) { throw 'Falha na inicializacao dos bancos.' }
& $pythonProjeto -m scripts.verificar
if ($LASTEXITCODE -ne 0) { throw 'A verificacao de conexoes falhou.' }
if (-not $SomenteBancos) {
    & $pythonProjeto -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
}
