$ErrorActionPreference = 'Stop'
$r023Name = 'MobileESS_V44_Campaign004_Recovery_R023'
$r023Args = '-X utf8 -u -m v44_recovery_r023.operations --handover'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R022U'
if (Get-ScheduledTask -TaskName $r023Name -ErrorAction SilentlyContinue) { throw 'R023_TASK_ALREADY_EXISTS' }
Disable-ScheduledTask -TaskName $oldTask.TaskName | Out-Null
$action = New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument $r023Args -WorkingDirectory 'D:/v44_r022_rowgen_20261017'
Register-ScheduledTask -TaskName $r023Name -Action $action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'r023 exact sparse assembly for unstarted May03 onward B0 B1 B3. Unconditional B1 A1 and B3 A2; no current A2 PASS gate. Protect live May02 r022 case, all PASS and accounting.' | Out-Null
Enable-ScheduledTask -TaskName $r023Name | Out-Null
$registered = Get-ScheduledTask -TaskName $r023Name
if (-not $registered.Settings.Enabled -or $registered.Actions[0].Arguments -ne $r023Args) { throw 'R023_TASK_REGISTRATION_FAILED' }
[pscustomobject]@{Task=$registered.TaskName; State=$registered.State.ToString(); Arguments=$registered.Actions[0].Arguments; ExecutionTimeLimit=$registered.Settings.ExecutionTimeLimit; MultipleInstances=$registered.Settings.MultipleInstances.ToString()} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R023_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R023_WINDOWS_TASK.json'
