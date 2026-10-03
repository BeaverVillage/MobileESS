"""Autonomous conventional layer, independent of AIDC/MESS optimization.

The session has no Planning native-state argument and never writes taps/caps.
Inputs are applied by the physical caller before solve_next(). Source settings,
enabled status and fixed capacitor states are checked before and after every
solve. An unexpected capacitor state stops execution without restoration.
"""
import numpy as np
from .authority import source,compile_verified,assert_inventory,common_contract,digest,regulator_parameters


class AutonomousSession:
    def __init__(self, *, arm='B0',regulator_sha=None,capacitor_sha=None):
        self.contract=common_contract(arm,regulator_sha=regulator_sha,capacitor_sha=capacitor_sha)
        self.odd,self.adapter,self.initial_inventory=compile_verified()
        self.initial_taps=np.array(source()['native_state'](self.odd)[0])
        self.next_slot=0; self.logs=[]

    def solve_next(self,slot):
        if slot!=self.next_slot or not 0<=slot<96:
            raise ValueError('SEQUENTIAL_DAY_SLOT_REQUIRED')
        m=source(); pre=m['inventory'](self.odd); assert_inventory(pre)
        previous=np.array(m['native_state'](self.odd)[0])
        self.odd.Solution.SolveSnap()
        post=m['inventory'](self.odd); assert_inventory(post)
        if not self.odd.Solution.Converged():
            raise ValueError('ACTUAL_AC_OR_CONTROL_NONCONVERGENCE')
        taps,caps=m['native_state'](self.odd)
        if caps!=[1,1,1,1]: raise ValueError('FIXED_CAPACITOR_STATE_DRIFT_NO_REPAIR')
        log=dict(slot=slot,previous_taps=previous.tolist(),actual_taps=taps,capacitor_states=caps,
            control_iterations=int(self.odd.Solution.ControlIterations()),
            convergence_iterations=int(self.odd.Solution.Iterations()),
            control_actions_done=bool(self.odd.Solution.ControlActionsDone()),
            converged=True,all_7_RegControls_enabled=True,CapControl_count=0,
            source_parameters_before_after_identical=True,
            REGCONTROL_AUTHORITY_SHA=digest(regulator_parameters(post)),
            control_mode=int(self.odd.Solution.ControlMode()))
        if not log['control_actions_done']: raise ValueError('CONTROL_ACTIONS_NOT_COMPLETE')
        self.logs.append(log); self.next_slot+=1
        return log

    def close(self): self.odd.Basic.ClearAll()


def replay_planning_native_state(*args,**kwargs):
    raise ValueError('PLANNING_TAP_CAP_FORCING_FORBIDDEN_IN_CURRENT_ACTUAL')
