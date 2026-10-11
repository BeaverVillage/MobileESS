param([string]$CampaignRoot='D:\v42_svr11_may_20261011_02', [string]$SourceRoot='D:\v42_svr11_epoch02_20261011')
$ErrorActionPreference='Stop'
$v42Python='C:\Users\kjw39\AppData\Local\Programs\Python\Python311\pythonw.exe'
$v42Tasks=@('MobileESS_V42_May_B2_B3_Autonomous_Supervisor','MobileESS_V42_May_B2_B3_Autonomous_Monitor')
$v42Archive=Join-Path $CampaignRoot 'previous_schedules'
New-Item -ItemType Directory -Force -Path $v42Archive | Out-Null
foreach($v42Name in $v42Tasks){
  $v42Old=Get-ScheduledTask -TaskName $v42Name
  $v42ArchiveFile=Join-Path $v42Archive ($v42Name+'.xml')
  if(!(Test-Path -LiteralPath $v42ArchiveFile)){Export-ScheduledTask -TaskName $v42Name | Set-Content -LiteralPath $v42ArchiveFile -Encoding utf8}
  Disable-ScheduledTask -TaskName $v42Name | Out-Null
  # Only the archived monitor task is stopped; it owns no scientific Solver.
  if($v42Name.EndsWith('_Monitor')){Stop-ScheduledTask -TaskName $v42Name}
  $v42Extra=if($v42Name.EndsWith('_Monitor')){' --monitor-only'}else{''}
  $v42Arguments='-B -X utf8 -m v42_svr11.watchdog '+$CampaignRoot+$v42Extra
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
