"""Final physical evidence and package byte inventory, no optimization."""
import shutil,subprocess
from .common import *

def main():
    reuse=read(OUT/'PASS27_REUSE_COMPATIBILITY.json');rows=[]
    for day in reuse['dates']:
        path=PRODUCTION/'stages'/day/'FRESH_AC'/'1'/'result.json';r=read(path);s=r['summary']
        expected={x['day']:x['receipt']['sha256'] for x in reuse['receipts'] if x['stage']=='FRESH_AC'}
        if sha(path)!=expected[day] or s['convergence_count']!=96 or s['OpenDSS_solve_count']!=96:raise ValueError('FRESH_CAUSAL_SNAPSHOT')
        fields=['voltage_violation_count','line_current_violation_count','transformer_current_violation_count','transformer_kva_violation_count','schedule_mutation_count']
        if any(s[k] for k in fields):raise ValueError('PASS_DAY_PHYSICAL_VIOLATION')
        actual=read(PRODUCTION/'stages'/day/'ACTUAL'/'1'/'output'/'ACTUAL_FIXED_REPLAY_RECEIPT.json')
        rows.append(dict(day=day,convergence=96,violations={k:s[k] for k in fields},
            Fresh_source=record(path),Actual_source=record(PRODUCTION/'stages'/day/'ACTUAL'/'1'/'output'/'ACTUAL_FIXED_REPLAY_RECEIPT.json')))
    write('PASS27_PRESERVED_PHYSICAL_AUDIT.json',dict(PASS=True,days=27,total_original_Fresh_convergence=2592,
        total_original_Fresh_solve_count=2592,all_physical_violations=0,new_Fresh_solves=0,days_rerun=0,rows=rows))
    for day in DAYS:
        lab=label(day);target=CASE/day
        for filename in ('ORIGINAL_FULL_DIAGNOSIS.log','ORIGINAL_IIS_LP_CERTIFICATE.log','BOUND_COMPLETE_CERTIFICATE.log'):
            if (target/filename).exists():shutil.copyfile(target/filename,OUT/(lab+'_'+filename))
    files=[record(p) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='SHA256_MANIFEST.json']
    files.extend(record(p) for p in sorted((ROOT/'v42_pr134_repair').iterdir()) if p.is_file())
    files.append(record(ROOT/'.gitattributes'))
    write('SHA256_MANIFEST.json',dict(files=files,external_evidence_manifest=record(CASE/'ORIGINAL_PRODUCTION_BYTE_MANIFEST.json'),
        scientific_base=BASE,production_source='b99f2778e47f8bfee22b4eb54f14af8eb9a2e3d1',
        package_prepublication_HEAD=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        final_state='MAY17_MAY19_TRUE_INFEASIBILITY_PROVEN'))
    print('Final artifacts and preserved 2592/2592 Fresh observations SHA inventory PASS',flush=True)
if __name__=='__main__':main()
