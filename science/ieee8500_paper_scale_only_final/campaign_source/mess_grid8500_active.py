"""Diagnostic compact electrical seed with complete IEEE8500 row separation.

The seed only decides which original rows are materialized before optimize.
Every logical row is evaluated after each candidate solve; this module does
not change the MESS route domain, electrical equations, or objective.
"""
from common8500 import *
import gurobipy as gp
import scipy.sparse as sp
import mess_grid8500 as full
REPORT_ROOT=P/'B2_ACTIVE_SET_DIAGNOSTIC'
ACTIVE_COUNT=0


class ActiveGrid:
    def __init__(self, model, coefficients, controls, eta, inputs, seed_path,report_root):
        self.model=model
        self.coefficients=tuple(coefficients)
        self.controls=tuple(controls)
        self.eta=eta
        self.parts=tuple(full.components(model, row) for row in controls)
        self.present=set()
        self.iteration=0
        self.logical_rows=0
        self.added_rows=0
        self.seed_path=Path(seed_path)
        self.report_root=Path(report_root)
        seed=read(self.seed_path)
        assert seed['status']=='PASS' and seed['seed_only'] and not seed['active_set_hard_cap']
        self.seed=seed
        self.seed_lines={}
        self.seed_voltage={}
        for slot,index in seed['line_states']:
            self.seed_lines.setdefault(int(slot),set()).add(int(index))
        for slot,index in seed['voltage_states']:
            self.seed_voltage.setdefault(int(slot),set()).add(int(index))
        self.exclusive=(float(inputs.electrical_authority.active_power_limit_kw),
                        float(inputs.electrical_authority.pcs_kva))
        self.floor=self._rho_floor()
        model.addConstr(eta>=self.floor,name='IEEE8500_MESS_DERIVED_RHO_FLOOR')
        self._install_seed()
        model.update()
        save(self.report_root/'SEED_BUILD.json',dict(
            status='SEED_ONLY_NOT_FULL_PRODUCTION',seed=record(self.seed_path),
            active_rows=self.added_rows,full_logical_rows=self.logical_rows,
            rho_floor=self.floor,source_coefficients=[c.coefficient_sha256 for c in coefficients],
            no_route_pruning=True,no_active_row_cap=True,full_separation_required=True))

    def _rho_floor(self):
        anchors=np.array([part[0] for part in self.parts])
        peak=full.evaluate_grid(self.coefficients,anchors,AX['nodes'])
        slot=int(peak['critical_slot'])
        fixed=self.parts[slot][0]
        pmax,qmax=self.exclusive
        floor=0.
        for kind,w,cons,_ in full.rows(self.coefficients[slot]):
            if kind!='line':continue
            base=cons+w@fixed
            radius=np.max(np.abs(w[:,12:36])*pmax+np.abs(w[:,36:60])*qmax,axis=1)
            floor=max(floor,float((base-radius).max())-1e-8)
        return floor

    def _add_group(self,slot,group,kind,w,cons,bound,indices):
        indices=np.asarray(sorted(set(map(int,indices))),dtype=int)
        if not len(indices):return 0
        fresh=np.array([i for i in indices if (slot,group,int(i)) not in self.present],dtype=int)
        if not len(fresh):return 0
        fixed,C,variables,_,_=self.parts[slot]
        ww=w[fresh]
        B=ww@C
        base=cons[fresh]+ww@fixed
        eta_column=-np.ones(len(fresh)) if kind=='line' else np.zeros(len(fresh))
        A=np.c_[B,eta_column]
        rhs=(0. if kind=='line' else bound)-base
        self.model.addMConstr(sp.csr_matrix(A),gp.MVar.fromlist(variables+[self.eta]),'<',rhs,
                              name=f'IEEE8500_{kind}_{slot}_g{group}_r{self.iteration}')
        self.present.update((slot,group,int(i)) for i in fresh)
        self.added_rows+=len(fresh)
        return len(fresh)

    def _install_seed(self):
        for slot,c in enumerate(self.coefficients):
            for group,(kind,w,cons,bound) in enumerate(full.rows(c)):
                self.logical_rows+=len(cons)
                if kind.startswith('voltage_'):
                    selected=self.seed_voltage.get(slot,())
                elif kind=='line':
                    selected=self.seed_lines.get(slot,())
                else:
                    selected=()
                self._add_group(slot,group,kind,w,cons,bound,selected)
        assert self.logical_rows==31945536,(self.logical_rows,'LOGICAL_ROW_AXIS_DRIFT')

    @staticmethod
    def _value(expression):
        if isinstance(expression,(float,int,np.number)):return float(expression)
        return float(expression.getValue() if isinstance(expression,gp.LinExpr) else expression.X)

    def separate(self):
        """Add every violated omitted row; return an auditable closure record."""
        model=self.model
        assert model.SolCount>0
        self.iteration+=1
        objective=float(model.ObjVal)
        bound=float(model.ObjBound)
        gap=float(model.MIPGap)
        solver_status=int(model.Status)
        eta=float(self.eta.X)
        numeric=np.array([[self._value(x) for x in slot] for slot in self.controls],dtype=float)
        assert numeric.shape==(96,60)
        tolerance=float(model.Params.FeasibilityTol)
        started=time.perf_counter()
        added=0
        scanned=0
        maximal=-float('inf')
        by_kind={}
        for slot,c in enumerate(self.coefficients):
            for group,(kind,w,cons,limit) in enumerate(full.rows(c)):
                violation=cons+w@numeric[slot]-(eta if kind=='line' else limit)
                scanned+=len(violation)
                maximal=max(maximal,float(violation.max()))
                selected=np.flatnonzero(violation>tolerance)
                if not len(selected):continue
                existing=[int(i) for i in selected if (slot,group,int(i)) in self.present]
                if existing:
                    raise RuntimeError(f'ACTIVE_GRID_EXISTING_ROW_VIOLATION:{slot}:{group}:{existing[:5]}:{float(violation[existing].max())}')
                count=self._add_group(slot,group,kind,w,cons,limit,selected)
                added+=count
                by_kind[kind]=by_kind.get(kind,0)+count
        model.update()
        result=dict(status='FULL_SEPARATION_CLOSED' if added==0 else 'VIOLATED_ROWS_ADDED',
                    iteration=self.iteration,all_logical_rows_checked=scanned,
                    exact_original_row_tolerance=tolerance,
                    maximum_violation=maximal,new_rows=added,total_active_rows=self.added_rows,
                    new_rows_by_kind=by_kind,incumbent_objective=objective,
                    restricted_best_bound=bound,restricted_mip_gap=gap,
                    solver_status=solver_status,seconds=time.perf_counter()-started,
                    no_row_cap=True,no_route_pruning=True)
        save(self.report_root/f'SEPARATION_{self.iteration:03}.json',result)
        return result


ACTIVE=None


def integrated_grid(model,coefficients,controls,eta,inputs):
    global ACTIVE,ACTIVE_COUNT
    ACTIVE_COUNT+=1
    report_root=REPORT_ROOT/f'call_{ACTIVE_COUNT:05}'
    ACTIVE=ActiveGrid(model,coefficients,controls,eta,inputs,
                      P/'COMPACT_B0_ACTIVE_SEED.json',report_root)
    return ACTIVE.added_rows+1
