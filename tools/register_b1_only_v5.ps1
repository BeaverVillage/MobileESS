param([string]$CampaignRoot='D:\v42_b1_only_may_20261012_05',[string]$SourceRoot='D:\v42_b1_repair_source_20261012')
$ErrorActionPreference='Stop'
$v42TaskName='MobileESS_V42_B1_Only_May2025_20261012_V5_Watchdog'
$v42Python='C:\Users\kjw39\AppData\Local\Programs\Python\Python311\pythonw.exe'
$v42ConsolePython=$v42Python.Replace('pythonw.exe','python.exe')
& $v42ConsolePython -B -X utf8 ($SourceRoot+'\tools\b1_only_v5.py') verify_release $CampaignRoot
if($LASTEXITCODE -ne 0){throw 'B1_EXPLICIT_RESUME_AND_SEALED_CONTINUATION_REQUIRED'}
$v42Action=New-ScheduledTaskAction -Execute $v42Python -Argument ('-B -X utf8 '+$SourceRoot+'\tools\b1_only_v5.py safeguard '+$CampaignRoot) -WorkingDirectory $SourceRoot
$v42Trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$v42Settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$v42Principal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
if(Get-ScheduledTask -TaskName $v42TaskName -ErrorAction SilentlyContinue){throw 'B1_ONLY_TASK_ALREADY_REGISTERED'}
Register-ScheduledTask -TaskName $v42TaskName -Action $v42Action -Trigger $v42Trigger -Settings $v42Settings -Principal $v42Principal | Out-Null
Start-ScheduledTask -TaskName $v42TaskName
Export-ScheduledTask -TaskName $v42TaskName | Set-Content -LiteralPath (Join-Path $CampaignRoot 'WINDOWS_DETACHED_TASK.xml') -Encoding utf8
Get-ScheduledTask -TaskName $v42TaskName | Select-Object TaskName,State,Actions,Principal | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $CampaignRoot 'WINDOWS_TASK_REGISTRATION.json') -Encoding utf8
