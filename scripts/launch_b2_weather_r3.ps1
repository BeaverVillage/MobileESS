$ErrorActionPreference='Stop'
$taskName='MobileESS_V44_B2_Weather_R3_20261022'
$repoFolder=Split-Path $PSScriptRoot -Parent
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'Recovery task already exists' }
$taskAction=New-ScheduledTaskAction -Execute 'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe' -Argument '-B -X utf8 -u -m b2_recovery_r3.run --run' -WorkingDirectory $repoFolder
$taskPrincipal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$taskSettings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $taskName -Action $taskAction -Principal $taskPrincipal -Settings $taskSettings -Description 'B2 May23: reuse completed M1, verified r049 causal observations, new Actual120/Fresh120; then May24-31 sequential full B2. Preserve prior scientific sources/results.' | Out-Null
Start-ScheduledTask -TaskName $taskName
