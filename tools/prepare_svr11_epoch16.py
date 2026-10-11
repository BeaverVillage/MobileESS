"""User-authorized May01/May02 restart, without daily independent proof replay."""
from pathlib import Path
import ast, copy, os, shutil, subprocess, sys
SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE));sys.path.insert(0,str(SOURCE/'tools'))
from v42_pr134_b1.common import atomic, read, record, sha, digest, now
from v42_common_campaign.authority import source_files
from v42_svr11 import DAYS
OLD=Path(r'D:\v42_svr11_may_20261011_15')
ROOT=Path(r'D:\v42_svr11_may_20261011_16')
GIB=1024**3


def review(old,sources):
    previous=old['execution_sources'];code=Path(old['code_root'])
    changes={k for k in set(previous)|set(sources) if previous.get(k)!=sources.get(k)}
    expected={'v42_svr11/campaign_mode.py','v42_svr11/milp_release.py',
        'v42_may_campaign_native90/m_model.py','v42_ultracompact/current.py','v42_b3_joint/m_source.py'}
    if changes!=expected:raise ValueError('UNREVIEWED_SOURCE_CHANGE:'+repr(changes))
    for name in changes-{'v42_svr11/campaign_mode.py'}:
        before=(code/name).read_text(encoding='utf8');after=(SOURCE/name).read_text(encoding='utf8')
        if sha(code/name)!=previous[name]:raise ValueError('PREVIOUS_SOURCE_DRIFT')
        if name.endswith('/current.py'):
            first=after.index('    from v42_svr11.campaign_mode import permit, receipt\n')
            last=after.index('    proof.update(schema=',first)
            after=after[:first]+"    from .current_verify import verify_current_c3a\n    proof=verify_current_c3a(ultra,graph)\n"+after[last:]
        elif name.endswith('/m_model.py'):
            first=after.index('    from v42_svr11.campaign_mode import permit, receipt\n')
            last=after.index('    original, od = compact.original.tocsr(), compact.original_data\n',first)
            after=after[:first]+after[last:]
            after=after.replace("ultra.proof['PASS'] if ultra.proof.get('independent_model_proof_replayed',True) else None","ultra.proof['PASS']")
        elif name.endswith('/m_source.py'):
            after=after.replace("c3_proof['PASS'] if c3_proof.get('independent_model_proof_replayed',True) else None","c3_proof['PASS']")
        else:
            first=after.index("    if contract.get('schema')=='SVR11_CAMPAIGN_REUSE_VALIDATED_ALGORITHM_V1':\n")
            last=after.index("    if contract.get('schema')=='SVR11_EXACT_C3A_MINIMAL_RELEASE_V1':\n",first)
            after=after[:first]+after[last:]
        if ast.dump(ast.parse(before))!=ast.dump(ast.parse(after)):
            raise ValueError('CONSTRUCTION_ALGORITHM_CHANGED:'+name)
    return dict(source_SHA=digest(sources),previous_source_SHA=old['execution_SHA'],
        construction_algorithms_unchanged=True,user_authorized_no_daily_proof=True,
        previous_validation=record(OLD/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json'),
        source_changes=sorted(changes),review='AST identity after removing only proof replay gates and honest replay labels',
        current_matrices_and_bounds_generated_fresh=True,policy_results_reused=0,
        independent_model_proof_replay=False,UTC=now())


def forecast(old,sources):
    previous=read(old['model_checkpoint_reuse_contract']['path'])
    known={v['linked']['path']:v['linked'] for v in previous['coefficient_NTFS_hardlinks']}
    links=[];days={}
    def linked(origin,target):
        authority=known[str(origin)]
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():target.hardlink_to(origin)
        if not os.path.samefile(origin,target) or target.stat().st_size!=authority['bytes']:
            raise ValueError('IMMUTABLE_FORECAST_HARDLINK_DRIFT')
        receipt=dict(authority,path=str(target))
        links.append(dict(original=authority,linked=receipt))
        return receipt
    for day in DAYS:
        origin=OLD/'models'/day;dest=ROOT/'models'/day
        for p in origin.rglob('*'):
            if not p.is_file() or p.suffix=='.lock':continue
            target=dest/p.relative_to(origin);target.parent.mkdir(parents=True,exist_ok=True)
            if p.suffix=='.npz':linked(p,target)
            else:shutil.copyfile(p,target)
        slots={}
        for t in range(96):
            p=origin/f'SLOT_{t:02d}.json';v=read(p)
            slots[str(t)]=dict(original_checkpoint=record(p),original_data=v['data'],
                generation_source_SHA=v.get('generation_source_SHA',v['source_SHA']))
        days[day]=dict(slots=slots,certificate=record(origin/'ELECTRICAL_CERTIFICATE.json'),
            forecast_anchor={n:record(origin/'FORECAST_ANCHOR'/n)
                for n in ('B0_NEW_PLANNING_GENERATION.json','PLANNING_PHYSICAL.npz')})
    contract=dict(PASS=True,generation_source_SHA=old['execution_SHA'],
        generation_manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),validation_source_SHA=digest(sources),
        days=days,mathematical_electrical_model_changed=False,
        Forecast_generation_sources_bitwise_unchanged=True,Native_policy_results_reused=0,
        Actual_inputs_read_by_model=0,Planning_tap_or_queue_transferred_to_Actual=False,
        reused_complete_slots=2976,previous_policy_optimization_reuse=0,
        coefficient_NTFS_hardlinks=links,origin_independent_revalidation=previous['origin_independent_revalidation'],
        prior_qualified_contract=old['model_checkpoint_reuse_contract'],
        additional_numerical_proof_performed=False,UTC=now())
    path=ROOT/'MODEL_CHECKPOINT_REUSE_CONTRACT.json';atomic(path,contract);ref=record(path)
    bytarget={p['linked']['path']:p['linked'] for p in links}
    for day in DAYS:
        dest=ROOT/'models'/day;v=read(dest/'ELECTRICAL_CERTIFICATE.json')
        coefficient=bytarget[str(dest/'COEFFICIENTS.npz')]
        v.update(source_SHA=digest(sources),generation_source_SHA=v.get('generation_source_SHA',old['execution_SHA']),
            coefficient_certificate_origin_source_SHA=old['execution_SHA'],
            physical_slot_generation_SHA_by_slot={t:s['generation_source_SHA'] for t,s in days[day]['slots'].items()},
            model_reused=True,regenerated_in_current_execution_epoch=False,validation_source_SHA=digest(sources),
            original_generation_certificate=days[day]['certificate'],revalidation_contract=ref,
            reused_forecast_slot_provenance=ref,output=coefficient)
        v['outputs']={k:coefficient for k in v['outputs']};atomic(dest/'ELECTRICAL_CERTIFICATE.json',v)
        for t in range(96):
            path=dest/f'SLOT_{t:02d}.json';v=read(path)
            v.update(source_SHA=digest(sources),generation_source_SHA=days[day]['slots'][str(t)]['generation_source_SHA'],
                reused=True,revalidation_contract=ref,data=bytarget[str(dest/f'SLOT_{t:02d}.npz')])
            atomic(path,v)
    return ref


