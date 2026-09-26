"""Explicit extension-only numeric authority contract. Never alters old manifests."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import runtime_environment as env

OUT=env.ROOT/'authority_recovery'
MISSING={
 'V40E_CORRECTED_APRIL_FULL_BUS_PHASE_SENSITIVITY.parquet':('b316bc7316bdd42cfaba2f05e6386ed2d1151cf4f0c34119564b15b101112c53',12700794),
 'V40E_CORRECTED_APRIL_LOCAL_SENSITIVITY.parquet':('41eba629845ffdb70a55cba29c39121b7667e5a4acfc5b27c24d0b74a10f3309',2305380),
}
PASS='IEEE123_PRE_RESITE_V41R4_NUMERIC_AUTHORITY_RECOVERY_PASS'

def sha(p):
    with env.OLD_OPEN(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(p):
    with env.OLD_OPEN(p,encoding='utf-8') as f:return json.load(f)

def save(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')

def leaves(x):
    if isinstance(x,dict):
        if {'path','bytes','sha256'}<=x.keys():yield x
        for v in x.values():yield from leaves(v)
    elif isinstance(x,(list,tuple)):
        for v in x:yield from leaves(v)

def missing_leaf(ref):
    expected=MISSING.get(Path(ref['path']).name)
    return expected is not None and (ref['sha256'],ref['bytes'])==expected

def main():
    started=time.time();OUT.mkdir(exist_ok=True);env.seed_aliases()
    # These are historical receipts, not replaced with a success result.
    history={n:sha(env.ROOT/n) for n in ['AUTHORITY_LOCK.json','CONTEXT_PREFLIGHT.json','PREFLIGHT_GATE.json']}
    save('ORIGINAL_FAILURE_RECORD_BINDINGS.json',history)
    subprocess.run([sys.executable,str(env.ROOT/'audit_preserved_operating_coefficients.py')],check=True)
    numeric=read(env.ROOT/'april_regeneration/ORIGINAL_OPERATING_COEFFICIENTS_AUDIT.json')
    assert numeric['output_files_verified']==124 and numeric['gradient_values_checked']==10285056
    assert numeric['unequal_gradient_values']==0
    save('ORIGINAL_OPERATING_COEFFICIENTS_RECHECK.json',numeric)
    intake=read(env.ROOT/'AUTHORITY_INTAKE.json');traffic=read(env.ROOT/'M1_TRAFFIC_AND_SETTINGS.json')
    refs={};categories={}
    def add(label,value):
        for ref in leaves(value):
            key=(ref['path'],ref['sha256'],ref['bytes']);refs[key]=ref
            categories.setdefault(key,set()).add(label)
    for d in intake['days']:
        add('mapping_PCC',d['mapping']);add('electrical_certificate',d['electrical_authority'])
        add('workload_ML',d['workload_traffic_snapshot']);add('input_manifest',d['input_manifest'])
        for key in ['electrical_authority','input_manifest','workload_traffic_snapshot']:
            add(key+'_transitive',read(env.read_path(d[key]['path'])))
    for t in traffic:add('traffic_mapping_mobility',t)
    matched=[];missing=[];fail=[]
    for key,ref in refs.items():
        if missing_leaf(ref):
            missing.append(dict(**ref,status='MISSING_ORIGINAL_HISTORICAL_LINEAGE',production_usage='FORBIDDEN'));continue
        try:
            p=Path(env.read_path(ref['path']));actual=sha(p)
            assert actual==ref['sha256'] and env.OLD_STAT(p).st_size==ref['bytes'],'SHA_OR_SIZE_DIFFERENCE'
            matched.append(dict(**ref,resolved_path=str(p),categories=sorted(categories[key])))
        except Exception as e:fail.append(dict(**ref,error=repr(e)))
    freeze=read(env.ROOT/'M2_ROUND1_FINAL_BOUNDARY_FREEZE.json')
    for d in freeze['days']:
        p=Path(env.read_path(d['input_joint']));v=read(p)
        # File pin is also covered by the protected inventory below.
        payload=json.dumps(v['decision'],sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n'
        assert hashlib.sha256(payload.encode()).hexdigest()==v['decision_SHA']
        assert v['decision']['day']==d['day']
    save('TRANSITIVE_AUTHORITY_RECHECK.json',dict(matched=matched,missing_historical=missing,failures=fail))
    assert not fail,repr(fail[:3])
    assert {Path(r['path']).name for r in missing}==set(MISSING)
    subprocess.run([sys.executable,str(env.ROOT/'verify_preservation.py')],check=True)
    preservation=read(env.ROOT/'PRESERVATION_VERIFICATION.json');assert preservation['status']=='PASS'
    save('PROTECTED_ARTIFACTS_RECHECK.json',preservation)
    assert history=={n:sha(env.ROOT/n) for n in history}
    contract=dict(schema='B3_2R_EXPLICIT_AUTHORITY_RECOVERY_V1',status=PASS,created_unix=time.time(),
        FINAL_OPERATING_AUTHORITY='ORIGINAL_SHA_VERIFIED',HISTORICAL_LINEAGE_COMPLETE=False,
        REGENERATED_SENSITIVITY_PARQUETS='DIAGNOSTIC_ONLY',PRODUCTION_NUMERIC_INPUTS='ORIGINAL_FINAL_COEFFICIENTS_ONLY',
        original_final_coefficient_files=124,planning_gradient_values=10285056,unequal_gradient_values=0,
        original_joint_authority_exact=True,mapping_PCC_exact=True,workload_traffic_authority_exact=True,
        verified_transitive_leaves=len(matched),missing_historical_lineage=missing,
        regenerated_sensitivity_production_usage=0,protected_artifacts_unchanged=True,
        original_loader_failure_records=history,original_verify_file_unchanged=True,
        extension_validator_policy='Only the two exact named historical SHA/size references may be documented as missing; every other leaf and every manifest digest must verify.',
        round2_boundary='existing paper-used final accepted DA/Fresh physical-closure joint; excludes Actual and QSAFE',
        boundary_freeze_sha256=sha(env.ROOT/'M2_ROUND1_FINAL_BOUNDARY_FREEZE.json'),
        round1_solver_calls=0,May_solver_calls=0,preflight_status='NOT_RUN',production_status='NOT_RUN',
        wall_seconds=time.time()-started)
    save('RECOVERY_CONTRACT.json',contract)
    print(PASS,flush=True)

def install_validator():
    """Add a named alternative validator; do not fake verify_file() success."""
    c=read(OUT/'RECOVERY_CONTRACT.json');assert c['status']==PASS
    for n,h in c['original_loader_failure_records'].items():assert sha(env.ROOT/n)==h
    import dayahead.v40h.identity as identity
    original=identity.verify_bound_files
    def verify_numeric_authority_with_documented_missing_lineage(value):
        seen=set();missing=[]
        def walk(node):
            if isinstance(node,dict):
                if {'path','bytes','sha256'}<=node.keys():
                    key=(node['path'],node['bytes'],node['sha256'])
                    if key not in seen:
                        if missing_leaf(node):missing.append(node)
                        else:identity.verify_file(node)
                        seen.add(key)
                if {'manifest_SHA','files'}<=node.keys():
                    identity.require(node['manifest_SHA']==identity.digest(node['files']),'BOUND_MANIFEST_CONTENT_DRIFT')
                for v in node.values():walk(v)
            elif isinstance(node,(list,tuple)):
                for v in node:walk(v)
        walk(value)
        env.LINEAGE_EXCEPTIONS.update((r['path'],r['sha256']) for r in missing)
        return len(seen)-len(missing)
    identity.verify_bound_files=verify_numeric_authority_with_documented_missing_lineage
    return original

if __name__=='__main__':main()
