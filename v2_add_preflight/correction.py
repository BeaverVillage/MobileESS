"""Append-only PR236 correction evidence. No Native optimization or worker imports.

Original phase2 results are read-only. TIME uses the original r043 event loop,
with exactly the original 96->120 chronological-axis extension for Actual.
"""
from pathlib import Path
from collections import defaultdict, deque
import ast
import csv
import json
import math
import subprocess
import sys
import time
from datetime import date, datetime, timezone, timedelta
import numpy as np
import psutil
from .audit import DOC, ROOT, sha, read, snapshot
from .physical import Physical, RUNTIME

OUT=DOC/'correction'
RUN=RUNTIME/'correction'
BASE='e880a07b866577e79062b1081edca776c3cadc92'
EXT=[1.75,1.85,1.90,1.95,2.,2.05,2.10]

def put(name,value):
    p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def csvout(name,rows):
    assert rows,name
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with (OUT/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def priority():
    p=psutil.Process();p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    cores=[i for i in p.cpu_affinity() if i>=12]
    if cores:p.cpu_affinity(cores[:1])
    return dict(pid=p.pid,affinity=p.cpu_affinity(),priority=p.nice())

def independent_orientation(e):
    # Independent implementation: Dijkstra unit distances, direct live bus data.
    # Does not read objective_included / legacy_parent_objective_included flags.
    import heapq
    graph=defaultdict(set)
    for r in e.inventory['lines']+e.inventory['transformers']:
        if not r['enabled']:continue
        buses=[b.split('.')[0].lower() for b in r['buses']]
        for b in buses[1:]:
            graph[buses[0]].add(b);graph[b].add(buses[0])
    for name in e.d.Reactors.AllNames():
        e.d.Reactors.Name(name)
        if not e.d.CktElement.Enabled():continue
        a,b=[v.split('.')[0].lower() for v in e.d.CktElement.BusNames()]
        graph[a].add(b);graph[b].add(a)
    dist={};todo=[(0,'sourcebus')]
    while todo:
        n,b=heapq.heappop(todo)
        if b in dist:continue
        dist[b]=n
        for c in graph[b]:
            if c not in dist:heapq.heappush(todo,(n+1,c))
    records=[]
    for r in e.inventory['lines']:
        a,b=[v.split('.')[0].lower() for v in r['buses']]
        da,db=dist.get(a),dist.get(b)
        if r['enabled']:assert da is not None and db is not None
        terminal=2 if da is not None and db is not None and db<da else 1
        assert terminal==r['parent_terminal']
        records.append(dict(element=r['element'],parent_terminal=terminal,parent_bus=(a,b)[terminal-1],
            bus1=a,bus2=b,depth1=da,depth2=db,enabled=r['enabled'],normal_amps=r['normal_amps'],
            group=r['group'],orientation='SHORTEST_SOURCE_DISTANCE' if da!=db else 'DECLARED_BUS1_TIE'))
    return records

def masks(axes,orientation):
    parent={r['element']:r for r in orientation}
    canonical=np.array([r['enabled'] and r['node']>0 and r['terminal']==parent[r['element']]['parent_terminal'] for r in axes])
    security=np.array([r['node']>0 for r in axes])
    mv=canonical & np.array([r['group']=='Primary' for r in axes])
    return canonical,security,mv,canonical & ~mv

def init():
    OUT.mkdir(exist_ok=True);RUN.mkdir(exist_ok=True)
    path=OUT/'PRESERVATION_BASELINE.json'
    if path.exists():return
    own=priority()
    # Capture every tracked old evidence byte, plus every old runtime receipt/data.
    tracked=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE],cwd=ROOT,text=True).splitlines()
    tracked=[p for p in tracked if p.startswith(('docs/v2_add/','v2_add_preflight/'))]
    files={p:sha((ROOT/p).read_bytes()) for p in tracked}
    runtime={str(p):sha(p.read_bytes()) for p in sorted((RUNTIME/'phase2').rglob('*')) if p.is_file() and p.suffix in ('.npz','.json')}
    put('PRESERVATION_BASELINE.json',dict(PR236_HEAD=BASE,tracked_sha256=files,runtime_sha256=runtime,own_process=own))
    directive=Path('C:/Users/kjw39/.codex/attachments/1f5193a5-aae4-487b-9161-9b1e3ca0d067/붙여넣은 텍스트.txt')
    (OUT/'TASK_DIRECTIVE_KO.md').write_bytes(directive.read_bytes())
    put('NUMERICAL_TOLERANCES.json',dict(serialization='np.savez_compressed preserves IEEE754 float64 bits; JSON Python roundtrip preserves float64',
        same_saved_array_max_abs_tolerance=1e-12,fresh_rho_abs_tolerance=1e-9,AC_balance_kw_kvar=1e-4,
        voltage_pu_tolerance=1e-8,thermal_ratio_tolerance=1e-8,SOC_kwh=1e-8,recorded_before_recalculation=True))
    print('PRESERVED',len(files),len(runtime),flush=True)

