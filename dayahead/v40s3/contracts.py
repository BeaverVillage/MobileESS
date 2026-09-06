"""Pure diagnostic formulas; never imported by an optimizer."""
import math
import numpy as np

U_HOURS = (4, 6, 8, 12, 24)
Q = 5576.44921875
FIELDS = ('job_uid', 'runtime_class', 'runtime_body_q50_sec',
          'runtime_body_q90_sec', 'tail_probability', 'tail_threshold_sec',
          'tail_flag', 'robust_tail_policy', 'candidate_duration_sec',
          'flexibility_protected')


def positive(values):
    a = np.asarray(values, dtype=float)
    if not np.isfinite(a).all() or (a <= 0).any():
        raise ValueError('POSITIVE_FINITE_SECONDS_REQUIRED')
    return a


def slots(seconds):
    return np.ceil(positive(seconds) / 900).astype(np.int64)


def baseline_safe(point, requested):
    p = np.asarray(point, dtype=float)
    r = positive(requested)
    if p.shape != r.shape or not np.isfinite(p).all():
        raise ValueError('INVALID_REFERENCE')
    return np.minimum(r, np.maximum(p + Q, 900.))


def body_tail(actual, threshold):
    if threshold not in [h * 3600 for h in U_HOURS]:
        raise ValueError('UNREGISTERED_THRESHOLD')
    a = positive(actual)
    return a <= threshold, a > threshold


def metrics(actual, duration, gpu):
    a, d, g = map(positive, (actual, duration, gpu))
    if not (a.shape == d.shape == g.shape) or not len(a):
        raise ValueError('IDENTICAL_NONEMPTY_ROWS_REQUIRED')
    e = a - d
    ep, over = np.maximum(e, 0), np.maximum(-e, 0)
    return dict(N=len(a), coverage=float(np.mean(e <= 0)),
                GPU_coverage=float(np.sum(g * (e <= 0)) / g.sum()),
                underprediction_rate=float(np.mean(e > 0)),
                positive_residual_mean_sec=float(ep.mean()),
                positive_residual_P95_sec=float(np.quantile(ep, .95)),
                positive_residual_max_sec=float(ep.max()),
                MAE_sec=float(np.abs(e).mean()), WAPE=float(np.abs(e).sum()/a.sum()),
                log_MAE=float(np.abs(np.log(a)-np.log(d)).mean()),
                completion_slot_MAE=float(np.abs(slots(a)-slots(d)).mean()),
                positive_error_sec=float(ep.sum()), GPU_underprediction_sec=float((g*ep).sum()),
                overreservation_GPU_hours=float((g*over).sum()/3600),
                overreservation_P95_sec=float(np.quantile(over, .95)))


def recall_capture(actual, threshold, probability, eta, gpu, body_safe):
    a, g, d = map(positive, (actual, gpu, body_safe))
    p = np.asarray(probability, dtype=float)
    if not (a.shape == g.shape == d.shape == p.shape):
        raise ValueError('ROW_ALIGNMENT')
    if not np.isfinite(p).all() or (p < 0).any() or (p > 1).any() or not 0 <= eta <= 1:
        raise ValueError('INVALID_PROBABILITY')
    _, tail = body_tail(a, threshold)
    flag = p >= eta
    mass = g * np.maximum(a-d, 0)
    return dict(recall=float(flag[tail].mean()) if tail.any() else None,
                GPU_recall=float(g[tail & flag].sum()/g[tail].sum()) if tail.any() else None,
                mass_capture=float(mass[flag].sum()/mass.sum()) if mass.sum() else None,
                flagged_fraction=float(flag.mean()))


def select_eta(actual, threshold, probability, gpu, body_safe, *, role, target=.9):
    if role != 'CALIBRATION':
        raise ValueError('CALIBRATION_ONLY')
    a = positive(actual)
    _, tail = body_tail(a, threshold)
    if len(a) < 100 or int(tail.sum()) < 100:
        return None
    p = np.asarray(probability, dtype=float)
    eligible = []
    for eta in sorted(set([0., 1., *p.tolist()])):
        m = recall_capture(a, threshold, p, eta, gpu, body_safe)
        if m['recall'] >= target and m['GPU_recall'] >= target:
            eligible.append(eta)
    return max(eligible) if eligible else None


def hybrid(body_q90, flag, rsp, rw, policy, *, state):
    if state != 'PENDING':
        raise ValueError('PENDING_ONLY')
    b, r, w = map(positive, (body_q90, rsp, rw))
    f = np.asarray(flag)
    if f.dtype != bool or not (b.shape == f.shape == r.shape == w.shape):
        raise ValueError('ROW_ALIGNMENT')
    if policy not in ('R0', 'R1'):
        raise ValueError('EXISTING_POLICY_ONLY')
    return np.where(f, r if policy == 'R0' else w, b)


def validate_adapter(row, *, state):
    if state != 'PENDING' or set(row) != set(FIELDS):
        raise ValueError('ADAPTER_SCOPE')
    positive([row[k] for k in ('runtime_body_q50_sec', 'runtime_body_q90_sec', 'candidate_duration_sec')])
    if row['runtime_body_q50_sec'] > row['runtime_body_q90_sec']:
        raise ValueError('CROSSING')
    p = row['tail_probability']
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError('INVALID_PROBABILITY')
    if row['tail_threshold_sec'] not in [h*3600 for h in U_HOURS]:
        raise ValueError('UNREGISTERED_THRESHOLD')
    flag = row['tail_flag']
    if type(flag) is not bool or row['flexibility_protected'] is not flag:
        raise ValueError('FLAG_CONTRACT')
    if row['runtime_class'] != ('TAIL_RISK' if flag else 'BODY'):
        raise ValueError('CLASS_CONTRACT')
    if row['robust_tail_policy'] not in (('R0', 'R1') if flag else ('NONE',)):
        raise ValueError('POLICY_CONTRACT')
    return True
