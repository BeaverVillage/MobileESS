$ErrorActionPreference = 'Stop'
$r019TaskName = 'MobileESS_V44_Campaign004_Recovery_R019'
$r019Root = 'D:/v44_may01_07_prepare_20261016'
$r019Arguments = '-X utf8 -u -m v44_recovery_r019.operations --handover'
$r019Python = 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R018'
if ($oldTask.Settings.Enabled) { throw 'R018_TASK_MUST_BE_DISABLED_FIRST' }
$existing = Get-ScheduledTask -TaskName $r019TaskName -ErrorAction SilentlyContinue
if ($existing) { throw 'R019_TASK_ALREADY_EXISTS_INSPECT_BEFORE_REPLACING' }
$r019Action = New-ScheduledTaskAction -Execute $r019Python -Argument $r019Arguments -WorkingDirectory $r019Root
Register-ScheduledTask -TaskName $r019TaskName -Action $r019Action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'Sealed r019: resume May02 B3 A2 saved Phase-I support at S15 after exact replay; retain original measured Native Runtime and completed M1, then continue the single-worker campaign.' | Out-Null
Enable-ScheduledTask -TaskName $r019TaskName | Out-Null
$registered = Get-ScheduledTask -TaskName $r019TaskName
if (-not $registered.Settings.Enabled -or $registered.Actions[0].Arguments -ne $r019Arguments) { throw 'R019_TASK_REGISTRATION_FAILED' }
[pscustomobject]@{Task=$registered.TaskName; State=$registered.State.ToString(); Execute=$registered.Actions[0].Execute; Arguments=$registered.Actions[0].Arguments; WorkingDirectory=$registered.Actions[0].WorkingDirectory; ExecutionTimeLimit=$registered.Settings.ExecutionTimeLimit; MultipleInstances=$registered.Settings.MultipleInstances.ToString()} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R019_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R019_WINDOWS_TASK.json'


