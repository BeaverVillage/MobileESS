"""Readback gates and namespace preparation; never optimize B0 or completed B1."""
import os, sys, json, shutil, time, subprocess, hashlib
from pathlib import Path
R=Path(__file__).resolve().parent;W=R/'v41r4';sys.path.insert(0,str(W))
from v41r4_windows_paths import install_long_file_operations
install_long_file_operations()
from fast_prepare import read, record
from dayahead.paper_analysis.storage import write_json
from v41r4_900_namespace import OLD,RUN,OUT,ACTUAL,OLD_ACTUAL
E=R/'manifests/per_mess_900s';E.mkdir(exist_ok=True)


def link(path,target):
    path=Path(path);target=Path(target).resolve()
    assert path.absolute().is_relative_to(R) and target.is_relative_to(R)
    if path.exists():assert path.resolve()==target;return
    path.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,IEEE123_LINK_PATH=str(path),IEEE123_LINK_TARGET=str(target))
    subprocess.run(['powershell.exe','-NoProfile','-Command',
        "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:IEEE123_LINK_PATH -Target $env:IEEE123_LINK_TARGET | Out-Null"],
        env=env,check=True,capture_output=True)


def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():assert record(source)['sha256']==record(target)['sha256'];return
    shutil.copyfile(source,target)


def audit():
    import v41r4_loop_runtime as loop
    from mission_loop_archive import install
    install()
    from dayahead.v40h.identity import verify_manifest
    from v41r4_resited_binding import verify_resited
    references={};issues=[];days=[]
    def refs(value):
        if isinstance(value,dict):
            if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
                p=Path(value['path']).resolve();references[str(p)]=(p,value['sha256'])
            for v in value.values():refs(v)
        elif isinstance(value,list):
            for v in value:refs(v)
    release=read(OLD/'audit/MAY_CAMPAIGN_RELEASE_V4.json');verify_manifest(release['source']);refs(release)
    # All original producer/model/ranking/physical source bytes are included.
    for p in list(W.glob('*.py'))+list((W/'dayahead').rglob('*.py')):
        if p.name.startswith(('v41r4_900','v41r4_per_mess','test_per_mess')):continue
        references[str(p.resolve())]=(p,record(p)['sha256'])
    for n in range(1,32):
        day=f'2025-05-{n:02}';row=dict(day=day,B0='REUSE',B1='REUSE' if n<=8 else 'NEW_AUTHORIZED')
        certificate=W/'frozen_artifacts/v41r4_may/e'/day.replace('-','')/'RESITED_ELECTRICAL_CERTIFICATE.json'
        electrical=read(certificate);verify_resited(electrical,day);refs(electrical);refs(record(certificate))
        refs(read(OLD/'audit'/day/'INPUT_PREPARATION.json'))
        for policy in ('B0','B1'):
            da=OLD/day/policy/'dayahead';phase=OLD/'audit'/day/f'PHASE_{policy}_DA.json'
            if policy=='B1' and n>8:
                assert not (da/'DAYAHEAD_RECEIPT.json').exists();continue
            assert read(phase)['status']=='PASS'
            loop.verify_old_or_current(day,policy)
            r=read(da/'DAYAHEAD_RECEIPT.json');refs(r);refs(record(da/'DAYAHEAD_RECEIPT.json'))
            refs(record(da/'SCIENTIFIC_MANIFEST.json'))
            row[policy+'_DA']=record(da/'DAYAHEAD_RECEIPT.json')
            row[policy+'_AC']='NEW_REPLAY_ONLY'
            ac=OLD/'audit'/day/f'PHASE_{policy}_AC.json'
            if ac.exists() and read(ac)['status']=='PASS':
                value=read(ac);refs(value)
                candidate=value['result'].get('actual_receipt')
                if candidate:
                    assert record(candidate['path'])==candidate
                    receipt=read(candidate['path']);base=Path(candidate['path']).parent
                    for name,sha in receipt['files'].items():
                        p=base/name;assert record(p)['sha256']==sha
                        references[str(p.resolve())]=(p,sha)
                row[policy+'_AC']='REUSE'
        days.append(row)
        print('REUSE_VERIFIED',day,flush=True)
    for p in (R/'mess_cache').glob('2025-05-*/*/search/M1_IDENTITY.json'):
        refs(read(p));refs(record(p))
    rows=[]
    for p,expected in references.values():
        current=record(p)
        if current['sha256']!=expected:issues.append(dict(path=str(p),expected=expected,actual=current['sha256']))
        rows.append(current)
    value=dict(status='PASS' if not issues else 'FAIL',days=days,files=rows,mismatches=issues,
        captured_at=time.time(),source_edits=0,optimizer_calls=0)
    write_json(E/'SCIENTIFIC_AND_REUSE_BEFORE.json',value)
    assert not issues,issues[:5]
    print('AUTHORITY_AND_REUSE_PASS',len(rows),flush=True)


