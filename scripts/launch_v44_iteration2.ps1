$ErrorActionPreference='Stop'
$repoFolder=Split-Path $PSScriptRoot -Parent
$pythonExe='C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe'
$principal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
foreach ($mode in @('run','monitor')) {
 $taskName='MobileESS_V44_iteration2_'+$mode
 if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw "Task already exists: $taskName" }
 $action=New-ScheduledTaskAction -Execute $pythonExe -Argument "-B -X utf8 -u -m v44_iteration2 --$mode" -WorkingDirectory $repoFolder
 $trigger=New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
 Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Independent V44_iteration2 B3 May01-31. Wait for final B2 completion, dead PIDs, released locks and reconciled ledgers; all31 M4 barrier; original scientific engines; rolling Actual max7 with RAM gate.' | Out-Null
 Start-ScheduledTask -TaskName $taskName
}
