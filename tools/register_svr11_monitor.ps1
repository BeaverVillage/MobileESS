param([string]$CampaignRoot='D:\v42_svr11_may_20261011_02',[string]$SourceRoot='D:\v42_svr11_epoch02_20261011')
$ErrorActionPreference='Stop'
$v42Python='C:\Users\kjw39\AppData\Local\Programs\Python\Python311\pythonw.exe'
$v42Tasks=@('MobileESS_V42_May_B2_B3_Autonomous_Supervisor','MobileESS_V42_May_B2_B3_Autonomous_Monitor')
foreach($v42Name in $v42Tasks){
  $v42Extra=if($v42Name.EndsWith('_Monitor')){' --monitor-only'}else{''}
  $v42Arguments='-B -X utf8 '+(Join-Path $SourceRoot 'tools\svr11_monitor_ui.py')+' watchdog '+$CampaignRoot+$v42Extra
  $v42Action=New-ScheduledTaskAction -Execute $v42Python -Argument $v42Arguments -WorkingDirectory $SourceRoot
  Set-ScheduledTask -TaskName $v42Name -Action $v42Action | Out-Null
  Enable-ScheduledTask -TaskName $v42Name | Out-Null
}
$v42Snapshot=foreach($v42Name in $v42Tasks){
 $v42Task=Get-ScheduledTask -TaskName $v42Name
 $v42Info=Get-ScheduledTaskInfo -TaskName $v42Name
 [pscustomobject]@{Name=$v42Name;State=$v42Task.State.ToString();Actions=@($v42Task.Actions|Select-Object Execute,Arguments,WorkingDirectory);Triggers=@($v42Task.Triggers|Select-Object StartBoundary,Enabled,@{N='Repeat';E={$_.Repetition.Interval}});LastRun=$v42Info.LastRunTime;LastResult=$v42Info.LastTaskResult;NextRun=$v42Info.NextRunTime}
}
$v42Snapshot | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $CampaignRoot 'WINDOWS_SCHEDULE_REGISTRATION.json') -Encoding utf8
$v42Snapshot | ConvertTo-Json -Depth 5
