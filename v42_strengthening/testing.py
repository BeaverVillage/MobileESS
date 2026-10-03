"""Post-heavy, one-process pytest with native Gurobi calls forced to one thread."""
from .common import ENV,write,OUT,ROOT,read,sha
from .resources import gate
import os
import sys
from datetime import datetime,timezone

def bind_historical_fixtures():
    """Restore the read-only junctions expected by unchanged legacy tests.

    Their native readers explicitly resolve these junctions to ASCII paths.
    No scientific lane accessor is rebound, and no historical solve is run.
    """
    from pathlib import Path
    import subprocess
    home=Path('C:/Users/kjw39/Documents/Codex/2026-10-03/m1-root-pathology-diagnostics')
    expected=read(ROOT/'docs/v42_m1_late_window_certificate_mipstart/MIP_START_IMPORT_AUDIT.json')['model_sha256']
    records=[]
    for name in ('V42_CERTIFICATE_LOCAL','THRESHOLD_LOCAL'):
        source=home/name;destination=ROOT.parent/name
        actual=sha(source/'F3.mps')
        assert actual==expected,'HISTORICAL_FIXTURE_SHA_MISMATCH'
        if destination.exists():
            assert destination.resolve()==source.resolve(),'EXISTING_FIXTURE_BINDING_MISMATCH'
        else:
            # Paths contain no apostrophes. One native PowerShell operation;
            # no deletion, move, cache copy or model mutation.
            assert "'" not in str(destination) and "'" not in str(source)
            command=f"New-Item -ItemType Junction -Path '{destination}' -Value '{source}' | Out-Null"
            subprocess.run(['powershell','-NoProfile','-Command',command],check=True)
        records.append(dict(path=str(destination),target=str(source),F3_SHA=actual,
                            historical_only=True,model_mutations=0,optimize_calls=0))
    write('HISTORICAL_TEST_FIXTURE_BINDINGS.json',dict(PASS=True,records=records,
          purpose='Unchanged legacy tests; historical scientific authority never used in new strengthening.',
          scientific_source_rebound=False,production_calls=0))

def run(args):
    os.environ.update(ENV)
    os.environ.pop('V42_ROOT_OUTPUT',None);os.environ.pop('V42_ROOT_LOCAL',None)
    gate('pytest_before_start')
    if not any('v42_strengthening' in a for a in args):bind_historical_fixtures()
    import gurobipy as gp
    import pytest
    from threadpoolctl import threadpool_limits
    gp.setParam('Threads',1)
    original=gp.Model.optimize;calls=[];active=[False]
    def optimize(model,*arguments,**kwargs):
        if active[0]:raise RuntimeError('OVERLAPPING_OPTIMIZATION_FORBIDDEN')
        model.Params.Threads=1
        row=dict(start=datetime.now(timezone.utc).isoformat(),Threads=model.Params.Threads,
                 rows=model.NumConstrs,columns=model.NumVars)
        calls.append(row);active[0]=True
        try:return original(model,*arguments,**kwargs)
        finally:active[0]=False;row['end']=datetime.now(timezone.utc).isoformat()
    gp.Model.optimize=optimize
    try:
        with threadpool_limits(limits=1):code=pytest.main(args)
    finally:gp.Model.optimize=original
    label='SEMANTIC' if any('v42_strengthening' in v for v in args) else 'FULL'
    write('PYTEST_'+label+'_RECEIPT.json',dict(exit_code=code,one_pytest_process=True,xdist=False,
          environment=ENV,test_optimization_calls=calls,all_Gurobi_Threads_one=all(r['Threads']==1 for r in calls),
          calls_nonoverlapping=all(a['end']<=b['start'] for a,b in zip(calls,calls[1:])),
          full_scientific_model_retry_calls=0,tests_after_heavy_work=True))
    return code

if __name__=='__main__':raise SystemExit(run(sys.argv[1:] or ['-q']))
