"""Conditional original-root primal PStart recovery; child LPs remain dual."""
import production_oracle as registered
from practical_support import *
from fractions import Fraction as F

class LPOracle(registered.LPOracle):
    def __init__(self):
        super().__init__()
        self.pstart_path=OUT/'runs/native_production_initial/ROOT_POINT.npz'
        with np.load(self.pstart_path) as z:self.pstart=z['x'].copy()
        self.pstart_replay=hc.replay(self.A,dict(self.d,types=np.full(self.A.shape[1],'C')),self.pstart,False)
        assert self.pstart_replay['PASS'] and self.pstart.shape==(self.A.shape[1],)
        self.retry_basis_for_node=self.primal_setup

    def primal_setup(self,node):
        if node['parent'] is not None:return None
        assert node['fixings']==[]
        self.m.Params.Method=0;self.m.Params.LPWarmStart=1
        self.m.setAttr('PStart',self.variables,self.pstart.tolist());self.m.update()
        assert np.array_equal(np.asarray(self.m.getAttr('PStart')),self.pstart)
        return None

    def solve(self,node):
        # The controller may install a prior basis hook. This root rescue
        # deliberately uses only the independently feasible original LP point.
        self.retry_basis_for_node=self.primal_setup
        result=super().solve(node)
        root=node['parent'] is None
        log=(registered.OUT/Path(result['receipt']).parent/'LP.log').read_text(encoding='utf-8',errors='replace')
        result['primal_start']=dict(supplied=root,source=str(self.pstart_path.relative_to(ROOT)) if root else None,SHA256=sha(self.pstart_path) if root else None,original_relaxed_replay=self.pstart_replay if root else None,accepted=root and 'LP warm-start: use start vectors' in log,root_Method=0 if root else None,not_a_MIP_start=True,not_a_tree_resume=True)
        result['receipt_oracle_source']=dict(file=Path(__file__).name,SHA256=sha(__file__),registered_parent_file_SHA256=sha(registered.__file__))
        atomic(registered.OUT/result['receipt'],result)
        return result

core=registered.core
