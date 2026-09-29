"""First pass is filesystem metadata only, including both nested roots. No raw hashing."""
from common14 import *
import subprocess,re,collections


def family(path):
    s=str(path).lower()
    if 'raddit' in s:return 'RADDIT'
    if 'dataset.zip'==path.name or 'genai' in s or 'generative ai' in s:return 'GENAI_POWER'
    if 'h100_b200' in s or 'h100b200' in s:return 'H100_B200_POWER'
    if 'kestrel' in s:return 'KESTREL_JOBS'
    if 'scheduler_authority' in s:return 'NLR_SCHEDULER_DOCUMENTATION'
    if 'eagle' in s:return 'EAGLE'
    if 'pue' in s or 'it_power' in s or 'it power' in s:return 'NLR_FACILITY'
    if 'untangling' in s:return 'UNTANGLING_GPU_POWER'
    if 'cordoba' in s:return 'CORDOBA_POWER_QUALITY'
    if any(x in s for x in ['alibaba','azure','burstgpt']):return next(x.upper() for x in ['alibaba','azure','burstgpt'] if x in s)
    if 'noaa' in s or '기상' in s or '외기' in s:return 'WEATHER'
    if '데이터 센터' in s:return 'DATACENTER_UNCLASSIFIED'
    return 'NON_RUNTIME_'+path.relative_to(RAW_A).parts[0]


def main():
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip()==BASE
    preservation=ROOT/'BASE_PRESERVATION_RECEIPT.json'
    if not preservation.exists():
        tracked=subprocess.check_output(['git','ls-files','-z'],cwd=REPO).decode().split('\0')
        old=[p for p in tracked if re.match(r'docs/runtime_vnext(?:[6-9]|1[0-3])_',p)]
        records=[dict(relative=p,**record(REPO/p)) for p in old]
        manifests=[p for p in old if p.endswith('/DELIVERY_MANIFEST.json')]
        for p in manifests:
            parent=(REPO/p).parent
            for item in read(REPO/p)['files']:assert sha(parent/item['relative'])==item['sha256']
        write('BASE_PRESERVATION_RECEIPT.json',dict(time=now(),base=BASE,tracked_prior_files=len(old),prior_manifests=manifests,
            files=records,initial_worktree_clean=True,PR85_head=BASE,PR85_base='codex/runtime-vnext12-causal-regime-runtime'))
    errors=[];rows=[]
    def error(e):errors.append(str(e))
    # Extended paths avoid Windows MAX_PATH failures; lstat inventories links without following targets.
    for directory,dirs,files in os.walk('\\\\?\\'+str(RAW_A),onerror=error,followlinks=False):
        for name in files:
            physical=Path(directory)/name
            p=Path(str(physical).removeprefix('\\\\?\\'))
            try:st=physical.lstat()
            except OSError as e:errors.append(str(e));continue
            rel=p.relative_to(RAW_A);fam=family(p);nested=RAW_B in p.parents
            sid='SRC_'+hashlib.sha256(str(rel).encode()).hexdigest()[:16]
            category=('A. SAME_KESTREL_JOB_LEVEL' if fam in ['KESTREL_JOBS','RADDIT'] else
                'E. OTHER_HPC_SYSTEM' if fam=='EAGLE' else
                'G. GRID / TRAFFIC / WEATHER / NON_RUNTIME' if fam.startswith('NON_RUNTIME_') or fam=='WEATHER' else
                'H. UNKNOWN_REQUIRES_FORENSIC')
            rows.append(dict(source_id=sid,root='ROOT_A;ROOT_B' if nested else 'ROOT_A',relative_path=rel.as_posix(),filename=name,
                extension=''.join(p.suffixes),size_bytes=st.st_size,directory=str(p.parent),file_type=p.suffix.lower() or 'no_extension',
                source_system='UNVERIFIED',source_category=category,dataset_family=fam,data_granularity='UNASSESSED',
                schema_available=False,timestamp_columns='',job_identifier_columns='',candidate_runtime_relevance=fam,
                record_content_inspected=False,notes='Filesystem metadata only; ROOT_B is nested in ROOT_A and counted once.',
                mtime_ns=st.st_mtime_ns))
    frame=pd.DataFrame(rows).sort_values('relative_path').reset_index(drop=True)
    frame.to_csv(ROOT/'RAW_SOURCE_INVENTORY.csv',index=False)
    write('RAW_INVENTORY_RECEIPT.json',dict(time=now(),ROOT_A=str(RAW_A),ROOT_B=str(RAW_B),
        ROOT_A_files=len(frame),ROOT_B_files=int(frame.root.str.contains('ROOT_B').sum()),physical_files=len(frame),
        total_bytes=int(frame.size_bytes.sum()),families=frame.dataset_family.value_counts().to_dict(),errors=errors,
        complete=not errors,raw_content_read=False,raw_files_hashed=False,May_outcomes_decoded=False))
    # This is a candidate duplicate grouping, not a content-equivalence claim.
    groups=[]
    for (name,size),part in frame.groupby(['filename','size_bytes']):
        if len(part)>1:
            group='DUP_'+hashlib.sha256((name+str(size)).encode()).hexdigest()[:12]
            for _,row in part.iterrows():groups.append(dict(group_id=group,source_id=row.source_id,dataset_family=row.dataset_family,
                duplicate_basis='same filename and size; content equality not yet proven',independent_information=False))
    pd.DataFrame(groups,columns=['group_id','source_id','dataset_family','duplicate_basis','independent_information']).to_csv(ROOT/'RAW_SOURCE_GROUPS.csv',index=False)
    print(frame.groupby('dataset_family').agg(files=('source_id','size'),bytes=('size_bytes','sum')).to_string(),flush=True)
    print('INVENTORY_ERRORS',len(errors),errors[:3],flush=True)


if __name__=='__main__':main()
