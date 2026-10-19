param([ValidateSet('start','stop')][string]$Action = 'start')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$stateFile = Join-Path $runtimeDir 'processes.json'

function Stop-OwnedProcesses {
    if (-not (Test-Path -LiteralPath $stateFile)) { return }
    $savedProcesses = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    foreach ($entry in $savedProcesses) {
        $runningProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$entry.id)
        if ($runningProcess -and $runningProcess.CreationDate.ToUniversalTime().ToString('o') -eq $entry.started -and $runningProcess.CommandLine.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            # Windows virtualenv Python can spawn a redirector child; stop the verified tree.
            Stop-OwnedTree -ProcessId $runningProcess.ProcessId
        }
    }
    Remove-Item -LiteralPath $stateFile -Force
}

function Stop-OwnedTree([int]$ProcessId) {
    foreach ($child in @(Get-CimInstance Win32_Process -Filter ('ParentProcessId = ' + $ProcessId))) {
        Stop-OwnedTree -ProcessId $child.ProcessId
    }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

if ($Action -eq 'stop') {
    Stop-OwnedProcesses
    Write-Host 'Application arretee. Les envois interrompus seront marques A verifier au prochain lancement.'
    exit 0
}
if (Test-Path -LiteralPath $stateFile) {
    Write-Host 'Une session existe. Lancez stop.bat avant de redemarrer.'
    exit 1
}
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$vitePath = Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $vitePath)) {
    Write-Host 'Executez setup.bat avant le premier lancement.'
    exit 1
}
foreach ($servicePort in @(8000,5173)) {
    if (Get-NetTCPConnection -LocalPort $servicePort -State Listen -ErrorAction SilentlyContinue) {
        Write-Host "Le port $servicePort est occupe. Fermez le service concerne avant de continuer."
        exit 1
    }
}
$startedProcesses = @()
try {
    $backendProcess = Start-Process -FilePath $pythonPath -ArgumentList @('-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port','8000','--no-access-log') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'backend.log') -RedirectStandardError (Join-Path $runtimeDir 'backend-error.log')
    $backendInfo = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $backendProcess.Id)
    $startedProcesses += @{id=$backendProcess.Id;started=$backendInfo.CreationDate.ToUniversalTime().ToString('o')}
    $startedProcesses | ConvertTo-Json | Set-Content -LiteralPath $stateFile
    $nodePath = (Get-Command node.exe).Source
    $frontendArgs = '"{0}" --host 127.0.0.1 --port 5173 --strictPort' -f $vitePath
    $frontendProcess = Start-Process -FilePath $nodePath -ArgumentList $frontendArgs -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'frontend.log') -RedirectStandardError (Join-Path $runtimeDir 'frontend-error.log')
    $frontendInfo = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + $frontendProcess.Id)
    $startedProcesses += @{id=$frontendProcess.Id;started=$frontendInfo.CreationDate.ToUniversalTime().ToString('o')}
    $startedProcesses | ConvertTo-Json | Set-Content -LiteralPath $stateFile
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $backendResponse = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
            $frontendResponse = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173' -TimeoutSec 2
            if ($backendResponse.StatusCode -eq 200 -and $frontendResponse.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
        if ($backendProcess.HasExited -or $frontendProcess.HasExited) { break }
    }
    if (-not $ready) { throw 'Demarrage impossible. Consultez les fichiers .runtime/*-error.log.' }
    Start-Process 'http://127.0.0.1:5173'
    Write-Host 'PFE Mail Agent : http://127.0.0.1:5173 - Arret : stop.bat'
} catch {
    Stop-OwnedProcesses
    Write-Host $_.Exception.Message
    exit 1
}
