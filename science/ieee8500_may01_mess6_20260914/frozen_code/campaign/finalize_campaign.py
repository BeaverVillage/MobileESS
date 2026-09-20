from bootstrap import *
def main():
 F=H.parent/'IEEE8500_MAY01_AIDC2X_HOST_REMAP_FULL4H_20260913'
 comparison={}
 for policy in ['B0','B1']:
  comparison[policy]=dict(DA=read(F/'DA_RESULT.json')[policy],Actual=read(F/'actual'/policy/'COMPLETE.json')['summary'],source=record(F/'RESULT.json'),MESS='OFF')
 for policy in ['B2','B3']:
  da=read(H/policy/'FINAL_AUTHORITY.json');actual=read(H/('actual_'+policy)/policy/'COMPLETE.json')
  comparison[policy]=dict(DA=da['AC'],Actual=actual['summary'],QSAFE_interventions=actual['Q_intervention_slots'],QSAFE_unresolved=actual['ROBUST_Q_ONLY_UNRESOLVED_slots'],AC_feasible=actual['AC_feasible'],MESS=6)
 for r in read(H/'INHERITED_SOURCE_FREEZE.json')['files']:assert sha(r['path'])==r['sha256']
 save(H/'RESULT.json',dict(status='COMPLETE',date='2025-05-01',policies=comparison,completed_unix=time.time(),A1_continuous_wall_seconds=14400,source_preservation='PASS'))
 rows=['# May01 six-MESS B2/B3 results','','| Policy | DA max phase-line loading | Actual max phase-line loading |','|---|---:|---:|']
 for policy,r in comparison.items():rows.append(f"| {policy} | {r['DA']['max_phase_line_loading_pu']:.12f} | {r['Actual']['max_phase_line_loading_pu']:.12f} |")
 rows+=['','B0/B1 preserve the completed MESS-OFF results. B2/B3 share six vehicles and the same initial fleet. Native tap/cap controls and all grid ratings remain unchanged.','', 'See per-policy exact, independent replay, Actual and QSAFE artifacts for feasibility and interventions.']
 (H/'REPORT.md').write_text('\n'.join(rows),encoding='utf-8')
 save(H/'FINAL_SHA256_MANIFEST.json',dict(files=[record(p) for p in H.rglob('*') if p.is_file() and p.name not in ['FINAL_SHA256_MANIFEST.json','SUPERVISOR_STATUS.json']]))
if __name__=='__main__':main()