def objective():
    init();e=Physical('CORRECTION_ORIENTATION_INVENTORY')
    orientation=independent_orientation(e);put('INDEPENDENT_PARENT_ORIENTATION.json',orientation)
    ratings={v['element']:v['normal_amps'] for v in orientation}
    rows=[];slots=[];top=[]
    receipts=read(DOC/'B0_AC_ARCHIVE_RECEIPTS.json')+read(DOC/'CONTROL_PILOT_ARCHIVE_RECEIPTS.json')
    for receipt in receipts:
        folder=Path(receipt['archive_path']).parent
        axis=read(folder/'AXES.json')['line'] if (folder/'AXES.json').exists() else e.line_axes
        a=np.load(folder/'AC_FULL.npz')['line_rho'];assert a.shape[1]==len(axis)
        c,s,m,l=masks(axis,orientation)
        assert all(r['normal_amps']==ratings[r['element']] for r in axis)
        # Check legacy flags separately after mask reconstruction, never use them as authority.
        if 'legacy_parent_objective_included' in axis[0]:
            assert np.array_equal(c,[v['legacy_parent_objective_included'] for v in axis])
        offset=24 if receipt['role']=='ACTUAL' else 0
        old=read(folder/'ROWS.json');assert np.max(abs(np.max(a[:,s],axis=1)-[r['rho_global'] for r in old]))<1e-12
        for metric,mask in [('V44_CANONICAL_OBJECTIVE',c),('ALL_TERMINAL_SECURITY_DIAGNOSTIC',s)]:
            ij=np.where(mask)[0];ev=a[offset:];flat=int(np.argmax(ev[:,ij]));t,j=np.unravel_index(flat,(len(ev),len(ij)));j=int(ij[j]);v=axis[j]
            rows.append(dict(case=receipt['case'],role=receipt['role'],beta_BG=receipt.get('beta_BG',1.5),
                kind=receipt.get('kind','B0'),amplitude=receipt.get('amplitude',''),metric=metric,rho_max=float(ev[t,j]),
                rho_MV=float(ev[:,mask & np.array([r['group']=='Primary' for r in axis])].max()),
                rho_LV=float(ev[:,mask & np.array([r['group']!='Primary' for r in axis])].max()),
                peak_slot=t,line=v['element'],phase=v['physical_phase'],terminal=v['terminal'],
                all_terminal_thermal_PASS=bool(np.max(a[:,s])<=1+1e-8),fresh='FRESH' in receipt['case']))
        for t in range(len(a)):
            ij=np.where(c)[0];j=int(ij[np.argmax(a[t,ij])]);v=axis[j]
            slots.append(dict(case=receipt['case'],slot=t,evaluation_slot=t-offset,rho_objective=float(a[t,c].max()),
                rho_all_terminals=float(a[t,s].max()),rho_MV_objective=float(a[t,m].max()),rho_LV_objective=float(a[t,l].max()),
                line=v['element'],phase=v['physical_phase'],terminal=v['terminal']))
        grouped={}
        for j,v in enumerate(axis):
            if not c[j]:continue
            rho=float(a[offset:,j].max())
            if rho>grouped.get(v['element'],{}).get('rho',-1):grouped[v['element']]=dict(line=v['element'],rho=rho,phase=v['physical_phase'],terminal=v['terminal'])
        for k,r in enumerate(sorted(grouped.values(),key=lambda r:(-r['rho'],r['line']))[:20]):top.append(dict(case=receipt['case'],rank=k+1,**r))
        print('RECALCULATED',receipt['case'],flush=True)
    canonical=[r.copy() for r in rows if r['metric']=='V44_CANONICAL_OBJECTIVE']
    base={(r['role'],r['beta_BG']):r['rho_max'] for r in canonical if r['kind']=='B0' and not r['fresh']}
    for r in canonical:r['delta_global_pp']=100*(base[(r['role'],r['beta_BG'])]-r['rho_max'])
    csvout('CANONICAL_VS_ALL_TERMINAL_RESULTS.csv',rows);csvout('RECALCULATED_B0_AND_PILOT.csv',canonical)
    csvout('RECALCULATED_SLOT_RESULTS.csv',slots);csvout('RECALCULATED_CANONICAL_TOP20.csv',top)
    put('OBJECTIVE_CERTIFICATION.json',dict(status='OBJECTIVE_CERTIFIED',old_mask_matches=False,
        independent_orientation_matches_PR197=True,line_count=len(orientation),canonical_cells=int(c.sum()),
        all_terminal_cells=int(s.sum()),disabled_lines=sum(not r['enabled'] for r in orientation),
        legacy_array_cases=len(receipts),new_operating_solves_for_recalculation=0,tolerance=1e-12))

