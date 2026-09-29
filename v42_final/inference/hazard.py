"""Inference-only extraction from SHA-verified Runtime source. Training methods excluded."""
from pathlib import Path
import json, numpy as np, lightgbm as lgb

def age_matrix(e):
    return np.column_stack([np.log1p(e[:-1]), np.log1p(e[1:]), np.log1p(np.diff(e)), np.arange(len(e) - 1)]).astype('float32')

class Hazard:

    def __init__(self, meta, booster):
        self.meta = meta
        self.booster = booster
        self.edges = np.array(meta['edges'], float)

    def parameters(self, x, threads=1, max_age=None):
        e = self.edges
        k = len(e) - 1
        if max_age is not None:
            k = int(np.searchsorted(e, max_age, side='left'))
            e = e[:k + 1]
        age = age_matrix(e)
        a = np.asarray(x[self.meta['columns']], dtype='float32')
        out = []
        for start in range(0, len(a), 2048):
            z = a[start:start + 2048]
            xx = np.column_stack([np.repeat(z, k, axis=0), np.tile(age, (len(z), 1))])
            h = self.booster.predict(xx, num_threads=threads).reshape(len(z), k)
            out.append(-np.log1p(-np.clip(h, 1e-07, 1 - 1e-07)) / np.diff(e))
        return np.concatenate(out) if out else np.empty((0, k))

    def tail_rates(self, par, continuation):
        if continuation == 'LAST_RATE':
            return par[:, -1]
        rate = self.meta['tail_exponential_rate']
        if rate is None:
            raise ValueError('INSUFFICIENT_TAIL_SUPPORT')
        return np.full(len(par), rate)

    def cumulative(self, par):
        return np.column_stack([np.zeros(len(par)), np.cumsum(par * np.diff(self.edges), axis=1)])

    def logsf(self, par, t, continuation='LAST_RATE'):
        t = np.broadcast_to(np.asarray(t, float), len(par))
        idx = np.clip(np.searchsorted(self.edges, t, side='right') - 1, 0, len(self.edges) - 1)
        rates = np.column_stack([par, self.tail_rates(par, continuation)])
        cum = self.cumulative(par)
        rows = np.arange(len(par))
        return np.where(t < 0, 0.0, -cum[rows, idx] - rates[rows, idx] * (t - self.edges[idx]))

    def inverse_logsf(self, par, logs, continuation='LAST_RATE'):
        h = -np.broadcast_to(np.asarray(logs, float), len(par))
        cum = self.cumulative(par)
        idx = np.sum(cum[:, 1:] < h[:, None], axis=1)
        rows = np.arange(len(par))
        rates = np.column_stack([par, self.tail_rates(par, continuation)])
        return self.edges[idx] + (h - cum[rows, idx]) / rates[rows, idx]

    @classmethod
    def load(cls, path):
        path = Path(path)
        return cls(json.loads((path / 'model.json').read_text()), lgb.Booster(model_str=(path / 'hazard.txt').read_text(encoding='utf-8')))
