"""Publication-only manifests; never imports or starts an optimizer."""
from pathlib import Path
import subprocess
from v42_pr134_b1.common import read,record,atomic

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'docs/v42_a_stage_phase1_pricing_20261007'


def manifest():
    external=[]
    for name in ('PHASE1_SOURCE_FREEZE.json','PHASE1_SOURCE_FREEZE_CONTINUATION_001.json'):
        external.append(read(OUT/name)['source_archive'])
    construction=read(OUT/'PHASE1_CONSTRUCTION_VERIFICATION.json')
    external.extend(construction[k] for k in ('weights','witness'))
    external.extend(r['external_full_block_cache'] for r in read(OUT/'BLOCK_PRICING_ORACLE_VERIFICATION.json')['records'])
    for call in read(OUT/'MAY19/NATIVE_CALLS.json')['calls']:
        identity=read(call['model_identity']['path'])
        external.extend((call['raw_attributes'],identity['matrix'],identity['attributes']))
    unique={r['path']:r for r in external}
    for r in unique.values():
        if record(r['path'])!=r:raise ValueError('EXTERNAL_PUBLISHED_BYTE_DRIFT:'+r['path'])
    paths=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name!='SHA256_MANIFEST.json')
    files=[dict(record(p),repo_path=p.relative_to(ROOT).as_posix()) for p in paths]
    source=[record(p) for p in sorted((ROOT/'v42_a_stage_phase1').glob('*.py'))]
    atomic(OUT/'SHA256_MANIFEST.json',dict(schema='PHASE1_PUBLICATION_MANIFEST_V1',
        documentary_source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        exact_base='9336d8f7fba243df86e8dff0276e70942855039c',
        files=files,external_immutable_artifacts=list(unique.values()),current_source_files=source,
        native_execution_sources_authority='versioned PHASE1_SOURCE_FREEZE*.json and their immutable ZIPs',
        excluded_self='SHA256_MANIFEST.json',final_publication_head_authority='external FINAL_PUBLICATION_RECEIPT.json'))
    print('MANIFEST_VERIFIED',len(files),len(unique),flush=True)


if __name__=='__main__':manifest()
