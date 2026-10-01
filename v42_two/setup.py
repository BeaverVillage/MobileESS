"""Freeze exact PR103 authority and the corrected user contract before solves."""
import subprocess
from v42_root.common import *
BASE103='9f437c8ea745e9590d43ea866639f03265e4dfa7'
OLD=ROOT/'docs/v42_root_lp_sparse_compression'
CORRECTION=Path('C:/Users/kjw39/.codex/attachments/cc027991-8205-422a-9964-92e11dd334ae/붙여넣은 텍스트.txt')

def main():
    OUT.mkdir(parents=True,exist_ok=True);LOCAL.mkdir(parents=True,exist_ok=True)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==BASE103
    (OUT/'.gitattributes').write_text('* -text whitespace=cr-at-eol\n',encoding='utf8')
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    dump('LEGACY_PRESERVATION_AUDIT.json',dict(PASS=True,base=BASE103,files=[dict(path=p,sha256=sha(ROOT/p)) for p in names if p]))
    dump('USER_OBJECTIVE_CORRECTION_RECEIPT.json',dict(authority='explicit human correction',source_sha256=sha(CORRECTION),scientific_objective_count=2,P1='MAX_LINE_LOADING',P2='MIN_INTERVENTION',supersedes='reserve-shortfall-P2 successor',stopped_process_id=34688,historical_branch='codex/v42-p2-reserve-root-strengthening',historical_checkpoint='461228ac',merged=False))
    old=read(OLD/'MAY_A1_OPTIMIZATION.json');p1=old['passes'][0]
    dump('PR103_P1_FREEZE_RECEIPT.json',dict(PASS=True,base=BASE103,PR='https://github.com/BeaverVillage/MobileESS/pull/103',P1=p1,certificate=read(OLD/'P1_PHYSICAL_VALIDATION.json'),receipt_sha256=sha(OLD/'MAY_A1_OPTIMIZATION.json'),old_P2_is_final_P2=False,root_seconds=86.83,continuous_LP_seconds=100.5559025))
    dump('PREREGISTRATION.json',dict(base=BASE103,scientific_groups=['MAX_LINE_LOADING','MIN_INTERVENTION'],
        AIDC_P2_components=['migration_count','shift_magnitude','prestart_relocation'],MESS_P2_components=['movement_energy','movement_count'],
        solver=dict(Threads=1,Seed=20260929,MIPGap=.005,TimeLimit=3600),cumulative_optimize_only_budget_seconds=3600,
        diagnostic_budget_seconds=3600,diagnostic_P1_lock=p1['incumbent']+1e-7,P1_epsilon=1e-7,component_epsilon=1e-8,
        scalar_lock_authority='exact certified PR103 value; production replays P1 and verifies agreement',
        acceptance='P1 accepted + all ordered P2 components certified at MIPGap .005 where meaningful (exact integer bound certificate reported) + independent physical PASS',
        source_start='PR103 reference plan for replay; PR103 certified P1 physical plan for locked P2 diagnostic; inherited complete-start validation on separate copy',
        physical_domain='unchanged F2-CRA variables, bounds, all constraints; objective-only change',
        reserve='report only; no zero-shortfall hardening; raw auxiliary and conditional minimum both reported',
        CC4='frozen temporal interface; deviation reporting only',rank='canonical reconstruction only',
        production_retries=0,native_return_grace_seconds=5,GPU=False,M1=False,A2=False,M2=False,FRESH_AC=False,IEEE8500=False,
        workers='no campaign parallelism without case independence/RAM/license audit; isolated canonical worker here'))
    rows=[]
    roles=[('rho','P1','P1 MAX_LINE_LOADING','KEEP'),('reserve_shortfall','historical P2','soft reliability/reporting','REMOVE_FROM_OBJECTIVE'),('CC4_reference_deviation','historical P3','frozen CC4 timing report','REMOVE_FROM_OBJECTIVE'),('migration_count','historical P4','P2 MIN_INTERVENTION component 1','KEEP'),('shift_slots','historical P5','P2 shift magnitude component 2','KEEP'),('prestart_changes','historical P6','P2 relocation component 3','KEEP'),('deterministic UID/event rank','already excluded in F2-CRA','canonical reconstruction','REPORT_ONLY'),('MESS movement_kwh','historical after reserve','P2 MESS component 1','KEEP'),('MESS movement_count','historical after movement energy','P2 MESS component 2','KEEP'),('MESS tie','historical objective','canonical reporting only','REMOVE_FROM_OBJECTIVE'),('voltage/transformer/SOC/PCS','physical rows','unchanged physical rows','HARD_CONSTRAINT')]
    for expr,oldrole,newrole,decision in roles:rows.append(dict(expression=expr,PR103_role=oldrole,final_V42_role=newrole,decision=decision))
    table('OBJECTIVE_CONTRACT_AUDIT.csv',rows);dump('OLD_TO_FINAL_OBJECTIVE_MAPPING.json',dict(scientific_groups=2,mapping=rows,no_arbitrary_weights=True,legacy_entrypoints='historical preserved sources; final commands are v42_two.production and v42_two.mess.solve'))
    dump('P2_COMPONENT_ORDER.json',dict(scientific_objective='MIN_INTERVENTION',AIDC=['migration_count','shift_magnitude','prestart_relocation'],MESS=['movement_energy','movement_count'],scientific_P3_P4_P5_P6=False,weights=None))
    specs={
      'README.md':'# Final V42 two-objective contract\n\nScientific groups are P1 MAX_LINE_LOADING and P2 MIN_INTERVENTION. Run `py -3.11 -m v42_two.production diagnostic`, then `py -3.11 -m v42_two.production replay`. The ordered intervention subpasses all belong to P2. PR103 source and physical rows remain immutable. Historical six-level commands are not final-contract entry points. STOP before M1.\n',
      'P2_MIN_INTERVENTION_SPEC.md':'# One intervention objective family\n\nAIDC minimizes checkpoint migrations, then absolute start-slot displacement, then pre-start site changes. MESS minimizes existing movement kWh, then movement count. Use sequential exact locks, no numerical weights, no reserve/CC4/rank objectives. All subpasses are components of P2. P1 scalar lock uses the exact PR103 accepted value plus 1e-7. Component locks retain 1e-8. MIPGap=.005; report zero gaps as degenerate and integer-bound certificates separately. Canonical class reconstruction is deterministic for a fixed complete trajectory multiset, not a claim that independent solves choose identical multisets.\n',
      'RESERVE_REPORTING_CONTRACT.md':'# Reliability metric, not an objective\n\nAll inherited reserve variables, target rows and headroom remain unchanged. No shortfall hardening. Raw unoptimized component auxiliaries may be nonminimal. For the final fixed upstream known/anonymous/CC4/Runtime state, report max(0,Tc+Tr−H), with a non-unique symmetric proportional component split. This arithmetic does not alter selected decisions or rank solutions. Report raw solver components separately. Reserve is neither P1/P2 nor an electrical feasibility certificate.\n',
      'CC4_REPORTING_CONTRACT.md':'# Frozen service signal\n\nCC4 work, temporal Q10/Q90 envelopes, causal depletion, carryout and power interface stay byte-for-byte unchanged. The inherited deviation expression is evaluated on the final plan, with no objective coefficient and no extra optimization pass. It is not a separate scientific level.\n'}
    for n,s in specs.items():(OUT/n).write_text(s,encoding='utf8')
    print('CORRECTED CONTRACT FROZEN',p1['incumbent'],flush=True)

if __name__=='__main__':main()
