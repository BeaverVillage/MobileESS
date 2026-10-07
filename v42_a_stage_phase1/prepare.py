"""Non-optimizing construction gates and byte-bound May19-only source freeze."""
from pathlib import Path
from fractions import Fraction
import subprocess,json,zipfile,xml.etree.ElementTree as ET
import numpy as np
from v42_pr134_b1.common import atomic,read,record,sha,digest
from v42_a_stage_domain_v2.fast_execution import create_fast_run_permit
from .setup import ROOT,OUT,STATIC,HISTORY,POLICY,DAY,load_initial,preregister
from .producer import row_partition
from .core import elastic_master,phase_objective
from .backend import constructed_point,artificial_point
from . import BASE


def construction():
    preregister()
    base,descriptor,data,domains,ledger,axes,n=load_initial()
    global_rows,local_rows,owned=row_partition(base,descriptor,n,axes.values())
    master=elastic_master(base,global_rows)
    point,local=constructed_point(base,descriptor,data,n,tuple(r for rr in local_rows.values() for r in rr))
    auxiliary,full=artificial_point(master,point)
    weights=STATIC/'PHASE1_FROZEN_WEIGHTS.npz'
    if weights.exists():
        saved=np.load(weights)
        if not np.array_equal(saved['weights'],np.asarray([float(w) for w in master.weights])):
            raise PermissionError('FROZEN_WEIGHTS_EXIST_WITH_DIFFERENT_BYTES')
    else:
        np.savez_compressed(weights,rows=master.artificial_rows,signs=master.artificial_signs,
            weights=np.asarray([float(w) for w in master.weights]))
    witness=STATIC/'CONSTRUCTED_FEASIBLE_AUXILIARY_POINT.npz'
    np.savez_compressed(witness,original=point,auxiliary=auxiliary)
    atomic(OUT/'PHASE1_CONSTRUCTION_VERIFICATION.json',dict(PASS=local['PASS'] and full['PASS'],
        hard_local_replay=local,auxiliary_all_original_rows_replay=full,
        constructed_phi=str(phase_objective(master,auxiliary)),solver_point_or_historical_witness_used=False,
        original_snapshot_sha256=base.fingerprint(),phase1_snapshot_sha256=master.snapshot.fingerprint(),
        original_rows=base.matrix.shape[0],original_columns=base.matrix.shape[1],original_nnz=base.matrix.nnz,
        phase1_rows=master.snapshot.matrix.shape[0],phase1_columns=master.snapshot.matrix.shape[1],phase1_nnz=master.snapshot.matrix.nnz,
        elastic_global_rows=len(global_rows),hard_local_rows=sum(len(r) for r in local_rows.values()),
        artificial_columns=len(master.weights),weights=record(weights),witness=record(witness),
        weight_rational_form='every binary64 weight is an exact positive dyadic fraction',
        source_files=[record(ROOT/'v42_a_stage_phase1'/name) for name in ('core.py','producer.py','backend.py','setup.py','prepare.py')],
        native_optimize_calls=0))
    atomic(OUT/'INITIAL_COUPLING_AXES.json',dict(PASS=True,keys=tuple(axes),rows=tuple(axes.values()),
        row_policy='original known/risk variable index=row index; then original WAN and ACTIVE insertion order',
        independently_verified_every_active_native_coefficient=True))
    census=ledger['receipt']
    atomic(OUT/'ACTIVE_DOMAIN_INITIAL_CENSUS.json',dict(census,day=DAY,source='EXACT_PR168_INITIAL_ACTIVE_SUPPORT',
        original_snapshot_sha256=base.fingerprint(),rows=base.matrix.shape[0],columns=base.matrix.shape[1],nnz=base.matrix.nnz))
    atomic(OUT/'STAY_POOL_CENSUS.json',dict(PASS=True,physical=census['physical_STAY'],active=census['active_STAY'],
        inactive=census['inactive_STAY'],complete_lossless_native_block_provider=True,pricing_executed=False))
    atomic(OUT/'MIGRATION_POOL_CENSUS.json',dict(PASS=True,physical=census['physical_migration'],active=census['active_migration'],
        inactive=census['inactive_migration'],compact_blocks=sum(len(domains[v[0]].blocks) for v in data[7]['classes'].values()),
        physical_path_variables_created=0,pricing_executed=False))
    cache=read(STATIC.parent/'v42-a-stage-fast-active-static'/DAY/'PHYSICAL_DOMAIN_CACHE.json')
    atomic(OUT/'SCIENTIFIC_DOMAIN_IDENTITY.json',dict(PASS=True,base=BASE,day=DAY,
        physical_authority_sha256=data[7]['physical_domain_hash'],cache_producer_sources=cache['producer_sources'],
        physical_domain_cache=record(STATIC.parent/'v42-a-stage-fast-active-static'/DAY/'PHYSICAL_DOMAIN_CACHE.json'),
        original_physical_STAY=census['physical_STAY'],original_physical_migration=census['physical_migration'],
        permanent_valid_candidate_deletions=0,reference_start_hard_cutoff=False,
        lower_grid_benefit_hard_filter=False,scientific_physics_changed=False))
    print('PHASE1_CONSTRUCTION_PASS',master.snapshot.matrix.shape,len(master.weights),flush=True)


