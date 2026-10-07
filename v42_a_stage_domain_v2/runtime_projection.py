"""Exact elimination of the completion-count equality auxiliary.

Every class finish is nonnegative and the sum across sites/ends (STAY plus
selected migration lanes) is its exact class cardinality N. Thus each grouped
finish count is in [0,N] over the LP as well as the integer model. Substituting
x=sum(finishes) into Runtime rows removes only an equality-defined variable.
"""


def finish_count(model, finishes, cardinality, name, *, direct):
    import gurobipy as gp
    expression=gp.quicksum(finishes)
    if direct:
        return expression
    variable=model.addVar(lb=0,ub=cardinality,name=name)
    model.addConstr(variable==expression,name='exact_Runtime_finish_count')
    return variable
