"""Owned-controller exclusion fixtures; no model and no optimize."""
from practical_support import *
from unittest.mock import patch
import owned_controller_guard as guard
class Owned:
    pid=999999
    def cmdline(self):return ['python.exe','docs/v42_m_practical_exact_solver_overnight_20261008/numeric_external_controller.py']
    def cwd(self):return str(ROOT)
    def create_time(self):return 1.
class Other(Owned):
    def cwd(self):return str(ROOT.parent/'unrelated_A_stage')
def run():
    observed=guard.owned_controller_alive()
    with patch.object(guard.psutil,'process_iter',return_value=[Owned()]):assert guard.owned_controller_alive()
    with patch.object(guard.psutil,'process_iter',return_value=[Other()]):assert guard.owned_controller_alive() is None
    atomic(OUT/'OWNED_CONTROLLER_GUARD_TESTS.json',dict(PASS=True,optimize_calls=0,current_owned_controller_observed=observed,own_parallel_controller_blocks_start=True,unrelated_A_stage_excluded=True,UTC=stamp()))
    print('OWNED_CONTROLLER_GUARD_TESTS_PASS_OPTIMIZE_0')
if __name__=='__main__':run()
