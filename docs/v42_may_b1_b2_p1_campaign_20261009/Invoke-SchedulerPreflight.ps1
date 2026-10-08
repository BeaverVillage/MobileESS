param(
    [string]$OutputRoot = 'D:\MobileESS_v42\runtime\v42_may_b1_b2_p1_campaign\scheduler_probe'
)
$ErrorActionPreference = 'Stop'
$resolvedRoot = [IO.Path]::GetFullPath($OutputRoot)
if (-not $resolvedRoot.StartsWith('D:\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'D_DRIVE_OUTPUT_REQUIRED'
}
New-Item -ItemType Directory -Force -Path $resolvedRoot | Out-Null
$name = 'MobileESS_V42_B1B2_P1_S4U_Probe_' + [Guid]::NewGuid().ToString('N').Substring(0,12)
$user = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-ScheduledTaskPrincipal -UserId $user.User.Value -LogonType S4U -RunLevel Limited
$action = New-ScheduledTaskAction -Execute 'C:\Users\kjw39\AppData\Local\Programs\Python\Python311\python.exe' -Argument '-B -c "pass"' -WorkingDirectory 'D:\MobileESS_v42'
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$report = [ordered]@{
    task = $name; user = $user.User.Value; logon_type = 'S4U'
    utc = [DateTime]::UtcNow.ToString('o'); PASS = $false; registered = $false
    started = $false; Native_optimize_calls = 0; campaign_launch = $false
    scope = 'Registration eligibility probe only; does not start or resume a campaign'
    is_administrator = ([Security.Principal.WindowsPrincipal]$user).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
try {
    Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Settings $settings | Out-Null
    $report.registered = $true
    $xml = Export-ScheduledTask -TaskName $name
    $xml | Set-Content -LiteralPath (Join-Path $resolvedRoot ($name + '.xml')) -Encoding utf8
    $report.PASS = ([xml]$xml).Task.Principals.Principal.LogonType -eq 'S4U'
} catch {
    $report.error = $_.Exception.Message
    $report.fully_qualified_error_id = $_.FullyQualifiedErrorId
    $report.exception_type = $_.Exception.GetType().FullName
} finally {
    if ($report.registered) {
        try {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            $report.cleaned = $true
        } catch {
            $report.PASS = $false
            $report.cleanup_error = $_.Exception.Message
            $report.cleaned = $false
        }
    }
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $resolvedRoot ($name + '.json')) -Encoding utf8
    $report | ConvertTo-Json -Depth 8
}
if (-not $report.PASS) { exit 1 }
