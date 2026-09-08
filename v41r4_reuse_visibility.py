"""Materialized reporting copies; never expose old Actual to a new DA worker."""
from fast_prepare import *
from v41r4_loop_runtime import MAY_RUN,MAY_OUT
from v41r4_loop_worker import retained
from dayahead.paper_analysis.storage import write_json
from dayahead.v40h.identity import verify_manifest
from dayahead.v41.scientific_archive import verify_manifest as verify_archive
import hashlib,shutil,time


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    destination=MAY_RUN/'reused_results';rows=[];total=0;count=0
    for n in range(1,32):
        day=f'2025-05-{n:02}'
        for policy in ('B0','B2'):
            row=dict(day=day,policy=policy,stages={},directory=str(destination/day/policy))
            evidence=[]
            for stage,folder in (('DA','dayahead'),('AC','actual')):
                source=retained(day,policy,stage)
                if source is None:continue
                run,out,phase=source;src=(run/day/policy/folder).resolve()
                receipt=src/('DAYAHEAD_RECEIPT.json' if stage=='DA' else 'ACTUAL_RECEIPT.json')
                r=read(receipt);assert r['status']=='COMPLETE'
                verify_manifest(r['science']);verify_archive(src/'SCIENTIFIC_MANIFEST.json')
                assert all(record(x['path'])==x for x in r['files'].values())
                dest=destination/day/policy/folder;entries=[]
                for file in sorted(src.rglob('*')):
                    if not file.is_file():continue
                    rel=file.relative_to(src);target=dest/rel
                    assert target.absolute().is_relative_to(destination)
                    target.parent.mkdir(parents=True,exist_ok=True)
                    sha=digest(file)
                    if not target.exists():shutil.copy2(file,target)
                    assert digest(target)==sha and target.stat().st_size==file.stat().st_size
                    size=target.stat().st_size;count+=1;total+=size
                    entries.append(dict(relative_path=rel.as_posix(),sha256=sha,bytes=size))
                summary_name=f'{policy}_{"DAYAHEAD" if stage=="DA" else "ACTUAL"}_SUMMARY.json'
                summary=read(out/day/summary_name);copy(out/day/summary_name,destination/day/policy/summary_name)
                row['stages'][stage]=dict(receipt=str(dest/receipt.name),summary=str(destination/day/policy/summary_name),
                    P1=summary.get('OBJECTIVE_VECTOR',[None])[0],rho_max=summary['grid']['rho_max'],
                    Vmin=summary['grid'].get('Vmin'),Vmax=summary['grid'].get('Vmax'),grid=summary['grid'])
                evidence.append(dict(stage=stage,source=record(receipt),files=entries,copy_directory=str(dest)))
            if row['stages']:
                write_json(destination/day/policy/'COPY_PROVENANCE.json',dict(status='PASS',all_file_bytes_equal=True,
                    source_paths_in_original_receipts_preserved=True,reporting_only=True,stages=evidence))
                rows.append(row);print('RESULT_FILES_COPIED',day,policy,','.join(row['stages']),flush=True)
    write_json(MAY_OUT/'REUSED_RESULTS_INDEX.json',dict(status='PASS',updated_at=time.time(),directory=str(destination),
        rows=rows,files=count,bytes=total,physical_copies=True,optimizer_input_paths_changed=False,
        existing_actual_reporting_only=True))
    (destination/'README.txt').write_text('Verified physical copies of retained B0/B2 results.\nOriginal sealed receipts retain source paths; COPY_PROVENANCE.json verifies copied bytes.\nOld Actual is displayed for reporting, and is imported into the active campaign only after all four new Day-Ahead freezes.\n',encoding='utf-8')
    print('COPY_COMPLETE',len(rows),count,total,flush=True)


if __name__=='__main__':main()
