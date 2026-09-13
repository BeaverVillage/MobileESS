from common8500 import *
import aidc_runtime,mess_runtime,terminal_ac_gate,inspect
from dayahead.tools.run_v35r3e_r1_beam import _run_case
OLD=P.parent/'IEEE8500_v41r4_production_20260911_r2'
def main():
    assert read(P/'RECOVERY_PREPARATION_PASS.json')['status']=='PASS'
    assert read(P/'B2/FINAL_AUTHORITY.json')['status']=='PASS'
    terminal_ac_gate.bind_final_selector(_run_case,P/'FINAL_SELECTOR_BUILD_TEST')
    for p in P.glob('*.py'):compile(p.read_text(encoding='utf-8'),str(p),'exec')
    previous=read(OLD/'PRODUCTION_RELEASE.json')
    for r in previous['code']:assert sha(r['path'])==r['sha256'],r['path']
    rules=read(OLD/'PRODUCTION_RULES.json')
    rules.update(recovery='B1 reused byte-for-byte; B2 recovered only from generated final children after exact AC admission',terminal_selection='Check every unique generated last-level child before terminal beam truncation; minimum original model P1 among exact-AC-feasible children; otherwise FAIL_CLOSE',additional_tuning=False,coefficient_changes=False,nonterminal_search_changes=False,MF_runtime_fix='Preserve function-restore tuple separately from before-grid metrics')
    save(P/'PRODUCTION_RULES.json',rules)
    save(P/'PRODUCTION_RELEASE.json',dict(status='FROZEN_AUTHORIZED',authorized_by='User requested diagnosis and repair of current run error',created_unix=time.time(),code=[record(p) for p in sorted(P.glob('*.py'))]+previous['code'],rules=record(P/'PRODUCTION_RULES.json'),prior_release=record(OLD/'PRODUCTION_RELEASE.json'),B1_reuse=record(P/'FINAL_B1_REUSE.json'),B2_recovery=record(P/'RECOVERY_PREPARATION_PASS.json')))
    save(P/'PRODUCTION_RELEASE_SHA256.json',record(P/'PRODUCTION_RELEASE.json'))
    print('RECOVERY_RELEASE_FROZEN',sha(P/'PRODUCTION_RELEASE.json'),flush=True)
if __name__=='__main__':main()
