from pathlib import Path
import json, subprocess, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *
from dayahead.v39l.infrastructure import process_inventory

def main():
    target=ROOT/'V40B_PRELAUNCH_SNAPSHOT.json'
    if target.exists(): raise RuntimeError('IMMUTABLE_SNAPSHOT_ALREADY_EXISTS')
    ROOT.mkdir(parents=True,exist_ok=True)
    baseline=read(V40A/'V40A_PRESTOP_CAMPAIGN_SNAPSHOT.json')
    sealed=read(V40A/'V40A_ARTIFACT_SHA256.json')
    sources=sealed['V40A_source_files']
    command="Get-ScheduledTask | Where-Object {$_.TaskName -like '*MobileESS*'} | Select-Object TaskName,TaskPath,State,@{n='Enabled';e={$_.Settings.Enabled}},Actions,Settings | ConvertTo-Json -Depth 8"
    tasks=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],encoding='utf-8').lstrip('\ufeff'))
    tasks=[tasks] if isinstance(tasks,dict) else tasks
    inventory=process_inventory()
    protected=baseline['protected_completed_files']
    cert_root=OLD/'dayahead/artifacts/v39e_full_may_2025/certificates'
    completed=[];certificates={}
    for p in sorted(cert_root.glob('V39E_MAY_DAY_CERTIFICATE_*.json')):
        value=read(p);certificates[p.name]={'sha256':sha(p),'payload':value}
        if value.get('status')=='PASS':completed.append(p.stem[-10:])
    report={'created_at_utc':now_utc(),'branch':subprocess.check_output(['git','branch','--show-current'],cwd=REPO,text=True).strip(),
      'HEAD':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
      'accepted_production_overlay_fingerprint':baseline['current_common_source_fingerprint'],
      'V40A_source_fingerprint':digest(sources),'V40A_source_files':sources,
      'V40A_sealed_artifact_manifest_SHA':sha(V40A/'V40A_ARTIFACT_SHA256.json'),
      'V39K_authority_SHA':baseline['V39K_authority_SHA'],
      'V39L_authority_files':{p.relative_to(OLD).as_posix():sha(p) for p in (OLD/'dayahead/artifacts/v39l_detached_may_resume').glob('*.json')},
      'old_source':audit(OLD,baseline['source_file_fingerprints']),
      'current_source':audit(REPO,baseline['source_file_fingerprints']),
      'current_authority':audit(REPO,baseline['production_authority_fingerprints']),
      'V40A_source':audit(REPO,sources),'old_results':audit(OLD,protected),
      'old_result_hashes':protected,'old_certificates':certificates,'old_completed_dates':completed,
      'old_incomplete_dates':[d for d in DAYS if d not in completed],
      'processes':inventory,'scheduled_tasks':tasks,
      'OLD_AUTHORITATIVE_MAY_ORCHESTRATORS':len(inventory['orchestrators']),
      'OLD_ACTIVE_MAY_WORKERS':len(inventory['workers']),
      'OLD_AUTO_RELAUNCH':'DISABLED' if all(not t['Enabled'] for t in tasks if 'V39' in t['TaskName']) else 'ENABLED',
      'old_full_file_inventory_reference':str(V40A/'V40A_PRESTOP_CAMPAIGN_SNAPSHOT.json'),
      'MAY_RESULT_BASED_TUNING_ALLOWED':'NO'}
    write(target,report)
    write(ROOT/'V40B_NUMERICAL_REGRESSION_PLAN.json',{'predeclared_at_utc':now_utc(),
       'days':['2025-04-01',min(completed)],'selection_rule':'April reference and earliest completed May date, without outcome selection',
       'cases':['B0','B1','B2'],'May_results_use':'EQUIVALENCE_ONLY','tuning_allowed':False,
       'criterion':'Exact decision/route/input authority; strongest existing production numerical reproducibility gate; no loosened tolerance'})
    print(json.dumps({k:v for k,v in report.items() if k in ('created_at_utc','old_completed_dates','OLD_AUTHORITATIVE_MAY_ORCHESTRATORS','OLD_ACTIVE_MAY_WORKERS','OLD_AUTO_RELAUNCH','old_source','current_source','current_authority','V40A_source','old_results')}))

if __name__=='__main__': main()
