param([switch]$SemInstalarDependencias)
$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $raizProjeto
$pythonProjeto = Join-Path $raizProjeto '.venv/Scripts/python.exe'

if (-not (Test-Path -LiteralPath $pythonProjeto)) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv venv --python 3.12 .venv
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
    } else {
        throw 'Instale Python 3.12 e execute este comando novamente.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ambiente Python.' }
}

if (-not $SemInstalarDependencias) {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv pip install --python $pythonProjeto -r requirements.txt
    } else {
        & $pythonProjeto -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar pip.' }
        & $pythonProjeto -m pip install -r requirements.txt
    }
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependencias.' }
}

& $pythonProjeto -m scripts.configurar
if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar a configuracao local.' }
Write-Output 'Ambiente Python preparado. Proximo comando: .\scripts\iniciar.ps1'
