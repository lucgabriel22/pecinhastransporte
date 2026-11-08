$ErrorActionPreference = 'Stop'
$raizProjeto = Split-Path -Parent $PSScriptRoot
$pastaEstado = Join-Path $raizProjeto '.estado_local'
$pastaLogs = Join-Path $raizProjeto '.logs'
New-Item -ItemType Directory -Force -Path $pastaEstado, $pastaLogs | Out-Null
$principalAtual = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principalAtual.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Este comando precisa de PowerShell como administrador para habilitar recursos do Windows.'
}

Start-Transcript -Path (Join-Path $pastaLogs 'preparar-windows.log') -Append | Out-Null
try {
    $precisaReiniciar = $false
    foreach ($nomeRecurso in @('Microsoft-Windows-Subsystem-Linux', 'VirtualMachinePlatform')) {
        $recursoAtual = Get-WindowsOptionalFeature -Online -FeatureName $nomeRecurso
        if ($recursoAtual.State -eq 'EnablePending') { $precisaReiniciar = $true }
        if ($recursoAtual.State -ne 'Enabled' -and $recursoAtual.State -ne 'EnablePending') {
            $resultadoRecurso = Enable-WindowsOptionalFeature -Online -FeatureName $nomeRecurso -All -NoRestart
            if ($resultadoRecurso.RestartNeeded) { $precisaReiniciar = $true }
        }
    }
    @{recursosHabilitados=$true; reinicializacaoNecessaria=$precisaReiniciar; verificadoEm=(Get-Date).ToString('o')} |
        ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $pastaEstado 'windows.json')
    if ($precisaReiniciar) {
        Write-Output 'Recursos habilitados. Reinicie o Windows quando encerrar seu trabalho. Este script nao reinicia o computador.'
    } else {
        Write-Output 'Recursos Windows habilitados. Continue com scripts\continuar_apos_reinicio.ps1.'
    }
} catch {
    @{recursosHabilitados=$false; erro=$_.Exception.Message; verificadoEm=(Get-Date).ToString('o')} |
        ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $pastaEstado 'windows.json')
    throw
} finally {
    Stop-Transcript | Out-Null
}
