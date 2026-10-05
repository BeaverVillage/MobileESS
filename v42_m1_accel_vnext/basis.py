"""A column append preserves feasibility of the old basis extended at lambda=0.

The unchanged row axis and old variable prefix are necessary conditions. New
nonnegative columns start nonbasic at their lower bound. Gurobi may crush this
valid basis through presolve (LPWarmStart=2). No reset or integer tree reuse.
"""
import time

class BasisSession:
    def __init__(self, model):
        self.model = model
        self.saved = None

    def capture(self):
        m = self.model; m.update()
        if m.Status != 2:
            raise ValueError('A terminal optimal LP basis is required')
        self.saved = dict(variables=m.getAttr('VarName'), rows=m.getAttr('ConstrName'),
                         VBasis=m.getAttr('VBasis'), CBasis=m.getAttr('CBasis'))
        return dict(variables=len(self.saved['variables']), rows=len(self.saved['rows']))

    def restore(self):
        m = self.model; m.update(); s = self.saved
        if s is None:
            raise ValueError('No captured basis')
        names=m.getAttr('VarName'); rows=m.getAttr('ConstrName')
        if names[:len(s['variables'])] != s['variables'] or rows != s['rows']:
            raise ValueError('Basis axis changed')
        new=m.getVars()[len(s['variables']):]
        if any(v.LB != 0 for v in new):
            raise ValueError('New columns must have zero lower bound')
        start=time.perf_counter()
        m.setAttr('VBasis', s['VBasis'] + [-1]*len(new))
        m.setAttr('CBasis', s['CBasis'])
        m.Params.Method=1; m.Params.LPWarmStart=2; m.update()
        return dict(supplied=True, new_nonbasic_columns=len(new),
                    restore_seconds=time.perf_counter()-start,
                    basis_status='SUPPLIED_VALID_AXIS; native acceptance must be observed in log')
