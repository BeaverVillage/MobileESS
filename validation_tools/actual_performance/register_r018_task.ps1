$ErrorActionPreference = 'Stop'
$r018TaskName = 'MobileESS_V44_Campaign004_Recovery_R018'
$r018Root = 'D:/v44_may01_07_prepare_20261016'
$r018Arguments = '-X utf8 -u -m v44_recovery_r018.operations --handover'
$r018Python = 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R017'
if ($oldTask.Settings.Enabled) { throw 'R017_TASK_MUST_BE_DISABLED_FIRST' }
$existing = Get-ScheduledTask -TaskName $r018TaskName -ErrorAction SilentlyContinue
if ($existing) { throw 'R018_TASK_ALREADY_EXISTS_INSPECT_BEFORE_REPLACING' }
$r018Action = New-ScheduledTaskAction -Execute $r018Python -Argument $r018Arguments -WorkingDirectory $r018Root
Register-ScheduledTask -TaskName $r018TaskName -Action $r018Action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'Sealed r018: resume May02 B3 A2 saved Phase-I support at S15 after exact replay; retain original measured Native Runtime and completed M1, then continue the single-worker campaign.' | Out-Null
Enable-ScheduledTask -TaskName $r018TaskName | Out-Null
$registered = Get-ScheduledTask -TaskName $r018TaskName
if (-not $registered.Settings.Enabled -or $registered.Actions[0].Arguments -ne $r018Arguments) { throw 'R018_TASK_REGISTRATION_FAILED' }
[pscustomobject]@{Task=$registered.TaskName; State=$registered.State.ToString(); Execute=$registered.Actions[0].Execute; Arguments=$registered.Actions[0].Arguments; WorkingDirectory=$registered.Actions[0].WorkingDirectory; ExecutionTimeLimit=$registered.Settings.ExecutionTimeLimit; MultipleInstances=$registered.Settings.MultipleInstances.ToString()} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R018_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R018_WINDOWS_TASK.json'