def restore_attested_log():
    da=OLD/'2025-05-08/B1/dayahead'
    entry=next(r for r in read(da/'SCIENTIFIC_MANIFEST.json')['artifacts'] if r['relative_path']=='A0/SOLVER.log')
    path=da/'A0/SOLVER.log';body=path.read_bytes();prefix=body[:entry['bytes']]
    assert hashlib.sha256(prefix).hexdigest()==entry['sha256']
    dest=E/'MAY08_B1_POSTSEAL_LOG';dest.mkdir(exist_ok=True)
    full=dest/'SOLVER.complete_with_postseal_tail.log'
    if full.exists():assert full.read_bytes()==body
    else:full.write_bytes(body)
    (dest/'POSTSEAL_TAIL.log').write_bytes(body[entry['bytes']:])
    write_json(dest/'RECOVERY.json',dict(status='PASS',original_full=record(full),attested=entry,
        postseal_bytes=len(body)-len(prefix),scientific_changes=0,optimizer_calls=0))
    if len(body)!=len(prefix):
        temporary=path.with_suffix('.log.recovered');temporary.write_bytes(prefix);os.replace(temporary,path)
    assert record(path)['sha256']==entry['sha256']


def prepare():
    audit=read(E/'SCIENTIFIC_AND_REUSE_BEFORE.json');assert audit['status']=='PASS'
    OUT.mkdir(parents=True,exist_ok=True)
    for p in (OLD/'audit').glob('MAY_CAMPAIGN_RELEASE*.json'):copy(p,OUT/p.name)
    for row in audit['days']:
        day=row['day'];source=OLD/'audit'/day;dest=OUT/day;dest.mkdir(exist_ok=True)
        for p in source.iterdir():
            if any(key in p.name for key in ('B2','B3')):continue
            if p.is_dir():
                if p.name in ('domain','screen'):link(dest/p.name,p)
            elif p.suffix in ('.json','.npz'):
                copy(p,dest/p.name)
        for policy in ('B0','B1'):
            if policy+'_DA' not in row:continue
            link(RUN/day/policy/'dayahead',OLD/day/policy/'dayahead')
            receipt=row[policy+'_DA'];producer=dict(science=read(receipt['path'])['science'],source=receipt,
                reuse_contract='VERIFIED_SAME_FROZEN_MAPPING_ELECTRICAL_AUTHORITY')
            write_json(dest/f'REUSED_DA_PRODUCER_{policy}.json',producer)
        assert not (RUN/day/'B2').exists() and not (RUN/day/'B3').exists()
    ACTUAL.mkdir(exist_ok=True)
    for p in OLD_ACTUAL.iterdir():
        if p.is_file() and p.suffix in ('.py','.json'):copy(p,ACTUAL/p.name)
    link(ACTUAL/'frozen_code',OLD_ACTUAL/'frozen_code')
    write_json(OUT/'REUSE_PLAN.json',audit['days'])
    write_json(E/'NAMESPACE_READY.json',dict(status='READY',RUN=str(RUN),ACTUAL=str(ACTUAL),
        B0_reoptimized=0,B1_completed_reoptimized=0,B1_new_days=list(range(9,32)),
        old_B2_B3_decisions_reused=0,old_candidate_cache_reused=0))
    print('CLEAN_NAMESPACE_READY',RUN,flush=True)


if __name__=='__main__':globals()[sys.argv[1]]()