def release():
    ROOT.mkdir(exist_ok=True)
    if (ROOT/'CAMPAIGN_MANIFEST.json').exists():raise ValueError('IMMUTABLE_RELEASE_ALREADY_EXISTS')
    old=read(OLD/'CAMPAIGN_MANIFEST.json');sources=source_files();source=digest(sources)
    review_path=ROOT/'VALIDATED_CONSTRUCTION_ALGORITHM.json';atomic(review_path,review(old,sources));authority=record(review_path)
    import prepare_svr11_epoch14 as helper
    helper.OLD=OLD;helper.ROOT=ROOT
    state=dict(old=old,sources=sources,source_SHA=source)
    receipts=helper.raw_and_hardware(state)
    cache=forecast(old,sources)
    atomic(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json',dict(schema='SVR11_PREDECESSOR_DRAIN_CONTRACT_V1',
        manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),monitor_manifest=record(OLD/'CAMPAIGN_MANIFEST.json'),
        source_SHA=old['execution_SHA'],scientific_model_change=False,physical_equipment_change=False,
        qualified_completed_dates_reused=True,qualified_completed_arms_reused=['B0'],
        user_authorized_predecessor_stop=True,old_policy_results_reused=0,
        reason='User explicitly stopped old May01 and requested immediate fresh May01 and May02 B2 on two workers without daily independent proof',UTC=now()))
    atomic(ROOT/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json',dict(
        schema='SVR11_CAMPAIGN_REUSE_VALIDATED_ALGORITHM_V1',source_SHA=source,
        algorithm_version=old['algorithm_version'],A1_A2_algorithms_changed=False,M_native_limit_seconds=1800,
        previous_validated_release=record(OLD/'FULL_MILP_VALIDATION_RELEASE_CONTRACT.json'),
        validated_construction_algorithm=authority,additional_Native_validation_calls=0,UTC=now()))
    from v42_svr11.model_release import validate as model_validate
    from v42_svr11.milp_release import validate as milp_validate
    manifest=copy.deepcopy(old)
    memory=copy.deepcopy(old['B2_memory_admission'])
    memory['worker_reservation_bytes'].update(M1=7*GIB,M2=7*GIB)
    memory['system_reserve_bytes']=GIB
    manifest.update(root=str(ROOT),code_root=str(SOURCE),run_id='SVR11_FINAL_MAY_'+ROOT.name,
        execution_sources=sources,execution_SHA=source,
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip(),
        hardware=record(ROOT/'hardware/HARDWARE.json'),scenario=record(ROOT/'hardware/SCENARIO.json'),
        thermal=record(ROOT/'hardware/THERMAL.json'),input_receipts=receipts,
        implementation=dict(version=old['implementation']['version'],sources=sources),builder_original_sources=sources,
        scientific_model_validation=model_validate(ROOT,sources),full_milp_validation=milp_validate(ROOT,sources),
        predecessor_drain_contract=record(ROOT/'PREDECESSOR_DRAIN_CONTRACT.json'),model_checkpoint_reuse_contract=cache,
        worker_counts=dict(B0=old['worker_counts']['B0'],B2=2,B1=1,B3=2),
        B2_memory_admission=memory,B3_memory_admission=memory,
        independent_model_proof_replay=False,validated_construction_algorithm=authority,
        user_latest_no_proof_restart_May01_and_May02=True,
        memory_reservation_basis='7 GiB normal native worker reservation; no second independent rational proof graph; observed RAM and commit admission with 1 GiB system floor',
        UTC=now())
    atomic(ROOT/'CAMPAIGN_MANIFEST.json',manifest)
    from v42_svr11.controller import initial
    previous=read(OLD/'CAMPAIGN_LEDGER.json');ledger=initial()
    for day in DAYS:
        row=copy.deepcopy(previous['dates']['B0/'+day])
        if row['status']!='PASS':raise ValueError('QUALIFIED_B0_REQUIRED')
        row['continued_from_qualified_B0_manifest']=record(OLD/'CAMPAIGN_MANIFEST.json')
        ledger['dates']['B0/'+day]=row
    ledger.update(policy='B2',source_SHA=source,UTC=now())
    atomic(ROOT/'CAMPAIGN_LEDGER.json',ledger)
    from svr11_monitor_ui import ui_files
    atomic(ROOT/'MONITOR_UI_RELEASE.json',dict(schema='SVR11_READ_ONLY_UI_V1',files=ui_files(),Native_calls=0,UTC=now()))
    from v42_svr11.authority import verify
    verify(ROOT/'CAMPAIGN_MANIFEST.json')
    atomic(ROOT/'CAMPAIGN_WITHOUT_DAILY_PROOF_READY.json',dict(ready=True,source_SHA=source,
        prior_algorithm_validation_reused=True,independent_model_proof_replay=False,
        B2_workers=2,fresh_May01_May02=True,Native_validation_calls=0,UTC=now()))
    print(dict(root=str(ROOT),source_SHA=source,ready=True,B2_workers=2))


if __name__=='__main__':release()
