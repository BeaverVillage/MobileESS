"""Real original AIDC Native0 builder with Source-YY electrical IO.

Complete source Job graphs and equations are reused. Neither Golden414 nor
an accepted numerical point is an input. The model is built, never optimized.
"""
import ast, inspect, pickle, types, textwrap, gc
from contextlib import contextmanager
from types import SimpleNamespace
from dataclasses import asdict
import numpy as np
import scipy.sparse as sp
from .stage_common import *
from .stage_a_grid import PF, prepare_grid
from .prestart_native import native_zero
from .prestart_acceptance import source_domain,certify

def power_bounds(bundle):
    from v42_temporal.native import load_power
    certificate,power,idle,swing=load_power(bundle);sites=tuple(bundle['capacities'])
    assert sites==tuple(f'AIDC{i:02d}' for i in range(1,13)) and sum(bundle['capacities'].values())==780
    bounds=np.empty((96,12,2))
    for t in range(96):
        for j,s in enumerate(sites):
            p=power[s,t];v=[p.slope*(idle*bundle['capacities'][s]+swing*g)+p.intercept_kw for g in (0,bundle['capacities'][s])]
            bounds[t,j]=min(v),max(v)
    return bounds,(certificate,power,idle,swing)

def fresh_data(bundle,windows,folder):
    from v42_root.data import prepare
    jobs,bounds,seconds,r,raw=source_domain(bundle,windows)
    ns=dict(prepare.__globals__,LOCAL=folder,load_native=lambda:(bundle,jobs,bounds,seconds,r,raw),
        dump=lambda name,value:(folder/name).write_text(json.dumps(value,default=str),encoding='utf-8'))
    data=types.FunctionType(prepare.__code__,ns,argdefs=prepare.__defaults__)()
    assert set(data[1])==set(jobs) and all(data[2][u].allowed_starts==bounds[u].allowed_starts for u in jobs)
    # Independent FULL reference acceptance, before touching any optimizer.
    from v42_job_capability import Option
    selected={u:asdict(Option(j.reference_start,j.reference_site,((j.reference_site,j.reference_start,j.reference_start+j.service_slots),))) for u,j in jobs.items()}
    cert=certify(selected,bundle,windows,identity={},expected_identity={});assert cert['PASS']
    return data,cert

def planning_function(folder,power_pack,mess,stage):
    from v42_boundary import model as boundary
    from .static_coefficients import CONTROLS
    # Timing, CC4 forecast, runtime reserve, P1/P2 expressions and C1 formula
    # remain literal source code. Only physical IO/control representation is
    # adapted: independent Q axis is the exact source PF multiple of P.
    # bind() can already have installed a date-routed function. Its code was
    # compiled against the original filename, so inspect.getsource would read
    # an unrelated first line on the second bind. Read the literal original
    # definition, retaining its original module namespace.
    source=Path(boundary.__file__).read_text(encoding='utf-8')
    definition=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='planning_grid')
    body=ast.get_source_segment(source,definition)
    old="else:row.append(0.) # Canonical A1 initial MESS P/Q=0; M1 follows only accepted A1."
    assert body.count(old)==1
    body=body.replace(old,"elif name.startswith('aidc_load_kvar'):row.append(row[len(row)-12]*_PF)\n            elif name.startswith('mess_p_kw'):row.append(_mess[t,_services.index(site)])\n            else:row.append(_mess[t,24+_services.index(site)])")
    # The Stage.A1 guard is a source label. A2's physical constants come only
    # from its SHA-verified current M1 parameter, not from mutable globals.
    body=body.replace('stage=Stage.A1','stage=_stage').replace('stage==Stage.A1','stage==_stage')
    coeff=tuple(SimpleNamespace(control_names=CONTROLS,transformer_current_authority_sha256=digest(read(OUT/'SOURCE_YY_GRID_AXES.json')['transformer_current'])) for _ in range(96))
    ns=dict(vars(boundary),native_coefficients=lambda cert:coeff,load_power=lambda b:power_pack,
        _PF=PF,_mess=mess,_services=[f'{s}{i:02d}' for s in ('IDC','STA') for i in range(1,13)],_stage=stage,
        add_grid=lambda m,c,x,a:append_grid(m,x,folder),OLD=folder.parent)
    exec(compile(body,boundary.__file__,'exec'),ns)
    return ns['planning_grid']

