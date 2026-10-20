$ErrorActionPreference = 'Stop'
$r016Ops = 'D:\MobileESS_V44\runtime\v43_planning_svr12_actual_v1\campaign004\AUTONOMOUS_RECOVERY'
if (Get-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R016' -ErrorAction SilentlyContinue) { throw 'R016 task already exists' }
$r016TaskXml = Export-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R015'
[System.IO.File]::WriteAllText((Join-Path $r016Ops 'R016_PREVIOUS_R015_TASK_PRESERVED.xml'), $r016TaskXml)
$r016TaskXml = $r016TaskXml.Replace('r015', 'r016').Replace('R015', 'R016')
Register-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R016' -Xml $r016TaskXml | Select-Object TaskName,State
Disable-ScheduledTask -TaskName 'MobileESS_V44_Campaign004_Recovery_R015' | Select-Object TaskName,State
