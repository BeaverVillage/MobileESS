"""One-tree callbacks with exhaustive incumbent separation and fail-closed gates.

The registry tracks native submissions, not assumed enforcement. A previously
submitted violation is never silently skipped. Under the user's strict one
submission policy it terminates the tree and invalidates certification.
"""
from collections import Counter
from fractions import Fraction
import time
import traceback
import numpy as np
import gurobipy as gp
from v42_rowgen.core import security_axis, exact_residual, TOL, row_digest

BATCH = {'line':128, 'voltage':64, 'transformer_current':32,
         'transformer_kVA':32}

def group(name):
    family = str(name).split('[')[0]
    if family == 'line_thermal_face': return 'line'
    if family in ('voltage_lower', 'voltage_upper'): return 'voltage'
    if family in ('NormalAmps', 'transformer_current'): return 'transformer_current'
    if family == 'transformer_kVA': return 'transformer_kVA'
    raise ValueError('UNREGISTERED_SECURITY_FAMILY:' + family)

class Separator:
    """Cached PR158 sparse evaluation, same enclosure and exact fallback."""
    def __init__(self, A, d, axis=None):
        self.A, self.d = A, d
        self.axis = security_axis(d) if axis is None else np.asarray(axis, int)
        self.C = A[self.axis].tocsr()
        self.absolute = abs(self.C)
        self.rhs = d['rhs'][self.axis]
        self.sense = d['sense'][self.axis]
        if not np.isin(self.sense, ['<','>','=']).all():
            raise ValueError('UNSUPPORTED_SENSE')
        lengths = np.diff(self.C.indptr)
        k = 2*lengths+4
        u = np.finfo(float).eps/2
        self.factor = 4*(k*u/(1-k*u))
        self.tiny = (k+4)*np.nextafter(0., 1.)
        self.scale = np.maximum(1., np.asarray(self.absolute.sum(axis=1)).ravel())
    def evaluate(self, x):
        if x.shape != (self.A.shape[1],) or not np.isfinite(x).all():
            raise ValueError('NONFINITE_OR_WRONG_POINT')
        raw = self.C@x-self.rhs
        magnitude = self.absolute@abs(x)+abs(self.rhs)
        error = np.nextafter(self.factor*magnitude+self.tiny, np.inf)
        if not np.isfinite(raw).all() or not np.isfinite(error).all():
            raise ValueError('NONFINITE_ENCLOSURE')
        vio = np.where(self.sense=='=',abs(raw),np.where(self.sense=='<',raw,-raw))
        low = np.nextafter(vio-error,-np.inf)
        high = np.nextafter(vio+error,np.inf)
        marked = low>TOL
        uncertain = np.flatnonzero((low<=TOL)&(high>TOL))
        for j in uncertain:
            marked[j] = exact_residual(self.A,self.d,x,int(self.axis[j]))>Fraction(TOL)
        pos = np.flatnonzero(marked)
        return dict(PASS=not len(pos), checked_rows=len(self.axis),
                    violated=self.axis[pos], positions=pos, raw_violation=vio[pos],
                    normalized_violation=vio[pos]/self.scale[pos],
                    ambiguous_exact_checks=len(uncertain),
                    maximum_upper=float(high.max(initial=0.)))

def expression(A, variables, i):
    a,b = A.indptr[i:i+2]
    return gp.LinExpr(A.data[a:b].tolist(),
                      [variables[int(j)] for j in A.indices[a:b]])