def append_grid(model,controls,folder):
    import gurobipy as gp
    from .static_native import native_rows_exact
    start=time.perf_counter();rho=model.addVar(lb=0,ub=1,name='rho_max');summary=[]
    for t in range(96):
        guard(start);path=folder/f'{t:02d}'
        B=sp.load_npz(path/'SELECTED.npz')
        with np.load(path/'SELECTED_DOMAIN.npz') as z:d={k:z[k] for k in z.files}
        with np.load(RUN/'coefficients'/f'{t:02d}.npz') as z:anchor=z['anchor'][:12]
        variables=[]
        for j in range(12):
            v=model.addVar(lb=d['lower'][j],ub=d['upper'][j],name=str(d['names'][j]));variables.append(v)
            model.addConstr(v==controls[t][j]-float(anchor[j]),name=f'original_C1_to_IEEE8500[{t},{j}]')
        variables.append(rho)
        aux=model.addMVar(B.shape[1]-13,lb=d['lower'][13:],ub=d['upper'][13:],name=[f'Agrid_{t}_{n}' for n in d['names'][13:]])
        variables.extend(aux.tolist());model.update()
        native=model.addMConstr(B,variables,d['sense'],d['rhs'],name=f'variable_AIDC_full_grid_{t:02d}');model.update()
        # Translate actual Native global indices for exhaustive coefficient
        # readback; no matrix of prior slots is duplicated.
        ids=np.array([v.index for v in variables]);C=B.tocoo()
        C=sp.csr_matrix((C.data,(C.row,ids[C.col])),shape=(B.shape[0],model.NumVars))
        native_rows_exact(model,native,C,d['rhs'],d['sense'],start)
        summary.append(dict(slot=t,rows=B.shape[0],nonzeros=B.nnz,variables=B.shape[1],all_Native_rows_exact=True))
        if t%8==0:print('AIDC NATIVE GRID',t,model.NumConstrs,flush=True)
    model._v2_add_grid=summary
    return rho

def prepare(tag='A1',mess=None):
    assert tag in ('A1','A2')
    filename='A1_VARIABLE_AIDC_FULL_NATIVE0.json' if tag=='A1' else 'A2_FIXED_M1_FULL_NATIVE0.json'
    with measured(filename) as (report,start),native_zero() as denied:
        folder=WORK/tag;folder.mkdir(parents=True,exist_ok=True)
        row=day_inputs();bundle=read(row['files']['native']['path']);windows=read(row['files']['windows']['path'])
        if mess is None:
            if tag!='A1':raise ValueError('A2_CURRENT_FULL_M1_WITNESS_REQUIRED')
            mess=np.zeros((96,48))
        assert mess.shape==(96,48)
        bounds,power=power_bounds(bundle)
        if not (folder/'grid/RECEIPT.json').exists():prepare_grid(tag,bounds,mess)
        grid=read(folder/'grid/RECEIPT.json')
        assert grid['MESS_parameter_sha']==digest(mess.tolist()) and grid['domain_P_bounds']==bounds.tolist()
        report.update(grid=grid,Native0_monolithic_PASS=False,complete_Source_Job_domain_PASS=False)
        data,reference=fresh_data(bundle,windows,folder)
        report.update(complete_Source_Job_domain_PASS=True,reference_FULL_acceptance=reference,
            jobs=len(data[1]),classes=len(data[7]['classes']),all_original_full_graphs=True)
        from v42_root.native import build
        from v42_native.voltage import Stage
        stage=Stage.A1 if tag=='A1' else Stage.A2
        planning=planning_function(folder/'grid',power,mess,stage)
        # Source timing kernel is input IO, not a new prediction/policy.
        from shutil import copyfile
        copyfile(ROOT/'docs/v42_final_integration/CC4_EXECUTION_LAG_KERNEL.csv',folder/'CC4_EXECUTION_LAG_KERNEL.csv')
        (folder/'MAY01_FINAL_NATIVE_INPUT_BUNDLE.json').write_text(json.dumps(bundle),encoding='utf-8')
        fn=types.FunctionType(build.__code__,dict(build.__globals__,grid=lambda m,b,k,r,**kw:planning(m,b,k,r,stage=stage),
            dump=lambda n,v:(folder/n).write_text(json.dumps(v,default=str),encoding='utf-8')),argdefs=build.__defaults__)
        class Context:
            def __init__(self):self.folder=folder
            def check(self):guard(start)
            def progress(self,value):
                guard(start)
                if value.get('units_complete',value.get('classes_complete',0))%20==0:print('ORIGINAL A FULL',tag,value,flush=True)
        model=None
        try:
            model,units,levels,controls,bindings=fn(Context(),data,'F2-CRA')
            model.setObjective(levels[0][1]);model.update();guard(start)
            from v42_pr134_sc.snapshot import capture
            descriptor=capture(model,units,levels,controls,bindings,folder/'SCIENTIFIC_INTERFACES.pkl.gz')
            report.update(Native0_monolithic_PASS=True,model=dict(variables=model.NumVars,binary=model.NumBinVars,
                integer=model.NumIntVars,rows=model.NumConstrs,nonzeros=int(model.DNumNZs)),
                original_C1_all_jobs_connected=True,grid_Native_readback=model._v2_add_grid,
                objectives=[n for n,e in levels],source_native=record(ROOT/'v42_root/native.py'),
                interfaces=record(folder/'SCIENTIFIC_INTERFACES.pkl.gz'),
                independent_complete_native_matrix_validator_PASS=False,
                source_A_stage_LB_UB_acceptance_handler_bound=False,denied_attempts=denied,
                PASS=False,reason='Native0 construction is distinct from independent full projection/acceptance and production stage binding')
            return report
        finally:
            if model is not None:model.dispose()

if __name__=='__main__':
    import sys
    prepare(sys.argv[1] if len(sys.argv)>1 else 'A1')
