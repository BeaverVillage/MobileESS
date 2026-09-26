"""Static descriptive figure from already frozen evaluation; never trains/selects."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
assert (ROOT / 'EVALUATION_COMPLETE.json').exists()
metrics = pd.read_csv(ROOT / 'MODEL_METRICS.csv')
may = metrics[metrics.role.eq('MAY_2025')].set_index('model')
if may.empty:
    roles = metrics.role.unique()
    may = metrics[metrics.role.eq(next(r for r in roles if 'MAY' in r.upper()))].set_index('model')
may = may.loc[['C0', 'C1', 'C2']]
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.facecolor': '#f8fafc'})
colors = ['#64748b', '#0284c7', '#d97706']
fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
fig.suptitle('CC4-v2.3 | May historical diagnostic\nFrozen base forecast; detector-gated corrections',
             fontsize=17, fontweight='bold')
x = np.arange(3)
for j, (metric, title, bound) in enumerate([
    ('detector_recall', 'Burst detector recall', .60),
    ('burst_coverage', 'Final burst coverage', .60),
    ('requirement_ratio', 'Requirement ratio', 2.),
    ('Q90_pinball', 'Operational Q90 pinball loss', None)]):
    ax = axes.ravel()[j]
    values = may[metric].to_numpy()
    ax.bar(x, values, color=colors, width=.60)
    ax.set_xticks(x, ['C0 / old gate', 'C1 / residual', 'C2 / tail'])
    ax.set_title(title, loc='left', fontweight='bold', pad=10)
    if bound is not None:
        ax.axhline(bound, color='#dc2626', linestyle='--', linewidth=1,
                   label='60% minimum' if bound == .60 else '<2.0 target')
        ax.legend(frameon=False, loc='upper left')
    if j < 2:
        ax.set_ylim(0, 1)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    else:
        ax.set_ylim(0, max(values.max() * 1.20, (bound or 0) * 1.20))
    for k, value in enumerate(values):
        label = f'{value:.1%}' if j < 2 else f'{value:.2f}'
        ax.annotate(label, (k, value), xytext=(0, 5), textcoords='offset points', ha='center')
    ax.grid(axis='y', alpha=.15)
    ax.set_axisbelow(True)
selected = json.loads((ROOT / 'FINAL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))['selected']
fig.supxlabel(f'DEV/CAL selection: {selected} retained. Exposed May is not untouched confirmation. No production promotion.', fontsize=10)
fig.savefig(ROOT / 'RESULTS.png', dpi=180)
fig.savefig(ROOT / 'RESULTS.pdf')
