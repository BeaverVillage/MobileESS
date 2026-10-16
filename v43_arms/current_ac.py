"""Original seven-RegControl probes plus the original frozen MESS mapper."""
import ast
import inspect
import textwrap
from types import SimpleNamespace

import numpy as np

from v43.common import record
from v43_actual.current_ac import OriginalCurrentAC
from v43_actual.vendor.policy import digest


def mess_mapper():
    from v42_regcontrol.authority import source
    source()
    from dayahead.v28r2.opendss_mapping import apply_trajectory_slot
    tree=ast.parse(textwrap.dedent(inspect.getsource(apply_trajectory_slot)))
    old=tree.body[0]
    index=next(i for i,node in enumerate(old.body) if isinstance(node,ast.AnnAssign)
        and isinstance(node.target,ast.Name) and node.target.id=='by_service')
    function=ast.FunctionDef(name='apply_mess_only',args=ast.arguments(posonlyargs=[],
        args=[ast.arg(arg=k) for k in ('odd','trajectory','slot')],kwonlyargs=[],kw_defaults=[],defaults=[]),
        body=old.body[index:],decorator_list=[])
    unit=ast.Module(body=[function],type_ignores=[]);ast.fix_missing_locations(unit)
    namespace=dict(apply_trajectory_slot.__globals__)
    exec(compile(unit,inspect.getfile(apply_trajectory_slot),'exec'),namespace)
    return namespace['apply_mess_only'],record(inspect.getfile(apply_trajectory_slot))


def bind_probe():
    """Add injection and result identities at exact audited source boundaries."""
    body=textwrap.dedent(inspect.getsource(OriginalCurrentAC._probe))
    boundary=next(line for line in body.splitlines(keepends=True)
        if "authority.assert_inventory(source['inventory'](odd))" in line)
    if body.count(boundary)!=2:raise ValueError('ORIGINAL_AC_INVENTORY_BOUNDARY_DRIFT')
    indent=boundary[:len(boundary)-len(boundary.lstrip())]
    body=body.replace(boundary,indent+"self._apply_frozen_mess(odd,row)\n"+boundary,1)
    old="checked_nodes=len(names),checked_branch_phases=len(branches)))"
    if body.count(old)!=1:raise ValueError('ORIGINAL_AC_RECEIPT_SHAPE_DRIFT')
    body=body.replace(old,"checked_nodes=len(names),checked_branch_phases=len(branches),\n"
        "            maximum_line_phase=str(branches[np.flatnonzero(lines)[np.argmax(measured[lines,1])]].branch_id),\n"
        "            maximum_line_phase_index=int(np.flatnonzero(lines)[np.argmax(measured[lines,1])]),\n"
        "            MESS_plan_sha=self.mess_sha))")
    namespace=dict(OriginalCurrentAC._probe.__globals__)
    exec(compile(body,inspect.getfile(OriginalCurrentAC._probe),'exec'),namespace)
    return namespace['_probe']


class ArmCurrentAC(OriginalCurrentAC):
    def __init__(self,*,mess_plan,day_start_seconds,**kwargs):
        super().__init__(**kwargs)
        self.mess_plan=mess_plan;self.mess_sha=digest(mess_plan)
        self.day_start=float(day_start_seconds)
        self._mapping,self.mapping_source=mess_mapper()
        if mess_plan is None:self._trajectory=None
        else:
            units=sorted(mess_plan['P_kW'])
            locations=np.array([[mess_plan['connection_site'][u][t] or 'TRANSIT_UNCONNECTED'
                for u in units] for t in range(96)])
            self._trajectory=SimpleNamespace(mess_locations_96x4=locations,
                mess_p_kw=np.array([mess_plan['P_kW'][u] for u in units]).T,
                mess_q_kvar=np.array([mess_plan['Q_kvar'][u] for u in units]).T)

    def _apply_frozen_mess(self,odd,row):
        if digest(self.mess_plan)!=self.mess_sha:raise ValueError('FROZEN_MESS_PLAN_MUTATED')
        t=int((row['start_seconds']-self.day_start)//900)
        if self._trajectory is not None and 0<=t<96:self._mapping(odd,self._trajectory,t)

    _probe=bind_probe()
