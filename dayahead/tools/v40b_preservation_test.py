from pathlib import Path
import sys,subprocess,json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from concurrent.futures import ThreadPoolExecutor
from dayahead.v40b.common import *
from dayahead.v39l.infrastructure import process_inventory

def check(item):
    name,expected=item;p=OLD/name
    if not p.is_file():return name,'MISSING'
    if p.stat().st_size!=expected['bytes'] or sha(p)!=expected['sha256']:return name,'SHA_OR_SIZE_CHANGED'
    return None

def main():
    manifest=read(V40A/'V40A_OLD_CAMPAIGN_PRESERVATION_MANIFEST.json');files=manifest['preserved_files'];changed=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for index,value in enumerate(pool.map(check,files.items()),1):
            if value:changed.append(value)
            if index%5000==0:print('PRESERVATION_HASHED',index,len(files),flush=True)
    processes=process_inventory()
    cmd="Get-ScheduledTask -TaskName 'MobileESS_V39L_May_Resume_20260905_174700' | Select-Object TaskName,State,@{n='Enabled';e={$_.Settings.Enabled}} | ConvertTo-Json -Compress"
    task=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',cmd],text=True,encoding='utf-8').lstrip('\ufeff'))
    good=not changed and not processes['orchestrators'] and not processes['workers'] and not task['Enabled']
    report={'status':'PASS' if good else 'FAIL','checked_at_utc':now_utc(),'files_hashed':len(files),
        'bytes_hashed':sum(v['bytes'] for v in files.values()),'OLD_RESULT_FILES_CHANGED':len(changed),'changes':changed,
        'old_processes':processes,'old_task':task,'baseline_manifest_SHA':sha(V40A/'V40A_OLD_CAMPAIGN_PRESERVATION_MANIFEST.json')}
    write(ROOT/'V40B_PRESERVATION_RECHECK.json',report);print('PRESERVATION',report['status'],len(files),len(changed),flush=True)

if __name__=='__main__':main()
