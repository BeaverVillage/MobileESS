import numpy as np

from actual_controller import Controller, Limits


LIMITS = Limits(300, 400, 440, 1080, .95, .95, .25)
P = np.array([0.])
Q = np.array([100.])
CONNECTED = np.array([True])
TRAVEL = np.array([0.])
DA = dict(rho=.8, vmin=.97, vmax=1.04)


def result(rho, vmin=.97, vmax=1.04):
    return dict(converged=True, settled=True, v=np.array([vmin, vmax]),
                ipu=np.array([rho]), tx=np.array([]), kva=np.array([.2]),
                line_rho=rho, taps=[])


calls = []


def no_event(p, q):
    calls.append(q.copy())
    return result(.8)


c = Controller(LIMITS, [760])
p, q, _, event = c.step(slot=0, p_da=P, q_da=Q, connected=CONNECTED,
                         travel_energy=TRAVEL, evaluate=no_event, da_exact=DA)
assert event['trigger'] == 'NONE' and event['exact_trials'] == 1
assert len(calls) == 1 and np.array_equal(p, P) and np.array_equal(q, Q)


def performance_event(p, q):
    return result(.83 if q[0] == 100 else .82 if q[0] > 100 else .84)


c = Controller(LIMITS, [760])
p, q, _, event = c.step(slot=0, p_da=P, q_da=Q, connected=CONNECTED,
                         travel_energy=TRAVEL, evaluate=performance_event, da_exact=DA)
assert event['trigger'] == 'MATERIAL_DA_DEVIATION'
assert event['status'] == 'Q_MATERIAL_REPAIRED' and q[0] == 100.5
assert np.array_equal(p, P)


def feasibility_event(p, q):
    return result(.8, vmax=1.06) if q[0] == 100 else result(.81)


c = Controller(LIMITS, [760])
p, q, _, event = c.step(slot=0, p_da=P, q_da=Q, connected=CONNECTED,
                         travel_energy=TRAVEL, evaluate=feasibility_event, da_exact=DA)
assert event['trigger'] == 'AC_FAIL' and event['AC_PASS']
assert event['status'] == 'Q_RESTORED' and np.array_equal(p, P)
assert event['future_actual_rows_exposed'] == 0
print('PASS: no-event DA Q; material-deviation minimal Q; AC feasibility repair; frozen P')
