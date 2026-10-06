"""Opt-in Branch-and-Price preparation. No scientific inputs or runs on import."""

import os

for _name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[_name] = '1'

BASE_SHA = 'ce5d30fb9bcb91ab8395d1313e868d24f5fde517'
