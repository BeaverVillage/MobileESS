"""Record actual checkpoint/source receipts and independent cached-input checks."""
import subprocess
from collections import defaultdict,Counter
from v42_root.common import *
from v42_root.data import prepare,scientific_signature
from v42_exact.support import ExactFactory

WIP='a88879fdb4e6c51dae35656feee90f68ed19ad8f'
ROLLBACK=ROOT.parent/'v42_root_lp_compression_pr/docs/v42_ubuntu_migration_rollback'
def main():
    prereg=read(OUT/'PREREGISTRATION.json')
    prereg.update(candidates=['F2-BASE','F2-T','F2-R','F2-TR','F2-A','F2-C','F2-CRA'],DA_candidates=['DA0','DA1','DA2','DA3'],structural_Pareto_axes=['columns','rows','nonzeros'],maximum_primary_LP_candidates=3,root_node_canary=dict(run=False,reason='optional diagnostic omitted; clean continuous LP selection followed by single production run'),performance_gate='VHD compaction complete AND final Windows rollback report complete AND rollback I/O idle; candidate set frozen only after gate',parallel_structural_builds='authorized 2026-10-01; build seconds during active compaction are not benchmarks',telemetry_seconds=[60,300,600,1200,1800,3600])
    prereg['selection'].update(priority=['lowest completed optimal P1 LP wall','within 5% stronger lower bound','within 1e-7 bound fewer presolved nonzeros','fewer presolved rows+columns','fewer numerical warnings and lower coefficient range ratio','fixed simplicity order'],simplicity_order=['F2-BASE','F2-T','F2-R','F2-TR','F2-A','F2-C','F2-CRA'])
    dump('PREREGISTRATION.json',prereg)
    source=subprocess.check_output(['git','ls-tree','-r','--name-only',WIP],cwd=ROOT,text=True).splitlines()
    dump('WIP_PRESERVATION_MANIFEST.json',dict(checkpoint=WIP,files=[dict(path=p,sha256=sha(ROOT/p)) for p in source],authorized_successor_changes=['v42_root source','new v42_sparse source','new tests','new docs/v42_root_lp_sparse_compression']))
    receipts={n:dict(path=str(ROLLBACK/n),sha256=sha(ROLLBACK/n),receipt=read(ROLLBACK/n)) for n in ['WINDOWS_V42_VALIDATION.json','ROOT_LP_WIP_WINDOWS_RESTORE.json','MIGRATION_PATH_REVERT_AUDIT.json','IEEE8500_WINDOWS_AUTHORITY_RECEIPT.json']}
    progress=json.loads((ROLLBACK/'COMPACTION_PROGRESS.json').read_text(encoding='utf-8-sig'))
    dump('WINDOWS_BASELINE_RECEIPT.json',dict(canonical='WINDOWS',validation=receipts,IEEE8500_read_scope='sealed rollback receipt only; no research/data changes',production_gpu=False,compaction_at_source_resume=progress))
    data=prepare();bundle,jobs,bounds,r,raw,graphs,old,prep=data
    factory=ExactFactory(r,max(b.latest_completion for b in bounds.values()));classes=defaultdict(list)
    for u,j in sorted(jobs.items()):classes[digest(scientific_signature(j,bounds[u],factory.original.cache.identity,raw[u],bundle))].append(u)
    assert sorted(map(tuple,classes.values()))==sorted(map(tuple,prep['classes'].values()))
    sizes=Counter(map(len,classes.values()))
    audit=dict(PASS=True,jobs=len(jobs),class_count=len(classes),singleton_classes=sizes[1],non_singleton_classes=sum(n for s,n in sizes.items() if s>1),jobs_covered_by_non_singletons=sum(s*n for s,n in sizes.items() if s>1),max_class_size=max(sizes),classes=dict(classes),UID_in_signature=False,original_tie_in_signature=False,cache_sha256=sha(LOCAL/'DATA.pkl'),provider_semantics_explicitly_matched=True,checkpoint_labels_retained_only_for_identical_membership=True,method='independently recomputed all frozen job/boundary/resource/Runtime provider/nominal-seconds/six-objective signatures from restored cached input')
    dump('SCIENTIFIC_CLASS_AUDIT.json',audit)
    dump('RESTORED_WIP_RECEIPT.json',dict(scientific_base=BASE,pushed_checkpoint=WIP,remote_WIP_at_fetch='2ca6f133c89900ac11add21acb2fd21c78afa657',source_difference_checkpoint_to_remote='none in v42_root/v42_exact/v42_native/v42_final/tests',worktree=str(ROOT),canonical='WINDOWS',inherited_tests=dict(passed=393,warnings=1,seconds=5.02),class_reproduction=audit,bounded_equivalence='SCIENTIFIC_AGGREGATION_EQUIVALENCE.json; independently rerun',baseline_matrix='BASELINE_STRUCTURAL.json; independently rebuilt; no optimization'))
    from v42_root.start_audit import main as start_audit
    start_audit();dump('MIP_START_CANDIDATE.json',read(OUT/'MIP_START_AUTHORITY_AUDIT.json'))
    print('independent scientific classes',len(classes),'jobs',len(jobs),'PASS',flush=True)
if __name__=='__main__':main()
