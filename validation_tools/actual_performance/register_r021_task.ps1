$ErrorActionPreference = 'Stop'
$r021TaskName = 'MobileESS_V44_Campaign004_Recovery_R021'
$r021Root = 'D:/v44_may01_07_prepare_20261016'
$r021Arguments = '-X utf8 -u -m v44_recovery_r021.operations --handover'
$r021Python = 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R020'
if ($oldTask.Settings.Enabled) { throw 'R020_TASK_MUST_BE_DISABLED_FIRST' }
$existing = Get-ScheduledTask -TaskName $r021TaskName -ErrorAction SilentlyContinue
if ($existing) { throw 'R021_TASK_ALREADY_EXISTS_INSPECT_BEFORE_REPLACING' }
$r021Action = New-ScheduledTaskAction -Execute $r021Python -Argument $r021Arguments -WorkingDirectory $r021Root
Register-ScheduledTask -TaskName $r021TaskName -Action $r021Action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'Sealed r021: user-authorized May02 B3 fresh A2 from completed M1, zero A2 Native clock, robust simplex and prior-witness dominance guard, exact rebuild cache; keep both B1/B3 A2 future improvements and original tolerances.' | Out-Null
Enable-ScheduledTask -TaskName $r021TaskName | Out-Null
$registered = Get-ScheduledTask -TaskName $r021TaskName
if (-not $registered.Settings.Enabled -or $registered.Actions[0].Arguments -ne $r021Arguments) { throw 'R021_TASK_REGISTRATION_FAILED' }
[pscustomobject]@{Task=$registered.TaskName; State=$registered.State.ToString(); Execute=$registered.Actions[0].Execute; Arguments=$registered.Actions[0].Arguments; WorkingDirectory=$registered.Actions[0].WorkingDirectory; ExecutionTimeLimit=$registered.Settings.ExecutionTimeLimit; MultipleInstances=$registered.Settings.MultipleInstances.ToString()} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R021_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R021_WINDOWS_TASK.json'


