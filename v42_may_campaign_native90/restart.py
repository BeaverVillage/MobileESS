"""Admit a distinct run after Native=0 build, domain and regression gates."""
from pathlib import Path
import argparse,sys
from .common import atomic,read,record,now
from .policy import VERSION,EXPECTED,source_files,digest

def create_manifest(root,authority_path):
    from v42_may_campaign.common import verify_manifest
    root=Path(root).resolve();authority_path=Path(authority_path).resolve()
    if (root/'CAMPAIGN_MANIFEST.json').exists() or (root/'dates').exists():
        raise PermissionError('NEW_RUN_ONLY_EXISTING_RUNTIME_NEVER_RESET')
    baseline=verify_manifest(authority_path)
    checks=root/'validation'
    required=['CHECKPOINT_COMPLETE_EQUIVALENCE','BUILD_MODEL_EQUIVALENCE','CHECKPOINT_INDEPENDENT_PROFILE','REQUIRED_REGRESSION']
    receipts={name:record(checks/(name+'.json')) for name in required}
    if any(read(r['path']).get('PASS') is not True for r in receipts.values()):
        raise PermissionError('ALL_INDEPENDENT_BUILD_AND_REGRESSION_GATES_REQUIRED')
    model=read(receipts['BUILD_MODEL_EQUIVALENCE']['path'])
    validation=dict(PASS=True,Native_calls=0,UTC=now(),gates=receipts,
        model_equivalence=model['verification'],scientific_authority=record(authority_path))
    atomic(checks/'IMPLEMENTATION_VALIDATION.json',validation)
    source=Path(read(authority_path.parent/'preflight_receipts/B1/2025-05-01.json')['output'])
    cache=source/'STATIC/DOMAIN/2025-05-01/PHYSICAL_DOMAIN_CACHE.json'
    sources=source_files();tasks={role:'MobileESS_V42_B1B2_P1_'+root.name+'_'+role.title()
        for role in ('coordinator','monitor','watchdog')}
    manifest=dict(schema='V42_MAY_B1_B2_NATIVE90_V2',run_id=root.name,frozen=True,
        axis=baseline['axis'],input_folders=baseline['input_folders'],sources=baseline['sources'],gates=baseline['gates'],
        source_HEAD=baseline['source_HEAD'],scientific_authority=record(authority_path),policy=EXPECTED,
        Python=sys.executable,monitor_port=8793,tasks=tasks,
        implementation=dict(version=VERSION,sources=sources,source_SHA=digest(sources)),
        implementation_validation=record(checks/'IMPLEMENTATION_VALIDATION.json'),
        physical_cache_sources={'B1/2025-05-01':dict(folder=str(source),receipt=record(cache),
            complete_domain_hashes=model['complete_domain_hashes'],model_verification=model['verification'])},
        superseded_run_id=baseline['run_id'],old_ledger_reused=False,old_completions_reused=False,UTC=now())
    atomic(root/'CAMPAIGN_MANIFEST.json',manifest)
    from .common import verify_manifest as verify_new
    verify_new(root/'CAMPAIGN_MANIFEST.json')
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);parser.add_argument('--authority',required=True)
    args=parser.parse_args();print(create_manifest(args.root,args.authority)['run_id'])
