$ErrorActionPreference='Stop'
$repoFolder=Split-Path $PSScriptRoot -Parent
$pythonExe='C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe'
$principal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$monitorTask=Get-ScheduledTask -TaskName 'MobileESS_V44_StatusMonitor_20261022'
if ($monitorTask.Actions.Arguments -notlike '*monitor_recovery_20261022\monitor_service.py --port 8795*') { throw 'Existing r043 monitor binding mismatch' }
if ($monitorTask.State -ne 'Running') { Start-ScheduledTask -TaskName $monitorTask.TaskName }
foreach ($mode in @('run')) {
 $taskName='MobileESS_V44_iteration2_'+$mode
 $existing=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
 if ($existing) {
  if ($existing.Actions.WorkingDirectory -ne $repoFolder -or $existing.Actions.Arguments -ne "-B -X utf8 -u -m v44_iteration2 --$mode") { throw "Existing task binding mismatch: $taskName" }
  if ($existing.State -ne 'Running') { Start-ScheduledTask -TaskName $taskName }
  continue
 }
 $action=New-ScheduledTaskAction -Execute $pythonExe -Argument "-B -X utf8 -u -m v44_iteration2 --$mode" -WorkingDirectory $repoFolder
 $trigger=New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
 Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Independent V44_iteration2 B3 May01-31. Wait for final B2 completion, dead PIDs, released locks and reconciled ledgers; all31 M4 barrier; original scientific engines; rolling Actual max7 with RAM gate.' | Out-Null
 Start-ScheduledTask -TaskName $taskName
}
