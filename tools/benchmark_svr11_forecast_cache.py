"""Exact real-DSS prefix/response comparison for a pure Forecast P/Q cache."""
from pathlib import Path
import sys,ast,copy,time,json,shutil
from unittest.mock import patch
import numpy as np
SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
from v42_pr134_b1.common import read,record,atomic,digest,now
from v42_common_campaign.authority import source_files
from v42_svr11.authority import scope
from v42_svr11 import model
from v42_voltage_control.timecontrol import CommonClock,seconds

OLD=Path(r'D:\v42_svr11_may_20261011_09');ROOT=Path(r'D:\v42_svr11_may_20261011_10')

def prepare_manifest():
    folder=ROOT/'model_benchmarks';folder.mkdir(parents=True,exist_ok=True)
    original=read(OLD/'CAMPAIGN_MANIFEST.json');m=copy.deepcopy(original);sources=source_files()
    for key in ('predecessor_drain_contract','equipment_change_contract','model_checkpoint_reuse_contract'):
        m.pop(key,None)
    for key in ('scenario','thermal','hardware'):
        path=folder/Path(m[key]['path']).name
        if key=='hardware':
            h=read(m[key]['path']);h['source_SHA']=digest(sources);atomic(path,h)
        else:shutil.copyfile(m[key]['path'],path)
        m[key]=record(path)
    m.update(root=str(ROOT),code_root=str(SOURCE),execution_sources=sources,execution_SHA=digest(sources),
        benchmark_only=True,official_campaign_worker_permitted=False)
    path=folder/'BENCHMARK_ONLY_MANIFEST.json';atomic(path,m);return path,m

def probe_function(path,slot):
    # Execute the exact production prefix/probe body, ending immediately before
    # the 96-slot output loop. Only this isolated benchmark function is compiled.
    tree=ast.parse(path.read_text(encoding='utf8'));fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='generate')
    boundary=next(i for i,n in enumerate(fn.body) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='t')
    fn.body=fn.body[:boundary]+ast.parse(f'''samples=[probe({slot})]
for j in range(60):
    samples.extend([probe({slot},j,1),probe({slot},j,-1)])
return dict(samples=samples,anchor=anchor[{slot}].copy(),controls=controls,independent_compiles=count,physical_solves=solves)
''').body
    code=ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[]));namespace=dict(vars(model))
    exec(compile(code,str(path),'exec'),namespace);return namespace['generate']

def coefficients(v):
    from dayahead import run_v16_3_voltage_candidate as original
    base=v['samples'][0];mat=[np.empty((60,len(x))) for x in base]
    for j,control in enumerate(v['controls']):
        d=original._perturbation(control,v['anchor'][j]);plus,minus=v['samples'][1+2*j:3+2*j]
        for k in range(4):mat[k][j]=(plus[k]-minus[k])/(2*d)
    out={}
    for k,f in enumerate(('voltage','current','flow_p','flow_q')):
        out[f+'_constant']=base[k]-v['anchor']@mat[k];out[f+'_matrix']=mat[k] if k<2 else mat[k].T
    return out

def same_bytes(a,b):
    return a.dtype==b.dtype and a.shape==b.shape and a.tobytes(order='C')==b.tobytes(order='C')

def setter_equivalence(day,manifest,native=None):
    from v42_voltage_control.bindings import original_bindings
    from v42_regcontrol.runner import background
    authority,*_=original_bindings()
    from dayahead.v28r2 import opendss_mapping as mapping
    if native is None:
        engine,adapter,_=authority.compile_verified()
        try:native=authority.source()['NativeAllocation'].from_adapter(adapter)
        finally:model.retire_completed_probe(engine)
        del engine;model.flush_completed_probes()
    provenance=read(OLD/'raw'/day/'SOURCE_PROVENANCE.json');ref=provenance['daily_sources']['aemo_forecast.json']
    forecast=read(ref['path']);bg=background(forecast['timestamps_96'],forecast['demand_mw_96'],forecast['pv_mw_96'])
    totals=model._forecast_native_totals(native,bg);calls=[]
    def capture(engine,name,p,q):calls.append((name,float(p).hex(),float(q).hex()))
    for t in range(96):
        with patch.object(mapping,'_set_load',capture):native.apply(None,bg,t)
        original=calls[:];calls.clear()
        with patch.object(mapping,'_set_load',capture):model._apply_forecast_native(None,native,totals,t)
        assert calls==original,('FORECAST_SETTER_BYTES_OR_ORDER_DIFFERENT',day,t)
        calls.clear()
    # Original allocation error and conservation checks remain authoritative.
    invalid=copy.deepcopy(bg);first=next(iter(invalid.gross_p_kw_96[0]));invalid.gross_p_kw_96[0][first]=-1
    try:model._forecast_native_totals(native,invalid)
    except Exception as error:
        assert type(error).__name__=='AllocationError'
    else:raise AssertionError('ORIGINAL_INVALID_ALLOCATION_CHECK_SKIPPED')
    return dict(PASS=True,day=day,slots=96,load_count=len(native.loads),
        setter_order_and_float_hex_exact=True,original_invalid_allocation_rejected=True,forecast=record(ref['path']))

