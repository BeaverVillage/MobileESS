param([int]$RunnerPid, [string]$OutputPath)
$runner = Get-Process -Id $RunnerPid -ErrorAction Stop
$command = (Get-CimInstance Win32_Process -Filter "ProcessId = $RunnerPid").CommandLine
if ($command -notmatch 'tools/run_v42_release_actual.py') { throw 'RC01_OWN_RUNNER_IDENTITY_MISMATCH' }
$started = $runner.StartTime.ToUniversalTime()
$peakRss = 0L
$sampledPrivate = 0L
$peakPaged = 0L
$samples = 0
while (-not $runner.HasExited) {
    try {
        $runner.Refresh()
        $peakRss = [Math]::Max($peakRss, $runner.PeakWorkingSet64)
        $sampledPrivate = [Math]::Max($sampledPrivate, $runner.PrivateMemorySize64)
        $peakPaged = [Math]::Max($peakPaged, $runner.PeakPagedMemorySize64)
        $samples++
    } catch { break }
    Start-Sleep -Milliseconds 1000
}
$finished = [DateTime]::UtcNow
$receipt = [ordered]@{
    schema = 'RC01_OWN_RUNNER_RESOURCE_OBSERVATION_V1'
    process_id = $RunnerPid
    command_line = $command
    process_start_utc = $started.ToString('o')
    observation_finish_utc = $finished.ToString('o')
    whole_process_wall_seconds = ($finished - $started).TotalSeconds
    OS_reported_peak_RSS_bytes = $peakRss
    OS_reported_peak_paged_bytes = $peakPaged
    sampled_peak_private_usage_bytes = $sampledPrivate
    private_usage_scope = '1_SECOND_SAMPLING_LOWER_BOUND_NOT_OS_PEAK_PRIVATE_COUNTER'
    RSS_scope = 'OS_PROCESS_PEAK_COUNTER_INCLUDES_TIME_BEFORE_MONITOR_START'
    sampling_count = $samples
    Native_calls_added = 0
}
$receipt | ConvertTo-Json | Set-Content -LiteralPath $OutputPath -Encoding UTF8