class OneTree:
    def __init__(self,A,d,variables,validate,deadline=float('inf'),
                 allow_lazy_resubmission=True, usercuts=True, begin=None):
        self.A,self.d,self.variables = A,d,variables
        self.separator = Separator(A,d)
        self.validate = validate
        self.deadline = deadline
        self.begin = time.perf_counter() if begin is None else begin
        self.allow_lazy_resubmission = allow_lazy_resubmission
        self.usercuts = usercuts
        self.registered = np.zeros(A.shape[0],dtype=np.uint8)
        self.registry,self.ledger,self.valid = [],[],[]
        self.counts = Counter()
        self.error = None
        self.first_solver = None
        self.first_valid = None
        self.bound_observer = None
    def submit(self, model, i, kind, node, violation):
        seen = int(self.registered[i])
        if seen:
            self.counts['duplicate_rows_avoided'] += 1
            if kind != 'MIPSOL': return False
            if not self.allow_lazy_resubmission:
                self.error = dict(reason='PREVIOUSLY_SUBMITTED_ROW_VIOLATED',
                    original_row=int(i), name=str(self.d['row_names'][i]),
                    first_submission='MIPNODE' if seen==1 else 'MIPSOL',
                    violation=float(violation), node=float(node),
                    row_SHA=row_digest(self.A,self.d,i),
                    remedy='Gurobi requires cbLazy rejection, but strict no-repeat policy forbids resubmission; terminate and do not certify this tree.')
                model.terminate()
                return False
            # Only enabled by an explicit authorization, never from elapsed time.
            model.cbLazy(expression(self.A,self.variables,i),str(self.d['sense'][i]),float(self.d['rhs'][i]))
            self.counts['lazy_resubmissions'] += 1
            if seen==1:self.counts['usercut_to_lazy_promotions'] += 1
            self.registered[i] = 2
            return True
        expr = expression(self.A,self.variables,i)
        if kind=='MIPSOL':
            model.cbLazy(expr,str(self.d['sense'][i]),float(self.d['rhs'][i]))
            self.registered[i] = 2
        else:
            model.cbCut(expr,str(self.d['sense'][i]),float(self.d['rhs'][i]))
            self.registered[i] = 1
        self.registry.append(dict(original_row_id=int(i),row_name=str(self.d['row_names'][i]),
            family=str(self.d['row_names'][i]).split('[')[0],callback_type=kind,
            node_number=float(node),violation=float(violation),
            first_added_wall=time.perf_counter()-self.begin,
            original_row_SHA=row_digest(self.A,self.d,i)))
        self.counts[kind+'_rows_added'] += 1
        return True
    def __call__(self,model,where):
        self.counts['callback_count'] += 1
        try:
            now = time.perf_counter()
            if now >= self.deadline and where!=gp.GRB.Callback.MIPSOL:
                model.terminate(); return
            if self.error: model.terminate(); return
            if self.bound_observer: self.bound_observer(model,where)
            kind = None
            if where==gp.GRB.Callback.MIPSOL:
                kind='MIPSOL';x=np.asarray(model.cbGetSolution(self.variables))
                node=model.cbGet(gp.GRB.Callback.MIPSOL_NODCNT)
                if self.first_solver is None: self.first_solver=now-self.begin
            elif where==gp.GRB.Callback.MIPNODE and self.usercuts:
                if model.cbGet(gp.GRB.Callback.MIPNODE_STATUS)!=gp.GRB.OPTIMAL: return
                x=np.asarray(model.cbGetNodeRel(self.variables))
                mask=self.d['types']!='C'
                if not np.any(abs(x[mask]-np.rint(x[mask]))>TOL): return
                kind='MIPNODE';node=model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)
            if kind is None: return
            start=time.perf_counter();r=self.separator.evaluate(x)
            before_unique=len(self.registry)
            before_resubmissions=self.counts['lazy_resubmissions']
            before_promotions=self.counts['usercut_to_lazy_promotions']
            self.counts[kind+'_separations'] += 1
            record=dict(callback_type=kind,node_number=float(node),
                start_wall=start-self.begin, checked_rows=r['checked_rows'],
                violations=len(r['violated']),added=0,
                ambiguous_exact_checks=r['ambiguous_exact_checks'],
                valid_full_original=False,full_objective=None,
                maximum_upper=r['maximum_upper'],error=None)
            self.ledger.append(record)
            if kind=='MIPSOL':
                if len(r['violated']):
                    self.counts['invalid_incumbents_rejected'] += 1
                    # Scan was exhaustive, including all previously registered rows.
                    for i,violation in zip(r['violated'],r['raw_violation']):
                        if time.perf_counter()>=self.deadline:
                            self.error=dict(reason='WALL_DEADLINE_DURING_EXHAUSTIVE_LAZY_SUBMISSION',
                                violations=len(r['violated']),submitted=record['added'])
                            model.terminate(); break
                        record['added'] += int(self.submit(model,int(i),kind,node,violation))
                        if self.error: break
                else:
                    check=self.validate(x)
                    if not check['PASS']:
                        self.error=dict(reason='GRID_FEASIBLE_CANDIDATE_FAILED_FULL_ORIGINAL_AUDIT',audit=check)
                        model.terminate()
                    else:
                        record['valid_full_original']=True
                        record['full_objective']=check['objective']
                        accepted=time.perf_counter()-self.begin
                        self.valid.append((accepted,check['objective'],x.copy(),check))
                        if self.first_valid is None:self.first_valid=accepted
            else:
                self.counts['duplicate_rows_avoided'] += int(np.count_nonzero(self.registered[r['violated']]))
                gs=np.asarray([group(self.d['row_names'][i]) for i in r['violated']])
                for g,k in BATCH.items():
                    pos=np.flatnonzero((gs==g)&(self.registered[r['violated']]==0))
                    # Stable original index tie-break, no observed-result tuning.
                    order=np.lexsort((r['violated'][pos],-r['normalized_violation'][pos]))
                    for p in pos[order[:k]]:
                        record['added']+=int(self.submit(model,int(r['violated'][p]),kind,node,r['raw_violation'][p]))
            record['end_wall']=time.perf_counter()-self.begin
            record['new_unique_rows']=len(self.registry)-before_unique
            record['lazy_resubmissions']=self.counts['lazy_resubmissions']-before_resubmissions
            record['usercut_to_lazy_promotions']=self.counts['usercut_to_lazy_promotions']-before_promotions
            record['error']=None if self.error is None else self.error['reason']
        except BaseException:
            self.error=dict(reason='CALLBACK_EXCEPTION',traceback=traceback.format_exc())
            model.terminate()