def run(day,slot,tag):
    manifest,m=prepare_manifest();oldcode=Path(read(OLD/'CAMPAIGN_MANIFEST.json')['code_root'])/'v42_svr11/model.py'
    folder=ROOT/'model_benchmarks'/tag;assert not folder.exists();folder.mkdir()
    results={};timings={};traces={}
    with scope(manifest):
        setters=setter_equivalence(day,m)
        for label,path in (('original',oldcode),('cached',SOURCE/'v42_svr11/model.py')):
            output=folder/label;(output/'FORECAST_ANCHOR').mkdir(parents=True)
            for name in ('B0_NEW_PLANNING_GENERATION.json','PLANNING_PHYSICAL.npz'):
                shutil.copyfile(OLD/'models'/day/'FORECAST_ANCHOR'/name,output/'FORECAST_ANCHOR'/name)
            trace=[]
            class TraceClock(CommonClock):
                def settle_slot(self,engine,t,**kw):
                    native_solve=engine.Solution.SolveSnap
                    def solve():trace.append(seconds(engine));return native_solve()
                    return super().settle_slot(engine,t,solve=solve,**kw)
            started=time.perf_counter()
            with patch('v42_voltage_control.timecontrol.CommonClock',TraceClock):
                results[label]=probe_function(path,slot)(day,OLD/'inputs'/'B2'/day,output,lambda v:None)
            timings[label]=time.perf_counter()-started;traces[label]=trace
            model.flush_completed_probes()
    a,b=results['original'],results['cached']
    assert a['independent_compiles']==b['independent_compiles']==121 and a['physical_solves']==b['physical_solves']
    assert traces['original']==traces['cached']
    assert all(same_bytes(x,y) for left,right in zip(a['samples'],b['samples']) for x,y in zip(left,right))
    ca,cb=coefficients(a),coefficients(b)
    with np.load(read(OLD/'models'/day/f'SLOT_{slot:02d}.json')['data']['path']) as z:
        exact={f:same_bytes(ca[f],cb[f]) and same_bytes(cb[f],z[f]) for f in ca}
    assert all(exact.values())
    artifacts=[]
    for label,v in results.items():
        path=folder/(label+'_ARRAYS.npz')
        np.savez_compressed(path,**{f'raw_response_{k}':np.array([row[k] for row in v['samples']]) for k in range(4)},**coefficients(v))
        artifacts.append(record(path))
    out=dict(PASS=True,day=day,slot=slot,timings_seconds=timings,speedup=timings['original']/timings['cached'],
        original_and_cached_all121_responses_bitwise_equal=True,fields=exact,
        independent_compiles=121,physical_solves=a['physical_solves'],all_solve_timestamps_identical=True,
        setter_equivalence=setters,source_before=record(oldcode),source_after=record(SOURCE/'v42_svr11/model.py'),
        reference_checkpoint=record(OLD/'models'/day/f'SLOT_{slot:02d}.json'),
        comparison_includes_dtype_shape_all_bytes_and_signed_zero=True,response_artifacts=artifacts,
        Actual_inputs_read=0,Native_optimizer_calls=0,campaign_workers_modified=0,UTC=now())
    atomic(folder/'EQUIVALENCE.json',out);print(json.dumps(out))

def all_forecast_setters():
    from v42_svr11 import DAYS
    from v42_voltage_control.bindings import original_bindings
    manifest,m=prepare_manifest()
    with scope(manifest):
        authority,*_=original_bindings();engine,adapter,_=authority.compile_verified()
        try:native=authority.source()['NativeAllocation'].from_adapter(adapter)
        finally:model.retire_completed_probe(engine)
        del engine;model.flush_completed_probes()
        axis=[setter_equivalence(day,m,native) for day in DAYS]
    receipt=dict(PASS=all(v['PASS'] for v in axis),days=31,slots=31*96,
        axis=axis,DSS_compiles=1,AC_solve_calls=0,Native_optimizer_calls=0,
        Actual_inputs_read=0,monthly_AC_only_canary=False,
        source_before=record(Path(read(OLD/'CAMPAIGN_MANIFEST.json')['code_root'])/'v42_svr11/model.py'),
        source_after=record(SOURCE/'v42_svr11/model.py'),UTC=now())
    atomic(ROOT/'model_benchmarks'/'ALL_FORECAST_INPUT_EQUIVALENCE.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='axis'}))

if __name__=='__main__':
    if sys.argv[1]=='all-setters':all_forecast_setters()
    else:run(sys.argv[1],int(sys.argv[2]),sys.argv[3])
