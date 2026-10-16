param(
    [Parameter(Mandatory=$true)][string]$ParentAttempt,
    [Parameter(Mandatory=$true)][string]$OutputAttempt,
    [string]$Python='C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe'
)
$ErrorActionPreference='Stop'
$repoPath=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoPath
$env:PYTHONPATH=$repoPath
$env:OMP_NUM_THREADS='1';$env:OPENBLAS_NUM_THREADS='1';$env:MKL_NUM_THREADS='1';$env:NUMEXPR_NUM_THREADS='1'
$stamp=[DateTimeOffset]::UtcNow.ToString('o')
try {
    $arguments=@('-u','-X','utf8','-m','v43_baseline.continue_worker',$ParentAttempt,$OutputAttempt)
    $process=Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $repoPath -WindowStyle Hidden -PassThru -RedirectStandardOutput ($OutputAttempt+'.stdout.log') -RedirectStandardError ($OutputAttempt+'.stderr.log')
    @{state='RUNNING';supervisor_PID=$PID;worker_PID=$process.Id;started_UTC=$stamp;parent=$ParentAttempt;output=$OutputAttempt}|ConvertTo-Json|Set-Content -LiteralPath ($OutputAttempt+'.PROCESS_START.json') -Encoding utf8
    $process.WaitForExit()
    @{state='EXITED';worker_PID=$process.Id;exit_code=$process.ExitCode;started_UTC=$stamp;finished_UTC=[DateTimeOffset]::UtcNow.ToString('o');result_exists=(Test-Path -LiteralPath (Join-Path $OutputAttempt 'RESULT.json'))}|ConvertTo-Json|Set-Content -LiteralPath ($OutputAttempt+'.PROCESS_EXIT.json') -Encoding utf8
} catch {
    @{state='LAUNCHER_ERROR';error=$_.Exception.Message;started_UTC=$stamp;finished_UTC=[DateTimeOffset]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath ($OutputAttempt+'.PROCESS_EXIT.json') -Encoding utf8
    throw
}
