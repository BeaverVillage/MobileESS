"""Native interfaces with the formulation-review optimization safety boundary."""
from v42_a_stage_domain_v2.execution import install_gurobi_backstop

try:
    import gurobipy as _gp
except ImportError:
    # Matrix-free scientific audits can import metadata without a solver.
    _gp = None
if _gp is not None:
    install_gurobi_backstop(_gp)
