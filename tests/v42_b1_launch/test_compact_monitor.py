import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def test_compact_metrics_sources_missing_zero_and_p2():
    monitor=ROOT/'tools/v42/monitor_b1_may.ps1'
    script=f"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); . '{monitor}' -LibraryOnly; " + r'''
    $live=[pscustomobject]@{state='RUNNING';active=[pscustomobject]@{stage='A1'};progress=[pscustomobject]@{phase='rho';solver_status='OPTIMIZING';incumbent=.8723;gap=.0123}}
    $a=Get-B1Metrics $live $null $null $null
    $live.progress.incumbent=0;$live.progress.gap=0;$b=Get-B1Metrics $live $null $null $null
    $live.progress.phase='migration_count';$live.progress.incumbent=7;$live.progress.gap=.125
    $c=Get-B1Metrics $live $null ([pscustomobject]@{P1_rho=.85}) $null
    $d=Get-B1Metrics $live ([pscustomobject]@{passes=@([pscustomobject]@{component='rho';objective=.84})}) $null $null
    $live.active.stage='FRESH_AC';$e=Get-B1Metrics $live $null $null ([pscustomobject]@{summary=[pscustomobject]@{rho_max_AC=1.08}})
    $live.active.stage='A1';$live.state='WAIT_RESOURCE';$live.progress.phase='rho';$f=Get-B1Metrics $live $null $null $null
    $live.state='RUNNING';$live.progress.incumbent=$null;$live.progress.gap=$null;$g=Get-B1Metrics $live $null $null $null
    @($a,$b,$c,$d,$e,$f,$g)|ConvertTo-Json -Depth 10 -Compress
    '''
    p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],
                     capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0 and not p.stderr,p.stderr
    a,b,c,d,e,f,g=json.loads(p.stdout)
    assert a['Loading']==.8723 and a['LoadingText']=='87.23% (Planning)' and a['GapText']=='1.23%'
    assert b['LoadingText']=='0.00% (Planning)' and b['GapText']=='0.00%'
    assert c['Loading']==.85 and c['Gap']==.125 and d['Loading']==.84
    assert e['LoadingText']=='108.00% (Fresh AC)' and e['Gap'] is None
    assert f['Loading'] is None and f['Gap'] is None
    assert g['Loading'] is None and g['Gap'] is None


def test_compact_screen_contains_only_core_values():
    monitor=ROOT/'tools/v42/monitor_b1_may.ps1'
    script=f"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); . '{monitor}' -LibraryOnly; " + r'''
    $live=[pscustomobject]@{PASS_days=3;active=[pscustomobject]@{day='2025-05-04';stage='A1'};progress=[pscustomobject]@{phase='rho'}}
    $frame=[pscustomobject]@{State='RUNNING';Live=$live;View=[pscustomobject]@{Failed=0;Failures=@()};Resource=[pscustomobject]@{available_GiB=7.5;commit_percent=80};Liveness=[pscustomobject]@{State='RUNNING'}}
    $metrics=[pscustomobject]@{LoadingText='84.00% (Planning)';GapText='1.20%'}
    @(Get-CompactB1Lines $frame $metrics)|ConvertTo-Json -Compress
    '''
    p=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],
                     capture_output=True,text=True,encoding='utf-8')
    assert p.returncode==0 and not p.stderr,p.stderr
    lines=json.loads(p.stdout);text='\n'.join(lines)
    assert len(lines)==9 and '3/31' in text and '9.7%' in text and '84.00%' in text and 'Gap  1.20%' in text
    for extra in ('node_count','pagefile','BestBd','MIPGap','PID','Threads','TimeLimit','155'):
        assert extra not in text


def test_readonly_monitor_and_output_identity_guard():
    source=(ROOT/'tools/v42/monitor_b1_may.ps1').read_text(encoding='utf-8-sig')
    for mutation in ('Set-Content','Out-File','Start-Process','Stop-Process','schtasks','Start-ScheduledTask','Register-ScheduledTask'):
        assert mutation not in source
    assert '$id.run_id -ne $Live.run_id' in source
    assert '$id.day -ne $day' in source and '$row.worker.PID -eq $Live.active.worker.PID' in source
    assert 'Resolve-Path -LiteralPath $Root' in source


