"""Pytest-only native path adapter for Gurobi's Unicode-path limitation.

Some inherited modules resolve the ASCII D: alias to the Korean OneDrive path.
Only gp.read filenames are translated back to the SAME existing file's ASCII
alias. No model bytes, mathematical rows, test assertions or solver settings
are changed. Invoke explicitly with pytest -p v42_april_b0.regression_paths.
"""
import os
from pathlib import Path


def pytest_sessionstart(session):
    import gurobipy as gp
    parent_alias = Path(os.getcwd()).parent
    parent_resolved = parent_alias.resolve()
    original_read = gp.read

    def read_existing_alias(filename, *args, **kwargs):
        path = Path(filename)
        try:
            relative = path.relative_to(parent_resolved)
        except ValueError:
            return original_read(filename, *args, **kwargs)
        alias = parent_alias/relative
        if path.is_file() and alias.is_file() and os.path.samefile(path, alias):
            return original_read(str(alias), *args, **kwargs)
        return original_read(filename, *args, **kwargs)

    gp.read = read_existing_alias
