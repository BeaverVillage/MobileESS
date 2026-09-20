"""Install the common search while preserving a legacy chronological runner."""
import types
from qsafe_shell import correct_slot,VERSION

def install(legacy,*,progress=None):
    namespace=legacy if isinstance(legacy,dict) else vars(legacy)
    runner=namespace['run_qsafe']
    rules=namespace['RULES']
    is_feasible=namespace['feasible'];constraints=namespace['constraints']
    def bound(evaluate,q_original,lower,upper,q_da=None):
        return correct_slot(evaluate,q_original,lower,upper,q_da=q_da,
                            rules=rules,feasible=is_feasible,constraints=constraints,
                            progress=progress)
    rebound=types.FunctionType(runner.__code__,dict(runner.__globals__,correct_slot=bound),runner.__name__,runner.__defaults__,runner.__closure__)
    rebound.__kwdefaults__=runner.__kwdefaults__
    namespace['correct_slot']=bound;namespace['run_qsafe']=rebound
    assert rebound.__code__ is runner.__code__
    return dict(version=VERSION,runner_bytecode_unchanged=True,
                prefix_evaluator_unchanged=True,fleet_size_hardcode=False,
                global_cap=None,wall_time_stop=False,
                production_execution_started=False)