def test_frame_tracks_coordinator_replacement_and_rejects_stale_identity():
    monitor=ROOT/'tools/v42/monitor_b1_may.ps1'
    script=f"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); . '{monitor}' -LibraryOnly; " + r'''
    $Root='C:\test B1'
    $created=[DateTimeOffset]::UtcNow.AddMinutes(-1)
    $process=[pscustomobject]@{PID=123;creation_time=$created.ToUnixTimeMilliseconds()/1000.0;command=@('python.exe','-m','v42_b1_production','run','--root',$Root)}
    $heartbeat=[pscustomobject]@{process=$process;timestamp_UTC=[DateTime]::UtcNow.ToString('o')}
    $live=[pscustomobject]@{state='RUNNING';timestamp_UTC=$heartbeat.timestamp_UTC;day_rows=@()}
    $actual=[pscustomobject]@{CreationDate=$created.UtcDateTime;CommandLine=($process.command -join ' ')}
    $a=Get-B1Frame $live $heartbeat $null @{} -ProcessInfo $actual
    $process.command=@('python.exe','C:\ops\run_b1_without_memory_guard.py','--root',$Root)
    $actual.CommandLine=$process.command -join ' '
    $b=Get-B1Frame $live $heartbeat $null @{} -ProcessInfo $actual
    $actual.CommandLine='python.exe foreign.py --root C:\test B1'
    $c=Get-B1Frame $live $heartbeat $null @{} -ProcessInfo $actual
    $actual.CommandLine=$process.command -join ' ';$actual.CreationDate=$created.UtcDateTime.AddMinutes(1)
    $d=Get-B1Frame $live $heartbeat $null @{} -ProcessInfo $actual
    $actual.CreationDate=$created.UtcDateTime;$heartbeat.timestamp_UTC=[DateTime]::UtcNow.AddSeconds(-60).ToString('o')
    $e=Get-B1Frame $live $heartbeat $null @{} -ProcessInfo $actual
    $heartbeat.timestamp_UTC=[DateTime]::UtcNow.ToString('o');$process.command=@('python.exe','foreign.py')
    $actual.CommandLine=$process.command -join ' '
    $f=Get-B1Frame $live $heartbeat $null @{} -ProcessInfo $actual
    @($a,$b,$c,$d,$e,$f)|ForEach-Object { $_.Liveness }|ConvertTo-Json -Depth 5 -Compress
    '''
    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],
                          capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0 and not result.stderr,result.stderr
    rows=json.loads(result.stdout)
    assert [row['State'] for row in rows]==['RUNNING','RUNNING','DEAD','DEAD','STALE','DEAD']
    assert rows[1]['IdentityMatches'] is True and rows[4]['Orchestrator']=='ALIVE'


def test_progress_uses_observed_work_and_keeps_solver_completion_unknown():
    monitor=ROOT/'tools/v42/monitor_b1_may.ps1'
    script=f"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); . '{monitor}' -LibraryOnly; " + r'''
    $live=[pscustomobject]@{state='RUNNING';PASS_days=1;day_rows=@([pscustomobject]@{status='PASS'},[pscustomobject]@{status='FAIL'},[pscustomobject]@{status='RUNNING'});active=[pscustomobject]@{stage='A1'};progress=[pscustomobject]@{phase='MODEL_BUILD';classes_complete=16;classes_required=55}}
    $a=Get-B1Progress $live
    $live.progress=[pscustomobject]@{phase='MODEL_BUILD';units_complete=641;units_required=644}
    $b=Get-B1Progress $live
    $live.progress=[pscustomobject]@{phase='rho';solver_status='OPTIMIZING';elapsed=900;gap=.01}
    $c=Get-B1Progress $live
    $live.active.stage='FRESH_AC';$live.progress=[pscustomobject]@{OpenDSS_slot=24}
    $d=Get-B1Progress $live
    @($a,$b,$c,$d)|ConvertTo-Json -Compress
    '''
    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],
                          capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0 and not result.stderr,result.stderr
    a,b,c,d=json.loads(result.stdout)
    assert a['Processed']==2 and abs(a['Percent']-200/31)<1e-9
    assert abs(a['StagePercent']-1600/55)<1e-9 and '16/55' in a['CurrentText']
    assert '641/644' in b['CurrentText']
    assert c['StagePercent'] is None and '1/4' in c['CurrentText'] and '900' in c['CurrentText']
    assert d['StagePercent']==25 and '24/96' in d['CurrentText']


def test_attempt_summary_distinguishes_memory_interruptions_from_infeasible(tmp_path):
    monitor=ROOT/'tools/v42/monitor_b1_may.ps1'
    parent=tmp_path/'a'/'20250501'/'0'
    for attempt in range(1,8):
        folder=parent/str(attempt)
        folder.mkdir(parents=True)
        if attempt<=5:
            (folder/'CANCEL.json').write_text(json.dumps({'reason':'RESOURCE_HARD_GUARD'}),encoding='utf-8')
        if attempt==6:
            (folder/'o').mkdir()
            (folder/'o'/'A1_SOLVE_RESULT.json').write_text(json.dumps({'passes':[{'status':3}]}),encoding='utf-8')
    script=f"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); . '{monitor}' -LibraryOnly; $Root='{tmp_path}'; "
    script+=r'''
    $live=[pscustomobject]@{run_id='run';active=[pscustomobject]@{day='2025-05-01';stage='A1'}}
    $checkpoint=[pscustomobject]@{run_id='run';stages=[pscustomobject]@{'2025-05-01/A1'=[pscustomobject]@{attempts=7;request=(Join-Path $Root 'a/20250501/0/7/request.json')}}}
    $a=Get-B1AttemptSummary $live $checkpoint
    $checkpoint.run_id='foreign';$b=Get-B1AttemptSummary $live $checkpoint
    [pscustomobject]@{Good=$a;Foreign=$b}|ConvertTo-Json -Compress
    '''
    result=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-Command',script],
                          capture_output=True,text=True,encoding='utf-8')
    assert result.returncode==0 and not result.stderr,result.stderr
    value=json.loads(result.stdout)
    assert value['Good']=={'Attempt':7,'ResourceStops':5,'Infeasible':1}
    assert value['Foreign'] is None
