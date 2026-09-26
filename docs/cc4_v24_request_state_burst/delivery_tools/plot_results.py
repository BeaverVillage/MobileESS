"""Descriptive plot only, after frozen historical evaluation."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
assert (ROOT / 'EVALUATION_COMPLETE.json').exists()
data = pd.read_csv(ROOT / 'MODEL_METRICS.csv')
may = data[data.role.eq('MAY_HISTORICAL')].set_index('model').loc[['C0', 'C1', 'C2']]
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.facecolor': '#f8fafc'})
figure, axes = plt.subplots(3, 2, figsize=(12, 11), constrained_layout=True)
figure.suptitle('CC4-v2.4 | Request-state proxy experiment\nMay exposed historical diagnostic', fontsize=17, fontweight='bold')
colors = ['#64748b', '#0284c7', '#d97706']
for axis, (name, title, target) in zip(axes.ravel(), [
    ('PR_AUC', 'Detector ranking: average precision', None),
    ('precision', 'Detector precision', None),
    ('detector_recall', 'Detector recall', .60),
    ('false_positive_rate', 'Detector false-positive rate', None),
    ('burst_coverage', 'Final burst coverage', .60),
    ('requirement_ratio', 'Forecast requirement ratio', 2.)]):
    values = may[name].to_numpy()
    axis.bar(np.arange(3), values, color=colors, width=.6)
    axis.set_title(title, loc='left', fontweight='bold', pad=10)
    axis.set_xticks(np.arange(3), ['C0 / reference', 'C1 / residual', 'C2 / magnitude'])
    if name == 'requirement_ratio': axis.set_ylim(0, max(values.max() * 1.20, 2.4))
    else:
        axis.set_ylim(0, 1.05)
        axis.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1))
    if target is not None: axis.axhline(target, color='#dc2626', linestyle='--', linewidth=1)
    for i, value in enumerate(values):
        label = f'{value:.3f}' if name in ['PR_AUC', 'requirement_ratio'] else f'{value:.1%}'
        axis.annotate(label, (i, value), xytext=(0, 5), textcoords='offset points', ha='center')
    axis.grid(axis='y', alpha=.15); axis.set_axisbelow(True)
selected = json.loads((ROOT / 'FINAL_SELECTION_FREEZE.json').read_text(encoding='utf-8'))['selected']
figure.supxlabel(f'All detector comparisons use gate 0.01. DEV/CAL selection: {selected}.\nRequest-state provenance UNVERIFIED / UNOBSERVED; no production promotion.', fontsize=10)
figure.savefig(ROOT / 'RESULTS.png', dpi=180)
figure.savefig(ROOT / 'RESULTS.pdf')
