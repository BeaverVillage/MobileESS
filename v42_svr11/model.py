"""Forecast-only independent-prefix AUTO/TIME finite-response generation.

Every signed probe recompiles from source, replays the identical causal
forecast prefix, and changes only the target slot's one existing control.
Discrete tap responses are secants, not a smooth global AC certificate.
"""
from pathlib import Path
from types import SimpleNamespace
import copy,time,gc
import numpy as np
from v42_pr134_b1.common import read,record,atomic,digest,now
from .authority import active
from .context_lifecycle import retire_completed_probe,flush_completed_probes

FIELDS=('voltage_constant','voltage_matrix','current_constant','current_matrix',
    'flow_p_constant','flow_q_constant','flow_p_matrix','flow_q_matrix','branch_limits')

def load_coefficients(certificate,day):
    from v42_thermal.authority import current_authority,denominators
    from v42_thermal.common import SCHEMA
    if certificate['day']!=day or active() is None or certificate['source_SHA']!=active()['execution_SHA']:
        raise PermissionError('SVR11_COEFFICIENT_EPOCH_DRIFT')
    ref=certificate['outputs']['planning_coefficients']
    if record(ref['path'])!=ref:raise PermissionError('SVR11_COEFFICIENT_BYTES_DRIFT')
    with np.load(ref['path']) as z:
        names=tuple(map(str,z['branch_names']));controls=tuple(map(str,z['control_names']))
        expected=denominators(names);assert np.array_equal(expected,z['rating_a'])
        ratings=tuple(None if np.isnan(x) else float(x) for x in z['transformer_ratings'])
        # NPZ indexing decompresses the whole 96-slot field every time.
        # Read each immutable field once; retain detached per-slot copies.
        cached={f:z[f] for f in FIELDS+('anchor_control',)}
        result=[SimpleNamespace(**{f:cached[f][t].copy() for f in FIELDS},slot=t,
            control_names=controls,branch_names=names,anchor=cached['anchor_control'][t].copy(),transformer_ratings=ratings,
            coefficient_sha256=ref['sha256'],current_denominators_A=expected.copy(),
            transformer_current_contract=SCHEMA,
            transformer_current_authority_sha256=current_authority()['transformer_current_authority_sha256']) for t in range(96)]
    return result

def verify_coefficients(certificate,day,coefficients):
    expected=load_coefficients(certificate,day)
    if len(coefficients)!=96:raise PermissionError('SVR11_MODEL_96_SLOTS_REQUIRED')
    for a,b in zip(coefficients,expected):
        for f in FIELDS+('anchor','current_denominators_A'):
            if not np.array_equal(getattr(a,f),getattr(b,f)):raise PermissionError('SVR11_EXACT_MODEL_BINDING_DRIFT:'+f)
        if a.branch_names!=b.branch_names or a.control_names!=b.control_names or a.coefficient_sha256!=b.coefficient_sha256:
            raise PermissionError('SVR11_MODEL_AXIS_DRIFT')
    return dict(PASS=True,slots=96,controls=60,transformer_phase_rows_per_slot=153,
        coefficient_SHA_by_slot=[c.coefficient_sha256 for c in expected],
        new_hardware_model_regenerated=True,Actual_inputs_read=0,discrete_native_response_is_secant=True)

