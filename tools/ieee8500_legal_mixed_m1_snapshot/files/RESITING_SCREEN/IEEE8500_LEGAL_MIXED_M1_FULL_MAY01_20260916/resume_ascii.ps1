$ErrorActionPreference = 'Stop'
$runDir = 'D:\ChatGPT\Mobile ESS 2\RESITING_SCREEN\IEEE8500_LEGAL_MIXED_M1_FULL_MAY01_20260916'
$pythonExe = 'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe'
$state = Get-Content -LiteralPath (Join-Path $runDir 'SUPERVISOR_STATUS.json') -Raw | ConvertFrom-Json
if ($state.status -ne 'FAILED') { throw 'Resume is only allowed from a failed supervisor; do not duplicate a running worker.' }
& $pythonExe -B -u (Join-Path $runDir 'native_solver_io_preflight.py')
if ($LASTEXITCODE -ne 0) { throw 'Native solver I/O preflight failed.' }
$stamp = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
Start-Process -FilePath $pythonExe -ArgumentList @('-B','-u','full_supervisor.py','--resume') -WorkingDirectory $runDir -RedirectStandardOutput (Join-Path $runDir "supervisor.resume.$stamp.stdout.log") -RedirectStandardError (Join-Path $runDir "supervisor.resume.$stamp.stderr.log") -WindowStyle Hidden -PassThru
