param([switch]$Integracao)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if ($Integracao) {
    & ./.venv/Scripts/python.exe -m scripts.testar --integracao
} else {
    & ./.venv/Scripts/python.exe -m scripts.testar
}
if ($LASTEXITCODE -ne 0) { throw 'A verificacao nao foi concluida com sucesso. Consulte o resultado acima.' }
