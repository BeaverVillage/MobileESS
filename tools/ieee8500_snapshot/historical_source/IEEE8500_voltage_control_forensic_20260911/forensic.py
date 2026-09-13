import sys,os,json,csv,hashlib,math,time
from pathlib import Path
from collections import defaultdict,deque
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OLD=ROOT/'IEEE8500_operating_point_20260911'
sys.path.insert(0,str(OLD))
import run_b0_screen as frozen
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')
def table(p,rs):
    if not rs:return
    with Path(p).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows([{k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in rs])
def protect():
    if (HERE/'PROTECTED_AUTHORITIES_BEFORE.json').exists():
        for r in read(HERE/'PROTECTED_AUTHORITIES_BEFORE.json'):assert sha(Path(r['path']))==r['sha256']
        return
    mp=OLD/'OPERATING_POINT_FREEZE_MANIFEST.json';assert sha(mp)==(OLD/'OPERATING_POINT_FREEZE_MANIFEST.sha256').read_text().split()[0]
    m=read(mp)
    for r in m['files']:assert sha(OLD/r['path'])==r['sha256']
    assert read(OLD/'SELECTED_ALPHA_AND_B0_STATUS.json')['status']=='NO_FEASIBLE_ALPHA_ON_FROZEN_GRID'
    records=[]
    for f in ['IEEE8500_scalability_20260910','IEEE8500_pcc_overlay_20260911','IEEE8500_operating_point_20260911']:
        for p in sorted((ROOT/f).rglob('*')):
            if p.is_file():s=p.stat();records.append(dict(path=str(p),sha256=sha(p),bytes=s.st_size,mtime_ns=s.st_mtime_ns))
    save(HERE/'PROTECTED_AUTHORITIES_BEFORE.json',records)
    save(HERE/'DIAGNOSTIC_INPUT_BINDING.json',dict(preregistration_sha256=sha(HERE/'DIAGNOSTIC_PREREGISTRATION.json'),original_operating_freeze_sha256=sha(mp),frozen_helper_sha256=sha(OLD/'run_b0_screen.py'),original_result='NO_FEASIBLE_ALPHA_ON_FROZEN_GRID',source_and_host_changes_allowed=False,created_before_diagnostic_solves=True))

class Model:
    def __init__(self,folder):
        self.d=d=frozen.engine(folder/'runtime');self.loads=frozen.native_inventory(d);self.ax=frozen.measurement_axes(d)
        self.nodes=list(d.Circuit.AllNodeNames());self.nodeidx={n:i for i,n in enumerate(self.nodes)}
        self.graph=self.build_graph();self.base_regs=self.regs();self.base_caps=self.caps(solved=False);self.base_sources=self.sources(solved=False)
        self.reg_by_transformer={r['transformer']:r['bank'] for r in self.base_regs}
        self.ratio=read(OLD/'PV_PENETRATION_RATIO_AUTHORITY.json')['ratio'];self.inv=read(frozen.OVERLAY/'PCC_OVERLAY_INVENTORY.json')
        text=frozen.add_resources(d,self.loads,self.ratio,self.inv);assert text==(OLD/'B0_RESOURCE_OBJECTS.dss').read_text(encoding='utf-8')
        f=read(OLD/'D1_AEMO_VIC1_FORECAST_AUTHORITY.json');self.md=np.array(f['demand_mw_96'])/max(f['demand_mw_96']);self.mpv=np.array(f['pv_mw_96'])/max(f['pv_mw_96'])
        with np.load(OLD/'V41R4_B0_AIDC_POWER_UNCHANGED.npz') as z:self.ap=z['pcc'].copy();self.aq=z['qcc'].copy()
        self.aidcs=sorted([r for r in self.inv if r['PCC_role']=='AIDC'],key=lambda r:r['location_id'])
    def build_graph(self):
        d=self.d;corr=defaultdict(list);adj=defaultdict(set);base={};busnodes={}
        for b in d.Circuit.AllBusNames():
            d.Circuit.SetActiveBus(b);base[b]=d.Bus.kVBase();busnodes[b]=d.Bus.Nodes()
        for name in d.PDElements.AllNames():
            d.Circuit.SetActiveElement(name)
            if not d.CktElement.Enabled():continue
            buses=d.CktElement.BusNames();bs=[b.split('.')[0].lower() for b in buses];nc=d.CktElement.NumConductors();nodes=np.array(d.CktElement.NodeOrder()).reshape(-1,nc).tolist()
            for j in range(1,len(bs)):
                if bs[0]==bs[j]:continue
                edge=dict(element=name.lower(),terminal_a=1,terminal_b=j+1,bus_a=bs[0],bus_b=bs[j],nodes_a=nodes[0],nodes_b=nodes[j],kind=name.split('.')[0].lower(),phases=d.CktElement.NumPhases())
                if edge['kind']=='transformer':
                    d.Transformers.Name(name.split('.',1)[1]);edge['bank']=d.Properties.Value('bank');edge['connection_a']='delta' if (d.Transformers.Wdg(1) or d.Transformers.IsDelta()) else 'wye'
                    d.Transformers.Wdg(j+1);edge['connection_b']='delta' if d.Transformers.IsDelta() else 'wye'
                corr[tuple(sorted([bs[0],bs[j]]))].append(edge);adj[bs[0]].add(bs[j]);adj[bs[j]].add(bs[0])
        d.Vsources.First();root=d.CktElement.BusNames()[0].split('.')[0].lower();parents={root:None};queue=deque([root]);order=[]
        while queue:
            b=queue.popleft();order.append(b)
            for c in sorted(adj[b]):
                if c not in parents:parents[c]=b;queue.append(c)
        assert len(parents)==4912 and len(corr)==4911
        links=[];nodeparents={};bus_edges={}
        for b in order[1:]:
            par=parents[b];edges=corr[tuple(sorted([b,par]))];bus_edges[b]=edges
            for n in busnodes[b]:
                choices=[]
                for e in edges:
                    down=e['nodes_b'] if b==e['bus_b'] else e['nodes_a'];up=e['nodes_a'] if b==e['bus_b'] else e['nodes_b']
                    if n not in down:continue
                    if e['kind']=='transformer' and e['phases']==1:u=next(x for x in up if x!=0)
                    else:
                        u=up[down.index(n)]
                        if u==0:continue
                    choices.append((e,u))
                assert choices,(b,n)
                e,u=choices[0];dn=f'{b}.{n}';un=f'{par}.{u}';assert dn in self.nodeidx and un in self.nodeidx
                row=dict(upstream_node=un,downstream_node=dn,upstream_bus=par,downstream_bus=b,element=e['element'],kind=e['kind'],upstream_nominal_ln_kv=base[par],downstream_nominal_ln_kv=base[b],corridor_elements=sorted(set(x['element'] for x in edges)),regulator_bank=e.get('bank',''),substation_delta_wye_transfer=e.get('connection_a')=='delta' and e.get('connection_b')=='wye')
                links.append(row);nodeparents[dn]=row
        return dict(source_root=root,feeder_root='_hvmv_sub_lsb',parents=parents,links=links,nodeparents=nodeparents,base=base)
    def regs(self):
        d=self.d;rs=[]
        for name in d.RegControls.AllNames():
            d.RegControls.Name(name);tf=d.RegControls.Transformer().lower();wd=d.RegControls.TapWinding();ctrlwd=d.RegControls.Winding();vreg=d.RegControls.ForwardVreg();band=d.RegControls.ForwardBand();ptr=float(d.Properties.Value('ptratio'));tapnum=d.RegControls.TapNumber();rev=d.Properties.Value('reversible')
            d.Transformers.Name(tf);d.Transformers.Wdg(wd);tap=d.Transformers.Tap();bank=d.Properties.Value('bank');buses=d.CktElement.BusNames();cb=buses[ctrlwd-1].split('.')[0];d.Circuit.SetActiveBus(cb);base=d.Bus.kVBase()
            rs.append(dict(regcontrol=name,transformer=tf,bank=bank,controlled_bus=cb,terminal_buses=buses,winding=wd,accepted_tap_number=tapnum,accepted_tap_pu=tap,Vreg_V=vreg,band_V=band,PT_ratio=ptr,controlled_bus_base_LN_kV=base,target_pu=vreg*ptr/(1000*base),deadband_low_pu=(vreg-band/2)*ptr/(1000*base),deadband_high_pu=(vreg+band/2)*ptr/(1000*base),reversible=rev))
        return rs
    def caps(self,solved=True):
        d=self.d;associations=defaultdict(list)
        for name in d.CapControls.AllNames():
            d.CapControls.Name(name);associations[d.CapControls.Capacitor().lower()].append(dict(capcontrol=name,enabled=d.CktElement.Enabled(),ONsetting=d.CapControls.ONSetting(),OFFsetting=d.CapControls.OFFSetting(),Vmin=d.CapControls.Vmin(),Vmax=d.CapControls.Vmax(),voltage_override=d.CapControls.UseVoltOverride()))
        rs=[]
        for name in d.Capacitors.AllNames():
            d.Capacitors.Name(name);enabled=d.CktElement.Enabled();state=list(d.Capacitors.States());kvar=d.Capacitors.kvar();buses=d.CktElement.BusNames();ns=d.Capacitors.NumSteps();assert ns==1
            physical=float(-np.array(d.CktElement.Powers()).reshape(-1,2)[:,1].sum()) if solved and enabled else (0. if solved else None)
            rs.append(dict(capacitor=name,bank=name[:-1] if name[-1] in 'abc' else name,bus_connections=buses,phases=d.CktElement.NumPhases(),nominal_kV=d.Capacitors.kV(),nameplate_kvar=kvar,enabled=enabled,step_states=state,effective_ON=bool(enabled and any(state)),nominal_ON_kvar=kvar*sum(state)/ns if enabled else 0.,physical_injected_kvar=physical,native_controlled=bool(associations[name]),capcontrols=associations[name]))
        return rs
    def sources(self,solved=True):
        d=self.d;rs=[]
        for name in d.Vsources.AllNames():
            d.Vsources.Name(name);bus=d.CktElement.BusNames()[0].split('.')[0];r=dict(source=name,source_bus=bus,setpoint_pu=d.Vsources.PU(),base_kV_LL=d.Vsources.BasekV(),angle_degrees=d.Vsources.AngleDeg(),frequency_Hz=d.Vsources.Frequency())
            d.Circuit.SetActiveBus(bus);r['bus_nominal_LN_kV']=d.Bus.kVBase()
            if solved:r['phase_nodes']=d.Bus.Nodes();r['phase_voltage_pu']=d.Bus.puVmagAngle()[::2];r['phase_voltage_mag_angle']=d.Bus.VMagAngle()
            rs.append(r)
        return rs
    def slot(self,a,t):
        d=self.d;d.Solution.LoadMult(1.);d.Solution.Hour(t//4);d.Solution.Seconds((t%4)*900)
        for i,r in enumerate(self.loads):
            d.Loads.Name(r['load']);d.Loads.kW(float(a*self.md[t]*r['base_kw']));d.Loads.kvar(float(a*self.md[t]*r['base_kvar']))
            d.Generators.Name(f'op8500_pv_{i:04d}');p=float(a*self.ratio*r['base_kw']*self.mpv[t]);d.CktElement.Enabled(p>0)
            if p>0:d.Generators.kW(p);d.Generators.kvar(0.)
        for j,r in enumerate(self.aidcs):d.Loads.Name('op8500_'+r['location_id'].lower());d.Loads.kW(float(self.ap[t,j]));d.Loads.kvar(float(self.aq[t,j]))
        self.solve()
    def solve(self):
        self.d.Solution.SolveSnap();assert self.d.Solution.Converged();assert self.d.Error.Number()==0
    def measure(self):
        d=self.d;ax=self.ax;v=np.array(d.Circuit.AllBusMagPu());raw=np.asarray(d.PDElements.AllCurrentsMagAng()).reshape(-1,2)[:,0];power=np.asarray(d.PDElements.AllPowers()).reshape(-1,2)
        line=raw[ax['line_pos']]/ax['line_rating'];tx=raw[ax['tx_pos']]/ax['tx_rating'];ps=np.bincount(ax['power_group'],weights=power[ax['power_pos'],0]);qs=np.bincount(ax['power_group'],weights=power[ax['power_pos'],1]);kva=np.hypot(ps,qs)/ax['kva_rating']
        return dict(Vmin_pu=float(v.min()),Vmax_pu=float(v.max()),Vmin_node=self.nodes[v.argmin()],Vmax_node=self.nodes[v.argmax()],max_phase_line_loading_pu=float(line.max()),line_witness=str(ax['line_label'][line.argmax()]),max_transformer_current_pu=float(tx.max()),max_transformer_kva_pu=float(kva.max()),overvoltage_node_count=int((v>1.05+1e-9).sum()),undervoltage_node_count=int((v<.95-1e-9).sum()),native_controls_complete=bool(d.Solution.ControlActionsDone())),v,line,tx,kva
    def path(self,node,v,regs):
        g=self.graph;parts=[];cur=node
        while cur in g['nodeparents']:
            edge=g['nodeparents'][cur];parts.append(edge);cur=edge['upstream_node']
        parts.reverse();path=[dict(order=0,node=cur,bus=cur.rsplit('.',1)[0],local_node=int(cur.rsplit('.',1)[1]),voltage_pu=float(v[self.nodeidx[cur]]),incoming_element='',incoming_corridor_elements=[],banks_on_incoming_corridor=[],accepted_path_regulators=[],crosses_up_into_overvoltage=False,feeder_electrical_root=cur.rsplit('.',1)[0]==g['feeder_root'])]
        for i,e in enumerate(parts,1):
            banks=sorted(set(r['bank'] for r in regs if 'transformer.'+r['transformer'] in e['corridor_elements']));rr=[r for r in regs if r['bank'] in banks];un=e['upstream_node'];dn=e['downstream_node'];uv=float(v[self.nodeidx[un]]);dv=float(v[self.nodeidx[dn]])
            path.append(dict(order=i,node=dn,bus=e['downstream_bus'],local_node=int(dn.rsplit('.',1)[1]),voltage_pu=dv,incoming_element=e['element'],incoming_corridor_elements=e['corridor_elements'],banks_on_incoming_corridor=banks,accepted_path_regulators=rr,crosses_up_into_overvoltage=uv<=1.05+1e-9 and dv>1.05+1e-9,feeder_electrical_root=e['downstream_bus']==g['feeder_root']))
        return path
    def frontiers(self,v):
        out=[]
        for e in self.graph['links']:
            uv=float(v[self.nodeidx[e['upstream_node']]]);dv=float(v[self.nodeidx[e['downstream_node']]])
            if uv<=1.05+1e-9 and dv>1.05+1e-9:out.append(dict(**e,upstream_pu=uv,downstream_pu=dv))
        return out
    def modify(self,case):
        d=self.d;changes=[]
        if case in ['ALL_CAP_INJECTIONS_DISABLED','UNCONTROLLED_CAP_ONLY_DISABLED']:
            targets=[r for r in self.base_caps if case=='ALL_CAP_INJECTIONS_DISABLED' or not r['native_controlled']]
            for r in targets:
                for c in r['capcontrols']:d.CapControls.Name(c['capcontrol']);d.CktElement.Enabled(False)
                d.Capacitors.Name(r['capacitor']);d.CktElement.Enabled(False);changes.append(dict(parameter='capacitor_injection_enabled',element=r['capacitor'],before=True,after=False))
        if case in ['SOURCE_PU_1_ONLY','SOURCE_AND_ALL_VREG_GLOBAL_SCALE']:
            assert len(self.base_sources)==1 and self.base_sources[0]['setpoint_pu']==1.05;factor=1/self.base_sources[0]['setpoint_pu']
            for r in self.base_sources:d.Vsources.Name(r['source']);d.Vsources.PU(r['setpoint_pu']*factor);changes.append(dict(parameter='source_pu',element=r['source'],before=r['setpoint_pu'],after=d.Vsources.PU()))
            if case=='SOURCE_AND_ALL_VREG_GLOBAL_SCALE':
                for r in self.base_regs:
                    assert r['reversible'].lower() in ['no','false'];d.RegControls.Name(r['regcontrol']);d.RegControls.ForwardVreg(r['Vreg_V']*factor);changes.append(dict(parameter='Vreg',element=r['regcontrol'],before=r['Vreg_V'],after=d.RegControls.ForwardVreg()))
        return changes

def main():
    protect();spec=read(HERE/'DIAGNOSTIC_PREREGISTRATION.json');witnesses=[];replays=[];cfrows=[];allfrontiers=[];allstates=[];paths=[]
    for alpha in spec['representative_alphas']:
        folder=HERE/'native'/f'alpha_{alpha:.2f}';folder.mkdir(parents=True,exist_ok=True);model=Model(folder)
        oldfolder=OLD/'screen'/f'alpha_{alpha:.2f}'
        with np.load(oldfolder/'B0_ALL_PHASE_ARRAYS.npz') as z:original={k:z[k].copy() for k in ['voltage_pu','line_current_loading_pu','transformer_current_loading_pu','transformer_total_kva_loading_pu']}
        os=read(oldfolder/'NATIVE_CONTROL_STATES_96.json');targets={}
        for kind,fun in [('Vmax',np.argmax),('Vmin',np.argmin)]:
            t,n=np.unravel_index(fun(original['voltage_pu']),original['voltage_pu'].shape);targets[kind]=dict(slot=int(t),node=model.nodes[n],original_value=float(original['voltage_pu'][t,n]))
        if not (HERE/'STATIC_NATIVE_CONTROL_MODEL.json').exists():save(HERE/'STATIC_NATIVE_CONTROL_MODEL.json',dict(sources=model.base_sources,regulators=model.base_regs,capacitors=model.base_caps,root=model.graph['source_root'],feeder_root=model.graph['feeder_root'],bus_count=len(model.graph['parents']),corridors=4911));save(HERE/'ELECTRICAL_PHASE_LINKS.json',model.graph['links'])
        errors=[0.,0.,0.,0.];rr=[];native_vectors=[];alpha_states=[]
        for t in range(96):
            model.slot(alpha,t);s,v,line,tx,kva=model.measure();regs=model.regs();caps=model.caps();source=model.sources();front=model.frontiers(v)
            for i,(key,val) in enumerate(zip(original,[v,line,tx,kva])):errors[i]=max(errors[i],float(abs(original[key][t]-val).max()))
            assert [r['accepted_tap_number'] for r in regs]==os[t]['tap_numbers'];assert [r['step_states'] for r in caps]==os[t]['capacitor_states']
            rr.append(dict(alpha=alpha,slot=t,**s));state=dict(alpha=alpha,slot=t,regulators=regs,capacitors=caps,source=source);allstates.append(state);alpha_states.append(state);allfrontiers.extend(dict(alpha=alpha,slot=t,**r) for r in front);native_vectors.append(v)
            for kind,target in targets.items():
                if target['slot']!=t:continue
                path=model.path(target['node'],v,regs);local=target['node'].rsplit('.',1)[1];primary=next((r['local_node'] for r in path if r['feeder_electrical_root']),path[0]['local_node'])
                w=dict(alpha=alpha,witness=kind,slot=t,bus=target['node'].rsplit('.',1)[0],local_node=int(local),upstream_primary_phase='ABC'[primary-1],node=target['node'],value_pu=target['original_value'],path_nodes=len(path),source=source,all_regulator_states=regs,all_capacitor_states=caps,root_to_bus_path=path,overvoltage_onsets_on_path=[r for r in path if r['crosses_up_into_overvoltage']],all_feeder_overvoltage_frontiers=front,source_itself_above_limit=any(x>1.05+1e-9 for z in source for x in z['phase_voltage_pu']))
                witnesses.append(w);save(folder/f'{kind}_WITNESS.json',w);table(folder/f'{kind}_ROOT_TO_BUS_PATH.csv',path)
        assert max(errors)<1e-10;table(folder/'NATIVE_96_SLOT_EXTREMA.csv',rr);save(folder/'NATIVE_CONTROL_STATES_96.json',alpha_states);save(folder/'REPLAY_MATCH.json',dict(alpha=alpha,voltage_max_abs_error=errors[0],line_loading_max_abs_error=errors[1],transformer_current_max_abs_error=errors[2],transformer_kva_max_abs_error=errors[3],all_96_tap_and_cap_states_identical=True,converged_slots=96,status='PASS'))
        replays.append(read(folder/'REPLAY_MATCH.json'));model.d.Basic.ClearAll();print(f'Native alpha {alpha:.2f}: all 96 slots match original; witnesses {targets}',flush=True)
        for kind,target in targets.items():
            t=target['slot'];node=target['node']
            for case in spec['cases']:
                cfdir=HERE/'diagnostic_only'/f'alpha_{alpha:.2f}'/f'{kind}_slot_{t:02d}'/case
                if (cfdir/'DIAGNOSTIC_RESULT.json').exists():
                    detail=read(cfdir/'DIAGNOSTIC_RESULT.json')
                    for view,z in detail['views'].items():
                        cfrows.append(dict(alpha=alpha,witness=kind,slot=t,native_witness_node=node,case=case,view=view,diagnostic_status=z.get('diagnostic_status','CONVERGED'),original_witness_voltage_pu=z['original_witness_voltage_pu'],total_cap_injected_kvar=sum(r['physical_injected_kvar'] for r in z['capacitors']),source_setpoint_pu=z['source'][0]['setpoint_pu'],regulator_tap_numbers=[r['accepted_tap_number'] for r in z['regulators']],capacitor_effective_ON=[r['effective_ON'] for r in z['capacitors']],**z['metrics']))
                    continue
                cf=Model(cfdir)
                for k in range(t+1):cf.slot(alpha,k)
                pre,pv,*_=cf.measure();assert np.max(abs(pv-original['voltage_pu'][t]))<1e-10
                native_regs=cf.regs();native_caps=cf.caps();changes=cf.modify(case);cf.d.Solution.ControlMode(-1);cf.solve()
                detail=dict(alpha=alpha,witness=kind,slot=t,native_witness_node=node,case=case,diagnostic_only=True,production_adoption=False,native_pre_intervention_metrics=pre,native_accepted_regulators=native_regs,native_accepted_capacitors=native_caps,parameter_changes=changes,views={})
                for view in ['STATE_HELD','CONTROL_SETTLED']:
                    error=None
                    if view=='CONTROL_SETTLED':
                        # EventLog is diagnostic telemetry only; no electrical setting changes.
                        for r in cf.base_regs:cf.d.Text.Command(f'Edit RegControl.{r["regcontrol"]} EventLog=yes')
                        for r in cf.base_caps:
                            for c in r['capcontrols']:cf.d.Text.Command(f'Edit CapControl.{c["capcontrol"]} EventLog=yes')
                        cf.d.Solution.ControlMode(0)
                        try:cf.solve()
                        except Exception as ex:
                            if '#485' not in str(ex):raise
                            error=str(ex)
                    diagnostic_status='CONTROL_ITERATION_LIMIT_EXCEEDED' if error or (view=='CONTROL_SETTLED' and not cf.d.Solution.ControlActionsDone()) else 'CONVERGED'
                    s,v,*_=cf.measure();regs=cf.regs();caps=cf.caps();source=cf.sources();path=cf.path(node,v,regs);front=cf.frontiers(v)
                    detail['views'][view]=dict(diagnostic_status=diagnostic_status,error=error,control_iterations=cf.d.Solution.ControlIterations(),event_log=cf.d.Solution.EventLog() if view=='CONTROL_SETTLED' else [],control_queue=cf.d.CtrlQueue.Queue() if error else [],metrics=s,original_witness_voltage_pu=float(v[cf.nodeidx[node]]),regulators=regs,capacitors=caps,source=source,root_to_original_witness_path=path,all_overvoltage_frontiers=front)
                    cfrows.append(dict(alpha=alpha,witness=kind,slot=t,native_witness_node=node,case=case,view=view,diagnostic_status=diagnostic_status,original_witness_voltage_pu=float(v[cf.nodeidx[node]]),total_cap_injected_kvar=sum(r['physical_injected_kvar'] for r in caps),source_setpoint_pu=source[0]['setpoint_pu'],regulator_tap_numbers=[r['accepted_tap_number'] for r in regs],capacitor_effective_ON=[r['effective_ON'] for r in caps],**s))
                save(cfdir/'DIAGNOSTIC_RESULT.json',detail);np.savez_compressed(cfdir/'CONTROL_SETTLED_VOLTAGE.npz',node_names=np.array(cf.nodes),voltage_pu=v);cf.d.Basic.ClearAll()
            print(f'Diagnostic alpha {alpha:.2f} {kind} slot {t}: 5 cases x 2 views complete',flush=True)
    save(HERE/'NATIVE_REPLAY_VERIFICATION.json',replays);save(HERE/'GLOBAL_WITNESSES_FULL.json',witnesses)
    table(HERE/'GLOBAL_WITNESSES.csv',[{k:w[k] for k in ['alpha','witness','slot','node','bus','local_node','upstream_primary_phase','value_pu','path_nodes','source_itself_above_limit']} for w in witnesses]);save(HERE/'ALL_NATIVE_CONTROL_STATES_480.json',allstates);table(HERE/'OVERVOLTAGE_ONSET_FRONTIERS_ALL_480_SLOTS.csv',allfrontiers);table(HERE/'COUNTERFACTUAL_COMPARISON.csv',cfrows);save(HERE/'COUNTERFACTUAL_COMPARISON.json',cfrows)
    save(HERE/'RUN_COMPLETION.json',dict(status='DIAGNOSTIC_COMPUTATION_COMPLETE',native_replay_slots=480,native_witness_conditions=10,diagnostic_cases=50,diagnostic_views=100,diagnostic_prefix_slots=sum(5*(w['slot']+1) for w in witnesses),diagnostic_intervention_solves=100,B1_B2_B3_runs=0,production_adoptions=0))
if __name__=='__main__':main()
