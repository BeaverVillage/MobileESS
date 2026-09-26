"""Descriptive figure after frozen evaluation; no scientific decisions."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
assert (ROOT / 'EVALUATION_COMPLETE.json').exists()
frame = pd.read_csv(ROOT / 'MODEL_METRICS.csv')
resolutions = ['H1', 'H3', 'H6', 'CUM']
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
    'axes.spines.top': False, 'axes.spines.right': False, 'figure.facecolor': '#f8fafc'})
figure, axes = plt.subplots(2, 3, figsize=(14, 8), constrained_layout=True)
figure.suptitle('CC4-v2.5 | Fixed-family target resolution\nMay exposed historical diagnostic', fontsize=17, fontweight='bold')
panels = [('Q90_coverage', 'Q90 empirical coverage', True),
          ('normalized_Q90_pinball', 'Q90 pinball / duration / frozen TRAIN scale', False),
          ('requirement_ratio', 'Requirement ratio (CUM terminal 24h)', False),
          ('high_load_coverage', 'TRAIN-defined high-load coverage', True),
          ('positive_coverage', 'Positive-target coverage', True),
          ('calibration_error', 'Absolute calibration error', True)]
for axis, (metric, title, percent) in zip(axes.ravel(), panels):
    for j, (method, color, label) in enumerate([('AGGREGATED_H1', '#64748b', 'Sum frozen H1 bounds'), ('DIRECT', '#0284c7', 'Direct fixed LightGBM')]):
        values = frame[frame.role.eq('MAY_HISTORICAL') & frame.method.eq(method)].set_index('resolution').loc[resolutions, metric].to_numpy()
        positions = np.arange(4) + (j - .5) * .36
        axis.bar(positions, values, width=.34, color=color, label=label)
        for x, value in zip(positions, values):
            text = f'{value:.1%}' if percent else f'{value:.2f}'
            axis.annotate(text, (x, value), xytext=(0, 5), textcoords='offset points', ha='center', fontsize=8)
    axis.set_title(title, loc='left', fontweight='bold'); axis.set_xticks(np.arange(4), resolutions)
    axis.grid(axis='y', alpha=.15); axis.set_axisbelow(True)
    if percent:
        axis.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1)); axis.set_ylim(0, 1.07 if metric != 'calibration_error' else max(.25, axis.get_ylim()[1] * 1.2))
    else: axis.set_ylim(0, axis.get_ylim()[1] * 1.16)
    if metric == 'Q90_coverage': axis.axhspan(.88, .92, alpha=.12, color='#16a34a')
    if metric == 'requirement_ratio':
        axis.set_ylim(0, max(2.2, axis.get_ylim()[1]))
        axis.axhline(2, linestyle='--', color='#dc2626', linewidth=1)
axes[0, 0].legend(loc='lower left', fontsize=9)
selection = json.loads((ROOT / 'FINAL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))['primary']
figure.supxlabel(f'DEV/CAL primary: {selection}. CUM prefix scores are marginal; prefixes are not added as reserve.\nSame-target direct-versus-sum and cross-target resolution effects are distinct. Provenance UNVERIFIED / UNOBSERVED.', fontsize=10)
figure.savefig(ROOT / 'COMPARISON.png', dpi=180)
figure.savefig(ROOT / 'COMPARISON.pdf')
