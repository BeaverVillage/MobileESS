$ErrorActionPreference = 'Stop'
$r020TaskName = 'MobileESS_V44_Campaign004_Recovery_R020'
$r020Root = 'D:/v44_may01_07_prepare_20261016'
$r020Arguments = '-X utf8 -u -m v44_recovery_r020.operations --handover'
$r020Python = 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R019'
if ($oldTask.Settings.Enabled) { throw 'R019_TASK_MUST_BE_DISABLED_FIRST' }
$existing = Get-ScheduledTask -TaskName $r020TaskName -ErrorAction SilentlyContinue
if ($existing) { throw 'R020_TASK_ALREADY_EXISTS_INSPECT_BEFORE_REPLACING' }
$r020Action = New-ScheduledTaskAction -Execute $r020Python -Argument $r020Arguments -WorkingDirectory $r020Root
Register-ScheduledTask -TaskName $r020TaskName -Action $r020Action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'Sealed r020: after the protected May02 B3 case finishes naturally, enable exact class-block and proof reuse plus batch graph ledger rebuilds for May03 onward B0/B1/B3 including both B1/B3 A2; preserve all original Native budgets and constraints.' | Out-Null
Enable-ScheduledTask -TaskName $r020TaskName | Out-Null
$registered = Get-ScheduledTask -TaskName $r020TaskName
if (-not $registered.Settings.Enabled -or $registered.Actions[0].Arguments -ne $r020Arguments) { throw 'R020_TASK_REGISTRATION_FAILED' }
[pscustomobject]@{Task=$registered.TaskName; State=$registered.State.ToString(); Execute=$registered.Actions[0].Execute; Arguments=$registered.Actions[0].Arguments; WorkingDirectory=$registered.Actions[0].WorkingDirectory; ExecutionTimeLimit=$registered.Settings.ExecutionTimeLimit; MultipleInstances=$registered.Settings.MultipleInstances.ToString()} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R020_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R020_WINDOWS_TASK.json'