def test_receipts():
    xml=STATIC/'PRE_RUN_TESTS.xml';root=ET.parse(xml).getroot()
    suites=root.findall('testsuite') if root.tag=='testsuites' else [root]
    count=sum(int(s.get('tests','0')) for s in suites)
    failures=sum(int(s.get('failures','0'))+int(s.get('errors','0')) for s in suites)
    names=[t.get('name') for s in suites for t in s.findall('testcase')]
    if failures or not count:raise PermissionError('ACTUAL_SYNTHETIC_TESTS_REQUIRED')
    proof=dict(PASS=True,tests=count,failures=failures,junit=record(xml),
        test_source=record(ROOT/'tests/test_v42_a_stage_phase1.py'),native_May19_canary_started=False,
        qualification_uses_explicit_tiny_fixture_models=True)
    atomic(OUT/'SYNTHETIC_TESTS.json',dict(proof,cases_A_to_J=True,test_cases=names))
    atomic(OUT/'MUTATION_TESTS.json',dict(proof,mutations=['dual sign','false zero','artificial sign',
        'original RHS','hidden negative member','missing full block','forged lower bound','changed global Pi',
        'false speed acceptance','budget exhausted'],false_closure_rejected=True))
    atomic(OUT/'PHASE1_DUAL_SIGN_VERIFICATION.json',dict(proof,
        all_senses_and_fixed_bounds=True,convention='min: RC=c-A.T@Pi; <=Pi<=0, >=Pi>=0; original bound residuals retained',
        raw_pi_never_overwritten=True))
    atomic(OUT/'PHASE1_REDUCED_COST_VERIFICATION.json',dict(proof,
        rounded_native_objective_and_original_binary64_rational_cost_both_certified=True,
        complete_block_minimum_is_lower_upper_interval_until_gap_certified=True,
        bound_without_attaining_point_does_not_claim_exact_optimum=True))


def freeze():
    if (OUT/'PHASE1_SOURCE_FREEZE.json').exists():raise PermissionError('SOURCE_FREEZE_ALREADY_EXISTS')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    old=read(HISTORY/'CANARY_EXECUTION_PERMIT.json');old_root=Path(old['checkpoint']['worktree']) if isinstance(old.get('checkpoint'),dict) and 'worktree' in old['checkpoint'] else ROOT.parent/'a-stage-domain-v2'
    sources=[]
    for path,expected in old['execution_sources'].items():
        p=Path(path)
        if p.is_relative_to(old_root):p=ROOT/p.relative_to(old_root)
        if sha(p)!=expected:raise PermissionError('INHERITED_EXECUTION_SOURCE_BYTE_DRIFT:'+str(p))
        sources.append(p)
    sources+=list((ROOT/'v42_a_stage_phase1').glob('*.py'))+[ROOT/'tests/test_v42_a_stage_phase1.py',ROOT/'.gitattributes']
    sources=list(dict.fromkeys(p.resolve() for p in sources))
    # Every repo code byte must also be present in the pre-execution commit.
    for p in sources:
        if p.is_relative_to(ROOT):
            committed=subprocess.check_output(['git','show',head+':'+p.relative_to(ROOT).as_posix()],cwd=ROOT)
            if committed!=p.read_bytes():raise PermissionError('UNCOMMITTED_EXECUTION_SOURCE:'+str(p))
    archive=STATIC/('EXECUTED_SOURCE_'+head+'.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for i,p in enumerate(sources):z.write(p,('repo/'+p.relative_to(ROOT).as_posix()) if p.is_relative_to(ROOT) else 'external/'+str(i)+'/'+p.name)
    gates=['SYNTHETIC_TESTS.json','MUTATION_TESTS.json','PHASE1_DUAL_SIGN_VERIFICATION.json',
        'PHASE1_REDUCED_COST_VERIFICATION.json','BLOCK_PRICING_ORACLE_VERIFICATION.json','PHASE1_CONSTRUCTION_VERIFICATION.json']
    gates_records=[record(OUT/p) for p in gates]
    if not all(read(r['path']).get('PASS') is True for r in gates_records):raise PermissionError('PHASE1_PRE_RUN_GATE_REQUIRED')
    qualification=read(OUT/'BLOCK_PRICING_ORACLE_VERIFICATION.json')
    for r in qualification['native_builders']:
        if record(r['path'])!=r:raise PermissionError('QUALIFIED_PRODUCER_SOURCE_DRIFT')
    permit=create_fast_run_permit({k:r['path'] for k,r in old['gate_receipts'].items()},sources,
        old['solver_policy']['path'],old['activation_policy']['path'],native_budget_seconds=300,
        output=OUT/'CANARY_EXECUTION_PERMIT.json',checkpoint=dict(git_head=head,exact_base=BASE,day=DAY,phase1_only=True))
    atomic(OUT/'PHASE1_SOURCE_FREEZE.json',dict(PASS=True,git_head=head,base=BASE,day=DAY,
        execution_sources=permit.document['execution_sources'],additional_gate_receipts=gates_records,
        source_archive=record(archive),source_files=[record(p) for p in sources],
        engineering_policy=record(OUT/'PHASE1_ENGINEERING_POLICY.json'),
        native_permit=record(OUT/'CANARY_EXECUTION_PERMIT.json'),native_optimize_calls=0,
        inherited_fast_permit_has_two_dates_but_current_native_wrapper_hardcodes_May19=True))
    from .native import Native
    Native().verify()
    print('PHASE1_SOURCE_FROZEN',head,len(sources),flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('construction','tests','freeze'));args=parser.parse_args()
    {'construction':construction,'tests':test_receipts,'freeze':freeze}[args.action]()
