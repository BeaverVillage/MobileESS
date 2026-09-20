"""New-campaign activation hook; no imports that start a production worker."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).absolute().parent))
from qsafe_binding import install

def activate(robust_search_module,frozen_worker_module,*,progress=None):
    """Call after loading the legacy kernel into a new campaign namespace.

    Input/output paths and the remapped feeder must already be bound by that
    campaign. This function changes only Q search, never engine or DA bindings.
    """
    report=install(robust_search_module,progress=progress)
    frozen_worker_module.run_qsafe=robust_search_module.run_qsafe
    return report
