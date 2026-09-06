from pathlib import Path
import shutil
from dayahead.paper_analysis.storage import read,sha,write_json,reference

REL=Path('dayahead/artifacts/v40g_segment_integration')
OLD=Path('dayahead/artifacts/v40g_joint_aidc')
REQUEST=Path('C:/Users/kjw39/.codex/attachments/f1f6400a-980d-4761-9f97-69f44589ac90/pasted-text.txt')


def initialize(repo):
    repo=Path(repo);root=repo/REL;root.mkdir(parents=True,exist_ok=True)
    manifest=root/'PRESERVED_V40G.json'
    if not manifest.exists():
        files=[p for p in (repo/OLD).rglob('*') if p.is_file()]+list((repo/'dayahead/v40g').glob('*.py'))
        write_json(manifest,{'files':{str(p):sha(p) for p in sorted(files)}})
    for name in ('common_service','electrical','april_joint_authority'):
        if not (root/name).exists():shutil.copytree(repo/OLD/name,root/name)
    if not (root/'INITIAL_INTERPRETATION_HOLD.json').exists():
        write_json(root/'INITIAL_INTERPRETATION_HOLD.json',{'status':'SCIENTIFIC_INTERPRETATION_HOLD',
            'V40G_ACTUAL_SCIENCE_INTERPRETATION':'HOLD','scope':'Current V40G May-01 Fresh/Actual migration result',
            'request':reference(REQUEST),'B2_B3_AUTHORIZED':'NO','FULL_MAY_AUTHORIZED':'NO'})
    return root


def context(repo):
    from dayahead.v40e import electrical
    old=electrical.REL;electrical.REL=REL;electrical.upstream.cache_clear()
    try:return electrical.planning_context(Path(repo).resolve(),'2025-05-01')
    finally:electrical.REL=old;electrical.upstream.cache_clear()


def verify_preserved(repo):
    root=Path(repo)/REL;files=read(root/'PRESERVED_V40G.json')['files']
    changed=[p for p,h in files.items() if not Path(p).exists() or sha(p)!=h]
    assert not changed,changed
    return {'status':'PASS','files':len(files),'changed_files':0}
