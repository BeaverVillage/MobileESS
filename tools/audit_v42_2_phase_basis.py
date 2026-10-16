"""Read back an extended basis on the actual failed S1 matrix, without Optimize."""
import json
from pathlib import Path
import numpy as np


def audit(state,predecessor,output):
    from v42_a_stage_phase1.core import elastic_master,primal_replay
    from v42_a_stage_phase1.backend import artificial_point
    from v42_a_stage_compact_rowgen.rowgen import restricted
    from v42_a_stage_domain_v2.stress_backend import materialize
    from v42_integration.pcc_definitions import hard_rows
    from v42_integration.table_v_phase_diagnostics import extend_basis,basis_admission
    from v42_integration.d0_resource import native_binding
    from v42_integration.m_engine import _write,file_record
    prior=Path(predecessor).resolve();output=Path(output);output.mkdir(parents=True,exist_ok=False)
    root=prior/'B1/A1/DW';s=state['compact'];G=state['grows'];definitions=hard_rows(state)
    included=set(range(len(G),s.matrix.shape[0]))|set(state['axes'].values())|definitions
    activity=s.matrix@state['prior_compact']-s.rhs
    nonzero=np.diff(s.matrix.indptr[:len(G)+1])>0
    included.update(np.flatnonzero(nonzero&(abs(activity[:len(G)])<=1e-6)))
    full=elastic_master(s,tuple(i for i in G if i not in definitions))
    p,replay=artificial_point(full,state['prior_compact'])
    if not replay['PASS']:raise ValueError('BASIS_NATIVE0_INITIAL_WITNESS')
    contributions=np.zeros(len(G))
    for i,w,x in zip(full.artificial_rows,full.weights,p[s.matrix.shape[1]:]):contributions[i]+=float(w)*x
    included.update(np.argsort(-contributions,kind='stable')[:50])
    masters=[];records=[]
    separation=json.loads((root/'PHASE_I/S0/ROW_SEPARATION.json').read_text())
    for i in range(2):
        rows=tuple(sorted(included));r=restricted(s,rows)
        master=elastic_master(r,tuple(j for j,k in enumerate(rows) if k<len(G) and k not in definitions))
        identity=root/f'PHASE_I/S{i}/SOURCE18R_FAST/MODEL_IDENTITY.json'
        if master.snapshot.fingerprint()!=json.loads(identity.read_text())['original_snapshot_sha256']:
            raise ValueError('BASIS_NATIVE0_EXACT_ACTUAL_SNAPSHOT_REQUIRED')
        masters.append(master);records.append(file_record(identity))
        included.update(separation['violated_rows'])
    ledger_path=prior/'PLANNING_NATIVE_LEDGER.json';ledger=json.loads(ledger_path.read_text())
    if ledger['inflight'] is not None:raise ValueError('BASIS_NATIVE0_PRIOR_CALL_MUST_BE_RECONCILED')
    native=json.loads((root/'PHASE_I/S0/SOURCE18R_FAST/NATIVE_RESULT.json').read_text())
    if native['status']!=2 or not native['independent_numerical_validation']['PASS']:
        raise ValueError('BASIS_NATIVE0_ACTUAL_ACCEPTED_NATIVE_BASIS_REQUIRED')
    raw_path=root/'PHASE_I/S0/SOURCE18R_FAST/RAW_ATTRIBUTES.npz'
    with np.load(raw_path) as data:raw={k:data[k] for k in data.files}
    vb,cb,proof=extend_basis(masters[0].snapshot,masters[1].snapshot,raw)
    admission=basis_admission(proof)
    import gurobipy as gp
    model,objectives=materialize(masters[1].snapshot,'2025-05-01')
    try:
        model.setObjective(objectives[0][1],gp.GRB.MINIMIZE);model.Params.Threads=1
        model.Params.LPWarmStart=2;model.update()
        model.setAttr('VBasis',vb.tolist());model.setAttr('CBasis',cb.tolist());model.update()
        exact=(np.array_equal(model.getAttr('VBasis'),vb) and np.array_equal(model.getAttr('CBasis'),cb))
        binding=native_binding(model)
        previous=json.loads((root/'PHASE_I/S1/SOURCE18R_FAST/NATIVE_RESULT.json').read_text())['ledger_call']['native_binding']
        if binding!=previous or not exact:raise ValueError('BASIS_NATIVE0_NATIVE_MATRIX_OR_BASIS_READBACK_DRIFT')
        # Read back the selected production parameters on the same exact model.
        # Positive elastic pivots use the actual original basis with primal
        # simplex and no presolve crushing. No Optimize call is made here.
        model.Params.Method=2
        for k,v in admission['parameters'].items():model.setParam(k,v)
        selected={k:int(getattr(model.Params,k)) for k in ('Method','LPWarmStart','Presolve')}
        if admission['primal_simplex_required'] and selected!={'Method':0,'LPWarmStart':1,'Presolve':0}:
            raise ValueError('BASIS_NATIVE0_ORIGINAL_PRIMAL_POLICY_READBACK_DRIFT')
        model.update()
        if not (np.array_equal(model.getAttr('VBasis'),vb) and np.array_equal(model.getAttr('CBasis'),cb)):
            raise ValueError('BASIS_POLICY_DISCARDED_ACTUAL_NATIVE_BASIS')
        if native_binding(model)!=previous:raise ValueError('BASIS_POLICY_CHANGED_NATIVE_MATRIX_DOMAIN_OBJECTIVE')
    finally:model.dispose()
    result=dict(PASS=True,Native_calls=0,proof=proof,actual_S0_S1_exact_snapshots=True,
        native_matrix_domain_objective_unchanged=True,native_basis_exact_readback=exact,
        prior_finalized_ledger=file_record(ledger_path),actual_native_basis=file_record(raw_path),
        actual_model_identities=records,native_binding=binding,
        selected_basis_admission=admission,selected_native_parameters=selected,
        original_FULL_UB_claimed=False,PStart_DStart_installed=False,
        solver_performance_improvement_claimed=False)
    _write(output/'RESULT.json',result)
    return result
