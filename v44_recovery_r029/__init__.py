"""Immutable operational recovery revision; original scientific sources stay pinned."""
from pathlib import Path
import sys

# Resolve scientific modules from their original, byte-pinned checkout. Only
# this operational adapter is loaded from the independent r029 worktree.
SCIENTIFIC_ROOT=Path('D:/v44_may01_07_prepare_20261016')
if SCIENTIFIC_ROOT.is_dir():sys.path.insert(0,str(SCIENTIFIC_ROOT))
