$ErrorActionPreference = 'Stop'
$r024Name = 'MobileESS_V44_Campaign004_Recovery_R024'
$r024Args = '-X utf8 -u -m v44_recovery_r024.operations --handover'
$oldTask = Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R023'
if ($oldTask.Settings.Enabled) { throw 'R023_TASK_MUST_BE_DISABLED' }
if (Get-ScheduledTask -TaskName $r024Name -ErrorAction SilentlyContinue) { throw 'R024_TASK_ALREADY_EXISTS' }
$action = New-ScheduledTaskAction -Execute 'C:/Users/kjw39/AppData/Local/Programs/Python/Python311/pythonw.exe' -Argument $r024Args -WorkingDirectory 'D:/v44_r022_rowgen_20261017'
Register-ScheduledTask -TaskName $r024Name -Action $action -Trigger $oldTask.Triggers -Principal $oldTask.Principal -Settings $oldTask.Settings -Description 'r024 Phase I Adaptive Multi-Column Pricing. User-authorized May02 B3 A2 Native0 fresh restart; all unstarted B1 B3 A stages unconditional, exact proofs and all prior PASS preserved.' | Out-Null
Enable-ScheduledTask -TaskName $r024Name | Out-Null
$task=Get-ScheduledTask -TaskName $r024Name
[pscustomobject]@{Task=$task.TaskName;State=$task.State.ToString();Enabled=$task.Settings.Enabled;Arguments=$task.Actions[0].Arguments;ExecutionTimeLimit=$task.Settings.ExecutionTimeLimit} | ConvertTo-Json | Set-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R024_WINDOWS_TASK.json' -Encoding utf8
Get-Content -LiteralPath 'D:/MobileESS_V44/runtime/v43_planning_svr12_actual_v1/campaign004/AUTONOMOUS_RECOVERY/R024_WINDOWS_TASK.json'
