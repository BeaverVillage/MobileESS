"""Post-acceptance report only; never a solver input."""
import json, hashlib
from pathlib import Path
H=Path(__file__).absolute().parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rec(p):return dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size)

def main():
    accepted=read(H/'B2_RESTORED_ACCEPTANCE.json');assert accepted['status']=='PASS'
    rule=read(H/'RULE_FREEZE.json')
    for r in rule['files']:assert sha(r['path'])==r['sha256'],r['path']
    audit=read(H/'STRUCTURAL_BINDING_AUDIT.json');assert audit['status']=='PASS'
    primary=read(Path(accepted['primary']['path']))
    original=read(H/'ORIGINAL_SELECTED_DECISION.json')['trajectory_slots'];final=accepted['final_slots']
    allowed=set(rule['allowed_changed_fields'])
    assert len(original)==len(final)==384
    changed={k for a,b in zip(original,final) for k in a if a[k]!=b[k]}
    assert changed<=allowed
    preservation=H.parent/'IEEE8500_runtime_repair_20260912/STOP_PRESERVATION_SHA256_MANIFEST.json'
    for r in read(preservation)['files']:assert sha(r['path'])==r['sha256'],r['path']
    report=['# IEEE8500 B2 frozen physical closure','',
        '**PASS — original beam/final selection preserved. B3 has not started.**','',
        'The original selected decision remains `B2-S4-b55b48c9f33cb380`. Its primary exact-AC failure remains frozen; post-selection P/Q closure does not replace that primary record. Completed authoritative B1 was neither changed nor rerun.','',
        '| Stage | Status | Evidence |','|---|---|---|',
        '| Primary Fresh | FAIL | Vmax = 1.0585440631902354 pu |',
        '| Local fixed-discrete restoration | '+accepted['local_status']+' | Gurobi status 3 is the sole fallback trigger |',
        '| Full physical P/Q fallback | '+str(accepted['full_physical_PQ_fallback'])+' | Original V41R4 minimum-effort / affine-deviation seeds and 16-step refinements |',
        '| Independent clean 96-slot AC | PASS | All voltage, phase-line, transformer phase-current/winding-kVA, convergence and settling gates |','',
        '| Metric | Primary failure | Accepted closure |','|---|---:|---:|']
    for k,v in accepted['AC'].items():report.append(f'| {k} | {primary["metrics"][k]:.12f} | {v:.12f} |')
    report+=['','All 384 vehicle-slot rows retain every field except P/Q and resulting battery energy/SoC. The AIDC schedule, vehicle, route, destination, service location, departure, connected/transit state and all other mobility fields are fixed.',
        '',f'Unchanged discrete SHA256: `{accepted["unchanged_discrete_sha"]}`.',
        '', 'The pruned candidate `B2-S4-e0d2bbcf68b5d690` (Vmax 1.0499207243101567 pu) remains `DIAGNOSTIC_AC_FEASIBLE_EXISTENCE_WITNESS` only. No restoration/fallback seed, target, or selection anchor reads it. The rejected selection-order proposal is preserved under `IEEE8500_runtime_repair_20260912/DEVELOPMENT_ONLY_REJECTED_SELECTION_ORDER`.',
        '', 'Electrical adapter preparation history: the first version stopped before the local solver on an additional tight-held-baseline check. Its failure and code remain preserved. The executing version retains the exactly reproduced chronological AC intercept and uses tight held-state derivatives, matching the frozen numerical preflight convention. The 3.0231086168841514e-05 pu diagnostic shift is recorded; original margin, chronological anchor tolerance, trust region and exact-acceptance limits remain unchanged.',
        '', 'Authority settings remain source 1.0400 pu, Vreg 123.5 V, alpha 0.50, CAPBank3 OFF. Topology, ratings, AIDC/MESS/PCC scales, 24-location mapping and all hard limits are unchanged.',
        '', 'Original local loop, local P/Q solver and fallback search bytecode identity passed the structural audit. Source, completed B1, frozen primary failure, diagnostic evidence and quarantined development bytes were checked against the preservation manifest after acceptance.',
        '', 'This is post-selection physical feasibility closure. No global AC optimum or improved beam/final-selection procedure is claimed.']
    (H/'B2_PHYSICAL_CLOSURE_REPORT.md').write_text('\n'.join(report)+'\n',encoding='utf-8')
    manifest=dict(status='PASS',files=[rec(p) for p in sorted(H.rglob('*')) if p.is_file() and p.name not in ('FINAL_REPORT_SHA256_MANIFEST.json','STATUS.json')],preservation_manifest=rec(preservation),preservation_hashes_verified=True)
    (H/'FINAL_REPORT_SHA256_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='PASS',AC=accepted['AC'],changed_fields=sorted(changed),unchanged_discrete_sha=accepted['unchanged_discrete_sha'],manifest=rec(H/'FINAL_REPORT_SHA256_MANIFEST.json')),indent=2))
if __name__=='__main__':main()
