$ErrorActionPreference = 'Stop'
$r025bName = 'MobileESS_V44_Campaign004_Recovery_R025B'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R025'
Disable-ScheduledTask -TaskName $oldTask.TaskName | Out-Null
if (Get-ScheduledTask -TaskName $r025bName -ErrorAction SilentlyContinue) { throw 'R025B_TASK_ALREADY_EXISTS' }
$action = New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument '-X utf8 -u -m v44_recovery_r025b.operations --handover' -WorkingDirectory 'D:/v44_r022_rowgen_20261017'
Register-ScheduledTask -TaskName $r025bName -Action $action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'r025b B1/B3 A Native3600 PhaseI1000; May02 B3 A2 exact active-row checkpoint and Native414.457 continuation; verified UB freeze and compatible physical gates.' | Out-Null
Enable-ScheduledTask -TaskName $r025bName | Out-Null
$task=Get-ScheduledTask -TaskName $r025bName
[pscustomobject]@{Task=$task.TaskName;State=$task.State.ToString();Enabled=$task.Settings.Enabled;Arguments=$task.Actions[0].Arguments;ExecutionTimeLimit=$task.Settings.ExecutionTimeLimit} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R025B_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R025B_WINDOWS_TASK.json'