def clock_class():
    source=ROOT/'v44/svr11_frozen/v42_voltage_control/timecontrol.py'
    tree=ast.parse(source.read_text(encoding='utf-8'))
    body=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) or isinstance(n,ast.Assign)]
    # Same chronological bound extension used by v44/svr11_ac.py:prefix_clock_class.
    class Axis(ast.NodeTransformer):
        def visit_Compare(self,node):
            if ast.unparse(node)=='0 <= slot < 96':node.comparators[-1]=ast.Constant(120)
            return self.generic_visit(node)
    tree=Axis().visit(ast.Module(body=body,type_ignores=[]));ast.fix_missing_locations(tree)
    def require(condition,message):
        if not condition:raise ValueError(message)
    ns=dict(csv=csv,date=date,math=math,require=require)
    exec(compile(tree,str(source),'exec'),ns)
    return ns['CommonClock'],ns['queue']

class CorrectedPhysical(Physical):
    def __init__(self,tag,role,mode='TIME'):
        super().__init__('CORRECTION_'+tag)
        self.role=role;self.mode=mode
        self.orientation=independent_orientation(self)
        self.canonical,self.security,self.cmv,self.clv=masks(self.line_axes,self.orientation)
        self.all_mask=self.canonical;self.mv_mask=self.cmv;self.lv_mask=self.clv
        self.triplex_mask=self.clv & np.array([r['group']=='Triplex' for r in self.line_axes])
        for r,c in zip(self.line_axes,self.canonical):
            r['objective_included']=bool(c);r['objective_scope']='V44_CANONICAL_OBJECTIVE'
        self.d.Solution.Hour(0);self.d.Solution.Seconds(0)
        self.d.Solution.MaxIterations(15);self.d.Solution.MaxControlIterations(100)
        self.clock=None
        if mode=='TIME':
            Clock,self.queue=clock_class();self.clock=Clock('ACTUAL' if role=='ACTUAL' else 'DAYAHEAD','2025-05-01')
            self.bind_receipt=self.clock.bind(self.d)
        self.last_events=[]

    def apply(self,role,t,beta,mess=None,aidc_delta=None):
        # Parent applies injections, then resets the STATIC clock. Retain the TIME
        # clock/queue/state across calls; no repeated mode=snapshot reset in TIME.
        if self.mode!='TIME':return super().apply(role,t,beta,mess,aidc_delta)
        import inspect,textwrap
        tree=ast.parse(textwrap.dedent(inspect.getsource(Physical.apply)))
        function=tree.body[0];function.name='_apply_injections_only'
        class InjectionOnly(ast.NodeTransformer):
            def visit_Expr(self,node):
                if isinstance(node.value,ast.Call) and ast.unparse(node.value.func) in ('self.d.Text.Command','self.d.Solution.Hour','self.d.Solution.Seconds'):return None
                return self.generic_visit(node)
        tree=InjectionOnly().visit(tree);ast.fix_missing_locations(tree)
        ns=dict(Physical.apply.__globals__);exec(compile(tree,__file__,'exec'),ns)
        ns['_apply_injections_only'](self,role,t,beta,mess,aidc_delta)

    def measure(self,role,t,beta,**kwargs):
        if self.mode!='TIME':
            row,a,state,ports=super().measure(role,t,beta,**kwargs)
            row['rho_all_terminals']=float(a['line_rho'][self.security].max())
            row['line_violation_cells']=int(np.sum((a['line_rho']>1+1e-8)&self.security))
            row['physics_PASS']=row['physics_PASS'] and row['line_violation_cells']==0
            return row,a,state,ports
        observed=[];eventarrays=[];eventstates=[];eventports=[]
        # Use original measurement/accounting without another automatic solve.
        # Its single Solve call is replaced with native SolveSnap; controlmode
        # assignment from the legacy function is suppressed via a tiny AST copy.
        import inspect,textwrap
        tree=ast.parse(textwrap.dedent(inspect.getsource(Physical.measure)))
        function=tree.body[0];function.name='_read_time_event'
        class Reader(ast.NodeTransformer):
            def visit_Expr(self,node):
                if isinstance(node.value,ast.Call) and ast.unparse(node.value.func)=='self.d.Text.Command':return None
                return self.generic_visit(node)
        tree=Reader().visit(tree);ast.fix_missing_locations(tree)
        ns=dict(Physical.measure.__globals__);exec(compile(tree,__file__,'exec'),ns);reader=ns['_read_time_event']
        def solve():
            # read_time_event performs one full native Solve at this physical time.
            row,a,state,ports=reader(self,role,t,beta,accounting=True)
            row['physical_seconds']=self.d.Solution.Hour()*3600+self.d.Solution.Seconds()
            row['rho_all_terminals']=float(a['line_rho'][self.security].max())
            row['line_violation_cells']=int(np.sum((a['line_rho']>1+1e-8)&self.security))
            pending=self.queue(self.d)
            row['physics_PASS']=bool(row['converged'] and row['controls_done'] and
                all(v['absolute_seconds']>row['physical_seconds'] for v in pending) and
                not any(row[k] for k in ('line_violation_cells','node_voltage_violation_cells','transformer_violation_cells','port_violation_cells')) and
                max(abs(row[k]) for k in ['PV_total_abs_error_kw','PV_actual_kvar','BG_P_abs_error_kw','BG_Q_abs_error_kvar','balance_P_error_kw','balance_Q_error_kvar'])<1e-4)
            observed.append(row);eventarrays.append(a);eventstates.append(state);eventports.append(ports)
        receipt=self.clock.settle_slot(self.d,t,solve=solve)
        self.last_events=receipt
        # Objective and safety cover every solved subslot, not only the last state.
        winner=int(np.argmax([v['rho_global'] for v in observed]));row=observed[winner].copy()
        for k in ('rho_global','rho_MV','rho_LV','rho_Triplex','rho_all_terminals','Vmax','transformer_nameplate_max','transformer_current_max','port_current_max'):
            row[k]=max(v[k] for v in observed)
        row['Vmin']=min(v['Vmin'] for v in observed);row['physics_PASS']=all(v['physics_PASS'] for v in observed)
        row['event_solve_count']=len(observed);row['end_seconds']=receipt['end_seconds']
        self.event_rows=observed;self.event_arrays=eventarrays;self.event_states=eventstates
        return row,eventarrays[winner],eventstates[-1],eventports[winner]

