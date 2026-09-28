"""Capture authoritative source bytes and scoped search receipts, not model results."""
from common7 import *
import urllib.request,datetime,subprocess,re,concurrent.futures
URLS={
 'NLR_catalog':'https://data.nlr.gov/submissions/302',
 'sacct_current':'https://slurm.schedmd.com/sacct.html',
 'scontrol_current':'https://slurm.schedmd.com/scontrol.html',
 'sbatch_current':'https://slurm.schedmd.com/sbatch.html',
 'slurm_man_version':'https://slurm.schedmd.com/man_index.html',
 'slurm2311_update_job':'https://raw.githubusercontent.com/SchedMD/slurm/slurm-23-11-10-1/src/scontrol/update_job.c',
 'slurm2311_job_mgr':'https://raw.githubusercontent.com/SchedMD/slurm/slurm-23-11-10-1/src/slurmctld/job_mgr.c',
 'slurm2311_sacct_man':'https://raw.githubusercontent.com/SchedMD/slurm/slurm-23-11-10-1/doc/man/man1/sacct.1',
 'slurm2311_accounting_mysql':'https://raw.githubusercontent.com/SchedMD/slurm/slurm-23-11-10-1/src/plugins/accounting_storage/mysql/as_mysql_job.c',
 'hpc_descriptor':'https://raw.githubusercontent.com/NatLabRockies/hpc-oda-commons/218d75f56b783ebfd698100f9406cfb46fa04c01/src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml',
 'hpc_feature_policy':'https://raw.githubusercontent.com/NatLabRockies/hpc-oda-commons/218d75f56b783ebfd698100f9406cfb46fa04c01/src/hpc_oda_commons/models/feature_policy.py'}
def main():
    dest=LOCAL/'authority';dest.mkdir(parents=True,exist_ok=True)
    def fetch(item):
        key,url=item;p=dest/(key+'.source')
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'Runtime feature provenance audit'})
            with urllib.request.urlopen(req,timeout=40) as r:data=r.read();headers=dict(r.headers);final=r.url
            p.write_bytes(data)
            return dict(key=key,url=url,final_url=final,downloaded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),http_last_modified=headers.get('Last-Modified'),status='OK',**record(p))
        except Exception as e:return dict(key=key,url=url,status='FETCH_FAILED',reason=str(e))
    with concurrent.futures.ThreadPoolExecutor(4) as pool:remote=list(pool.map(fetch,URLS.items()))
    local=[RAW.parent/'datacard.md',AUTH/'README_MobileESS.txt',AUTH/'99_manifest/download_info.txt',AUTH/'99_manifest/repos.tsv',
       HPC/'src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml',HPC/'src/hpc_oda_commons/datasets/normalize.py',
       HPC/'src/hpc_oda_commons/ingest/jobs_parquet/apply.py',HPC/'src/hpc_oda_commons/ingest/jobs_parquet/wizard.py',
       HPC/'src/hpc_oda_commons/kernel/transformations.py',HPC/'src/hpc_oda_commons/models/feature_policy.py',
       HPC/'src/hpc_oda_commons/adapters/slurmctld/adapter.py',HPC/'tests/unit/test_slurmctld_parser.py']
    write('AUTHORITY_SOURCE_RECEIPTS.json',dict(remote=remote,local=[record(p) for p in local if p.exists()],
      important='Upstream Slurm code illustrates semantics; installed historical Kestrel Slurm version/config unknown. hpc-oda is downstream of the published ZIP. No private DB pipeline recovered.',
      NLR_public_pipeline='sacct periodic capture -> PostgreSQL load_slurm -> DB triggers/batches -> internal anonymization/export -> published Parquet -> hpc-oda normalization -> MobileESS normalized features'))
    commands=[(['gh','search','code','load_slurm','--owner','NatLabRockies','--limit','30','--json','path,repository,url'],None),
      (['gh','search','code','load_slurm','--owner','NREL','--limit','30','--json','path,repository,url'],None),
      (['gh','search','code','slurm_data','--owner','NatLabRockies','--limit','30','--json','path,repository,url'],None),
      (['git','log','--all','-G','load_slurm|set_job_calc|upd_calc_cols','--format=%h %s','--','src','docs'],HPC),
      (['git','log','--all','--format=%h %ad %s','--date=iso-strict','--','src/hpc_oda_commons/datasets/descriptors/job-runtime/nlr_kestrel.yml'],HPC),
      (['git','rev-list','--all','--count'],HPC)]
    receipts=[]
    for cmd,cwd in commands:
        r=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace');receipts.append(dict(command=cmd,cwd=str(cwd),returncode=r.returncode,stdout=r.stdout,stderr=r.stderr))
    write('SEARCH_AUTHORITY_RECEIPTS.json',dict(searches=receipts,local_roots=[str(NATIVE),str(WORK),str(WORK.parent/'Mobile ESS'),str(RAWROOT)],
      filename_search=record(ROOT/'SEARCH_CANDIDATE_PATHS.txt'),content_search=record(ROOT/'SEARCH_CONTENT_MATCH_PATHS.txt'),
      broad_content_search_status='PARTIAL_STOPPED_AFTER_1223_PATH_MATCHES: large duplicate derived-model receipts dominated; subsequently targeted upstream source/history searches completed.',
      omitted='Private/authenticated NLR database and scheduler service not available; no contacts messaged; no exhaustive statement about external disks or internal logs.',
      negative_term='NOT_FOUND_IN_SEARCHED_AUTHORITY; never DOES_NOT_EXIST',
      artifacts_found='Power-telemetry slurmid filenames in dataset312 are execution telemetry from separate experiments, not Kestrel submission revision logs. Public hpc-oda slurmctld fixtures synthetic.'))
    for r in remote:print(r['key'],r['status'],flush=True)
if __name__=='__main__':main()
