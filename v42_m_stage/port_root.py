"""Mechanical PR152 adapter port; retain provenance and scientific dependencies."""
from .common import *
import shutil

def run():
    dest=ROOT/'v42_m_stage_root';dest.mkdir(exist_ok=True)
    src=ROOT/'v42_dw_continuation'
    provenance={}
    for name in ('cg.py','cg_reuse.py','worker.py','integration.py','resources.py'):
        source=(src/name).read_text(encoding='utf8')
        provenance[name]=dict(source=f'v42_dw_continuation/{name}',sha256=sha(src/name))
        if name=='cg.py':
            source=source.replace("elif self.materiality!='INCONCLUSIVE':self.stop='CERTIFIED_THRESHOLD_DECISION'", "# Materiality never stops root CG.")
            source=source.replace("'../v42_m1_dw_accelerated_root_integration/'","'../'+SCI.name+'/'")
            source=source.replace('self.current_round=14;self.call=52;self.column_id=189',
                "self.current_round=basecp['RMP']['round'];self.call=max(p['call'] for p in basecp['restart_state']['prices']);self.column_id=1604")
            source=source.replace("self.historical_optimize=basecp['elapsed_budget']","self.historical_optimize=basecp['cumulative_optimize']")
            source=source.replace("SCI/'RMP_POINT_0013.npz'","SCI/basecp['RMP']['point_file']")
            # restore_smoothing has its own cp and no basecp.
            source=source.replace("with np.load(SCI/basecp['RMP']['point_file']) as z:self.last_true_pi", "with np.load(SCI/cp['RMP']['point_file']) as z:self.last_true_pi")
            source=source.replace("if self.materiality=='INCONCLUSIVE':self.start_workers(4)","self.start_workers(4)")
            source=source.replace("if self.materiality!='INCONCLUSIVE':self.stop='CERTIFIED_THRESHOLD_DECISION'", "# Materiality is diagnostic; it never stops root CG.")
            source=source.replace("self.rmps[-1]['status']==2", "self.authority_rmp()['status']==2")
            source=source.replace("while not self.stop and self.materiality=='INCONCLUSIVE' and not self.converged:", "while not self.stop and not self.converged:")
            source=source.replace("if self.remaining()<self.RMP_cap+144:","if self.remaining()<144:")
            source=source.replace("if self.materiality!='INCONCLUSIVE':break", "# Continue even after a materiality decision.")
            source=source.replace("if self.materiality!='INCONCLUSIVE' or self.converged:return", "if self.converged:return")
            source=source.replace("if self.remaining()<124:return", "if self.remaining()<2:return")
            source=source.replace("prices,safe=self.pricing_round('FINAL_CERTIFICATION',dual,120)",
                "prices,safe=self.pricing_round('FINAL_CERTIFICATION',dual,min(120.,max(.001,self.remaining()-2)))")
            source=source.replace("elif self.materiality!='INCONCLUSIVE':self.stop='CERTIFIED_THRESHOLD_DECISION'", "# A materiality certificate does not certify root convergence.")
            source=source.replace("else 'CERTIFIED_THRESHOLD_DECISION')", "else 'ROOT_GRANT_STOP')")
            source=source.replace("self.stop=self.stop or 'NEW_BUDGET_BLOCK_RESERVE_EXHAUSTED'", "self.stop=self.stop or 'NEW_BUDGET_BLOCK_RESERVE_EXHAUSTED'")
            # Final certification safety and same-dual proof are tested independently.
            old="self.converged=bool(c['certified'] and all(p['native_status']==2 and p['valid_bound'] and p['ObjBound']>=-EPS for p in prices))"
            source=source.replace(old,"self.converged=convergence_certificate(c,prices,key)")
            source=source.replace("from .common import *", "from .common import *\nfrom .policy import convergence_certificate")
        if name=='integration.py':
            source=source.replace("from .admission import wait_admission", "from .admission import wait_admission")
            source=source.replace("SCI/'RMP_POINT_0013.npz'", "SCI/read(SCI/'DW_CHECKPOINT_LATEST.json')['RMP']['point_file']")
        (dest/name).write_text(source,encoding='utf8')
    (dest/'__init__.py').write_text('"""PR152 mechanics in a separate grant/artifact namespace."""\n',encoding='utf8')
    write('ROOT_PORT_PROVENANCE.json',provenance)
    for name in ('PR147_BYTE_FREEZE.json','DW_RUNTIME_FEATURE_SELECTION.json'):
        shutil.copyfile(SCI/name,OUT/name)

if __name__=='__main__':run()