def fingerprint():
    files=[ROOT/'v2_add_preflight/physical.py',
        ROOT/'v2_add_preflight/vendor/ieee8500_ac.py',DOC/'PHYSICAL_CONFIGURATION_FREEZE.json',
        DOC/'AIDC12_STA12_PCC_MAPPING.csv',DOC/'input/IEEE123_FROZEN_ELECTRICAL_INPUTS.npz',
        DOC/'input/IEEE8500_BG_ALLOCATION_CANDIDATE.npz',ROOT/'v44/svr11_frozen/v42_voltage_control/timecontrol.py']
    files+=sorted((DOC/'source/feeder').glob('*'))
    import inspect
    result={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in files if p.is_file()}
    result['effective_correction_code']=sha('\n'.join(inspect.getsource(v) for v in
        (independent_orientation,masks,clock_class,CorrectedPhysical,trajectory,run_case)).encode())
    return result

def run_case(beta,role,mode='TIME',schedule=None,fresh=False,aidc=None):
    name='B0' if schedule is None else schedule['name']
    tag=f'{mode}_{beta:.2f}_{role}_{name}'+('_FRESH' if fresh else '')
    folder=RUN/tag;folder.mkdir(exist_ok=True)
    key=dict(beta=beta,role=role,mode=mode,schedule=schedule,aidc_sha=None if aidc is None else sha(aidc.tobytes()),inputs=fingerprint())
    identity=sha(json.dumps(key,sort_keys=True).encode())
    if (folder/'RECEIPT.json').exists():
        receipt=read(folder/'RECEIPT.json');assert receipt['identity']==identity,'Changed scientific inputs; preserve case and choose an explicit new evidence tag'
        assert all(sha((folder/p).read_bytes())==h for p,h in receipt['files'].items()),'Cached artifact changed'
        print('REUSE',tag,flush=True);return read(folder/'ROWS.json'),receipt
    e=CorrectedPhysical(tag,role,mode);rows=[];states=[];events=[];all_event_rows=[];event_slots=[]
    arrays={k:[] for k in ('line_rho','node_voltage_pu','transformer_current_rho','transformer_winding_nameplate_kva_rho')}
    count=120 if role=='ACTUAL' else 96;offset=24 if role=='ACTUAL' else 0
    initial=read(DOC/'MESS8_INITIAL_STATES_AND_PORTS.json')['initial_sites']
    p,q,soc=trajectory(schedule) if schedule is not None else (None,None,None)
    for t in range(count):
        ev=t-offset;mess={}
        if schedule is not None and ev>=0:
            mess={site:(float(p[ev,u]),float(q[ev,u])) for u,site in enumerate(initial.values())}
        delta=None
        if aidc is not None:delta={site:tuple(aidc[t,j]) for j,site in enumerate(e.sites)}
        e.apply(role,t,beta,mess,delta)
        row,a,state,ports=e.measure(role,t,beta)
        rows.append(row);states.append(state)
        observed=e.event_arrays if mode=='TIME' else [a]
        event_slots.extend([t]*len(observed))
        for v in observed:
            for k in arrays:arrays[k].append(v[k])
        if mode=='TIME':events.append(e.last_events);all_event_rows.extend(e.event_rows)
        if t%32==0:print(tag,t,round(row['rho_global']*100,4),'events',row.get('event_solve_count',1),flush=True)
    e.check_parameters()
    np.savez_compressed(folder/'AC_FULL.npz',**{k:np.stack(v) for k,v in arrays.items()},event_slot=np.array(event_slots))
    for name,value in [('ROWS',rows),('STATES',states),('EVENTS',events),('EVENT_ROWS',all_event_rows),
        ('AXES',dict(line=e.line_axes,nodes=e.node_axes,orientation=e.orientation))]:
        (folder/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    receipt=dict(case=tag,identity=identity,scientific_inputs=key,files={p.name:sha(p.read_bytes()) for p in folder.iterdir() if p.is_file()},
        physics_PASS=all(v['physics_PASS'] for v in rows),physical_solve_count=e.solve_count,native_optimizer_calls=0,
        initial_state=e.initial_state,archive_path=str(folder/'AC_FULL.npz'))
    (folder/'RECEIPT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('DONE',tag,'PASS',receipt['physics_PASS'],'solves',e.solve_count,flush=True)
    return rows,receipt

def trajectory(schedule):
    if schedule is None:return None,None,None
    p=np.zeros((96,8));q=p.copy();soc=np.full((97,8),760.)
    for u in range(8):
        b=schedule['discharge_begin'][u];n=schedule['duration']
        p[8:16,u]=320/.95/2
        p[b:b+n,u]=-320*.95/(n*.25)
        q[b:b+n,u]=-schedule.get('Q_support',0.)
    for t in range(96):soc[t+1]=soc[t]+.25*(.95*np.maximum(p[t],0)-np.maximum(-p[t],0)/.95)
    assert np.max(abs(soc[-1]-760))<1e-8 and soc.min()>=440-1e-8 and soc.max()<=1080+1e-8
    assert abs(p).max()<=300 and abs(q).max()<=250
    for a in np.arange(16)*2*np.pi/16:assert np.max(np.cos(a)*p+np.sin(a)*q)<=400*np.cos(np.pi/16)+1e-8
    return p,q,soc

def summary(rows,receipt,beta,role):
    off=24 if role=='ACTUAL' else 0;ev=rows[off:];peak=max(ev,key=lambda r:r['rho_global'])
    return dict(case=receipt['case'],beta_BG=beta,role=role,rho_objective=max(r['rho_global'] for r in ev),
        rho_all_terminals=max(r['rho_all_terminals'] for r in ev),rho_MV_objective=max(r['rho_MV'] for r in ev),
        rho_LV_objective=max(r['rho_LV'] for r in ev),MV_LV_headroom_pp=100*(max(r['rho_MV'] for r in ev)-max(r['rho_LV'] for r in ev)),
        peak_slot=peak['evaluation_slot'],line=peak['binding_line'],phase=peak['binding_physical_phase'],terminal=peak['binding_terminal'],
        Vmin=min(r['Vmin'] for r in rows),Vmax=max(r['Vmax'] for r in rows),physics_PASS=receipt['physics_PASS'],
        physical_solve_count=receipt['physical_solve_count'],receipt=str(Path(receipt['archive_path']).parent/'RECEIPT.json'))

def fresh_check(a,b):
    pa=Path(a['archive_path']).parent;pb=Path(b['archive_path']).parent
    x=np.load(pa/'AC_FULL.npz');y=np.load(pb/'AC_FULL.npz')
    diff={k:float(np.max(abs(x[k]-y[k]),initial=0)) if x[k].shape==y[k].shape else None for k in x.files}
    states=read(pa/'STATES.json')==read(pb/'STATES.json');events=read(pa/'EVENTS.json')==read(pb/'EVENTS.json')
    return dict(case=a['case'],differences=diff,states_identical=states,events_identical=events,
        PASS=all(v is not None and v<=1e-9 for v in diff.values()) and states and events)

def time_tests():
    priority();assert read(OUT/'OBJECTIVE_CERTIFICATION.json')['status']=='OBJECTIVE_CERTIFIED'
    results=[];checks=[];compare=[]
    for beta in (1.,1.5):
        for role in ('PLANNING','ACTUAL'):
            rows,r=run_case(beta,role);fr,rr=run_case(beta,role,fresh=True);check=fresh_check(r,rr);checks.append(check);assert check['PASS']
            s=summary(rows,r,beta,role);results.append(s)
            oldfolder=RUNTIME/'phase2'/f'B0_beta{beta:.2f}_{role}'
            old=read(oldfolder/'ROWS.json');oldstates=read(oldfolder/'STATES.json')
            for t,row in enumerate(rows):
                compare.append(dict(beta_BG=beta,role=role,slot=t,evaluation_slot=row['evaluation_slot'],
                    static_all_terminal=old[t]['rho_global'],time_canonical=row['rho_global'],time_all_terminal=row['rho_all_terminals'],
                    all_terminal_difference_pp=100*(row['rho_all_terminals']-old[t]['rho_global']),
                    final_taps_differ=oldstates[t]['taps']!=read(Path(r['archive_path']).parent/'STATES.json')[t]['taps'],
                    final_caps_differ=oldstates[t]['capacitors']!=read(Path(r['archive_path']).parent/'STATES.json')[t]['capacitors'],
                    time_physical_solves=row['event_solve_count']))
            csvout('TIME_B0_ANCHOR_RESULTS.csv',results);csvout('STATIC_VS_TIME_CONTROL_AUDIT.csv',compare)
            put('TIME_CONTROL_FRESH_CERTIFICATION.json',dict(status='RUNNING',checks=checks))
    put('TIME_CONTROL_FRESH_CERTIFICATION.json',dict(status='TIME_CONTROL_CERTIFIED',checks=checks,
        original_event_loop='r043 CommonClock; only chronological 96->120 bound extension as in svr11_ac.prefix_clock_class',
        temporal_contract='snapshot body, TIME2; all native queued instants before next boundary solved; boundary next inputs first',
        independent_Planning_Actual=True,actual_prefix_continuity=True,clock='issue-relative 0..108000s Actual, day-relative0..86400s Planning',
        hardware_contract='IEEE8500 P5 independent frozen hardware; not IEEE123 SVR43 equivalence',
        all_subslot_objective_and_security=True))

if __name__=='__main__':
    globals()[sys.argv[1]]()
