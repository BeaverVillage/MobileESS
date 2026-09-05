from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from dayahead.v40b.common import *
from dayahead.v39e.campaign_adapter import configure_v37_runner, build_day

def main():
    runner=configure_v37_runner();rows=[]
    for day in DAYS:
        for case in ('B0','B1','B2'):
            cp=runner._checkpoint_path(OLD,day,case)
            if not cp.exists():continue
            aidc=build_day(REPO,day,'B0' if case=='B2' else case)
            fp=runner.case_execution_fingerprint(REPO,day,case,aidc)
            saved=read(cp)
            valid=runner._valid_case_checkpoint(OLD,day,case,fp)
            differences={k:{'saved':saved.get('execution_fingerprint',{}).get(k),'current':v}
              for k,v in fp.items() if saved.get('execution_fingerprint',{}).get(k)!=v}
            row={'day':day,'case':case,'accepted':valid is not None,'checkpoint':str(cp),
                 'differences':differences,'result':valid}
            rows.append(row);print(day,case,'PASS' if valid else 'REJECT',list(differences),flush=True)
            write(ROOT/'V40B_CURRENT_LOADER_PROBE.json',{'rows':rows})

if __name__=='__main__':main()
