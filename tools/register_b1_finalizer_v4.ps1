$ErrorActionPreference='Stop'
$v42Source='D:\v42_b1_only_source_20261012'
$v42Name='MobileESS_V42_B1_Only_May2025_20261012_V4_FinalReport'
$v42Action=New-ScheduledTaskAction -Execute 'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\pythonw.exe' -Argument ('-B -X utf8 '+$v42Source+'\tools\finalize_b1_only_v4.py') -WorkingDirectory $v42Source
$v42Trigger=New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$v42Settings=New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$v42Principal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
if(Get-ScheduledTask -TaskName $v42Name -ErrorAction SilentlyContinue){throw 'B1_FINALIZER_ALREADY_REGISTERED'}
Register-ScheduledTask -TaskName $v42Name -Action $v42Action -Trigger $v42Trigger -Settings $v42Settings -Principal $v42Principal | Out-Null
Start-ScheduledTask -TaskName $v42Name
