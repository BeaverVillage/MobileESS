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
    assert len(lines)==7 and '3/31' in text and '84.00%' in text and 'Gap  1.20%' in text
    for extra in ('node_count','pagefile','BestBd','MIPGap','PID','Threads','TimeLimit','155'):
        assert extra not in text


def test_readonly_monitor_and_output_identity_guard():
    source=(ROOT/'tools/v42/monitor_b1_may.ps1').read_text(encoding='utf-8-sig')
    for mutation in ('Set-Content','Out-File','Start-Process','Stop-Process','schtasks','Start-ScheduledTask','Register-ScheduledTask'):
        assert mutation not in source
    assert '$id.run_id -ne $Live.run_id' in source
    assert '$id.day -ne $day' in source and '$row.worker.PID -eq $Live.active.worker.PID' in source
    assert 'Resolve-Path -LiteralPath $Root' in source