def generate(day,input_folder,output,progress):
    from v42_voltage_control.bindings import original_bindings
    from v42_voltage_control.svr import install
    from v42_voltage_control.timecontrol import CommonClock
    from v42_voltage_control.b0_new import build_planning
    from v42_regcontrol.runner import background
    from v42_thermal.authority import current_authority
    m=active();scenario=read(m['scenario']['path']);output=Path(output)
    cert_path=output/'ELECTRICAL_CERTIFICATE.json'
    if cert_path.is_file():
        cert=read(cert_path);verify_coefficients(cert,day,load_coefficients(cert,day));return record(cert_path)
    output.mkdir(parents=True,exist_ok=True)
    anchor_folder=output/'FORECAST_ANCHOR'
    plan=build_planning(day,input_folder,anchor_folder) if not (anchor_folder/'B0_NEW_PLANNING_GENERATION.json').exists() else None
    # Retrying an interrupted preparation uses exact frozen arrays, never a
    # previous policy solution. Planning producer artifacts are immutable.
    if plan is None:
        with np.load(anchor_folder/'PLANNING_PHYSICAL.npz') as z:arrays={k:z[k].copy() for k in z.files}
        plan={'arrays':arrays}
    p=np.asarray(plan['arrays']['PCC_P_kw']);assert p.shape==(96,12)
    authority,*_=original_bindings()
    from dayahead import run_v16_3_voltage_candidate as original
    from dayahead.v28r2.opendss_backend import _voltage_vector
    from dayahead.v28r2.opendss_mapping import _set_generator
    forecast=read(read(Path(input_folder)/'SOURCE_PROVENANCE.json')['daily_sources']['aemo_forecast.json']['path'])
    bg=background(forecast['timestamps_96'],forecast['demand_mw_96'],forecast['pv_mw_96'])
    e,ad,_=authority.compile_verified()
    try:
        install(e,scenario['svr']);branches,topology=authority.source()['oriented_branches'](e)
        nodes=tuple(sorted(n.lower() for n in e.Circuit.AllNodeNames() if n.rsplit('.',1)[-1] in ('1','2','3')))
        controls=original._control_axis(e);native=authority.source()['NativeAllocation'].from_adapter(ad)
        names=tuple(f'{b.branch_id}::{b.phase}' for b in branches)
        thermal=current_authority();rows={r['branch_phase'].lower():r for r in thermal['rows']+thermal['lines']}
        ratings=np.array([rows[n.lower()]['NormalAmps'] for n in names])
        kva=np.array([rows[n.lower()]['kVA']/rows[n.lower()]['Phases'] if n.startswith('transformer.') else np.nan for n in names])
        limits=np.array([b.ampacity_a_u080 for b in branches])
    finally:retire_completed_probe(e)
    del e
    flush_completed_probes()
    assert len(controls)==60 and sum(n.startswith('transformer.') for n in names)==153
    anchor=np.zeros((96,60));anchor[:,:12]=p
    count=solves=0;started=time.perf_counter();slots=[]
    def apply(e,ad,t):
        native.apply(e,bg,t)
        original._set_slot(e,{**ad,'loads':[]},bg,p,t)
    def measurement(e):
        v=_voltage_vector(e,nodes)**2
        pq=[original._terminal_phase(e,b.branch_id,b.parent_bus,b.phase) for b in branches]
        a=np.asarray(pq)
        return v,a[:,2]/ratings,a[:,0],a[:,1]
    def probe(target,j=None,sign=0):
        nonlocal count,solves
        e,ad,_=authority.compile_verified();count+=1
        try:
            clock=CommonClock('DAYAHEAD',day);clock.bind(e);install(e,scenario['svr'])
            for t in range(target+1):
                apply(e,ad,t)
                if t==target and j is not None:
                    delta=original._perturbation(controls[j],anchor[t,j])
                    original._apply_control(e,controls[j],float(anchor[t,j]+sign*delta),p[t])
                clock.settle_slot(e,t,capture_events=False)
            solves+=clock.total_physical_solve_count
            return measurement(e)
        finally:retire_completed_probe(e)
    for t in range(96):
        checkpoint=output/f'SLOT_{t:02d}.json'
        if checkpoint.is_file():
            saved=read(checkpoint)
            if saved['source_SHA']!=m['execution_SHA'] or saved['day']!=day or record(saved['data']['path'])!=saved['data']:
                raise PermissionError('SVR11_MODEL_CHECKPOINT_DRIFT')
            if saved.get('reused'):
                contract=read(m['model_checkpoint_reuse_contract']['path'])
                owned=contract['days'][day]['slots'].get(str(t))
                if not owned or record(owned['original_checkpoint']['path'])!=owned['original_checkpoint'] or record(owned['original_data']['path'])!=owned['original_data'] or owned['original_data']['sha256']!=saved['data']['sha256'] or saved['generation_source_SHA']!=owned.get('generation_source_SHA',contract['generation_source_SHA']):
                    raise PermissionError('SVR11_REUSED_MODEL_SLOT_PROVENANCE_DRIFT')
            with np.load(saved['data']['path']) as z:slots.append({f:z[f].copy() for f in FIELDS})
            continue
        progress(dict(phase='SVR11_FORECAST_MODEL_GENERATION',model_slot=t,model_slots=96,Native_Runtime=0,
            independent_compiles=count,physical_solves=solves))
        base=probe(t);mat=[np.empty((60,len(x))) for x in base]
        for j,control in enumerate(controls):
            plus=probe(t,j,1);minus=probe(t,j,-1);d=original._perturbation(control,anchor[t,j])
            for k in range(4):mat[k][j]=(plus[k]-minus[k])/(2*d)
        row={}
        for k,f in enumerate(('voltage','current','flow_p','flow_q')):
            row[f+'_constant']=base[k]-anchor[t]@mat[k]
            row[f+'_matrix']=mat[k] if k<2 else mat[k].T
        row['branch_limits']=limits
        np.savez_compressed(output/f'SLOT_{t:02d}.npz',**row)
        atomic(checkpoint,dict(day=day,source_SHA=m['execution_SHA'],data=record(output/f'SLOT_{t:02d}.npz')))
        slots.append(row)
        # All target-slot results are detached NumPy arrays. Release finished
        # probe object cycles before the next prefix; physics stays identical.
        flush_completed_probes()
        atomic(output/'MODEL_GENERATION_PROGRESS.json',dict(day=day,completed_slots=t+1,independent_compiles=count,
            physical_solves=solves,wall_seconds=time.perf_counter()-started,source_SHA=m['execution_SHA'],Actual_inputs_read=0))
    np.savez_compressed(output/'COEFFICIENTS.npz',**{f:np.array([r[f] for r in slots]) for f in FIELDS},
        node_names=nodes,branch_names=names,control_names=controls,anchor_control=anchor,rating_a=ratings,transformer_ratings=kva)
    old=read(read(Path(input_folder)/'NATIVE_INPUT.json')['electrical_certificate']['path'])
    cert=copy.deepcopy(old);ref=record(output/'COEFFICIENTS.npz')
    cert.update(schema='V42_SVR11_ELECTRICAL_CERTIFICATE_V1',day=day,source_SHA=m['execution_SHA'],scenario_SHA=scenario['scenario_SHA'],
        equipment_SHA=read(m['hardware']['path'])['equipment_SHA'],model_regenerated=True,Actual_inputs_read=0,
        control_semantics='Independent source-initial native TIME prefix for each slot/control/sign; no tap setters',
        sensitivity_semantics='Local central secant with identical unperturbed prefix; discrete AUTO response; no global nonlinear feasibility guarantee',
        output=ref,independent_compiles=count,physical_solves=solves,wall_seconds=time.perf_counter()-started,UTC=now(),
        unused_probe_EventLog_receipt_copy=False,
        reused_forecast_slot_provenance=m.get('model_checkpoint_reuse_contract'))
    cert['outputs']={k:ref for k in ('voltage','current','planning_coefficients','transformer_coefficients')}
    atomic(cert_path,cert);verify_coefficients(cert,day,load_coefficients(cert,day))
    return record(cert_path)
