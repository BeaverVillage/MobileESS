"""Current provenance gate around the unchanged corrected electrical kernel.

Generation is explicit and is never called by a loader. The local function
namespace relocates outputs; it does not change any electrical equation.
"""
from pathlib import Path
from types import FunctionType
import shutil
import numpy as np
from dayahead.v40e import electrical as frozen
from dayahead.paper_analysis.storage import write_npz
from .identity import CAMPAIGN, require, verify_file, verify_bound_files
from .electrical import generate, load


FIELDS = ('voltage_constant', 'voltage_matrix', 'current_constant', 'current_matrix',
          'flow_p_constant', 'flow_q_constant', 'flow_p_matrix', 'flow_q_matrix', 'branch_limits')


def _kernel():
    namespace = dict(vars(frozen)); namespace['REL'] = CAMPAIGN
    for name in ('upstream', 'rebuild_day', 'electrical_context', 'planning_context'):
        original = getattr(frozen, name)
        original = getattr(original, '__wrapped__', original)
        namespace[name] = FunctionType(original.__code__, namespace, name, original.__defaults__, original.__closure__)
    return namespace


def _arrays(context):
    return {name: np.asarray([getattr(c, name) for c in context.coefficients]) for name in FIELDS}


def generate_current(repo, day, expected_builder):
    """Future electrical generation; no generation is performed at import/load."""
    repo = Path(repo).resolve(); out = repo / CAMPAIGN / 'electrical' / day
    certificate = out / 'GENERATION_CERTIFICATE.json'
    if certificate.exists(): return load(certificate, expected_builder)
    require(not (out / 'V40E_ELECTRICAL_REBUILD_LINEAGE.json').exists(), 'UNATTESTED_GENERATION_EVIDENCE_PRESERVED')
    def producer(expected):
        require(expected['identity']['inputs']['day'] == day, 'ELECTRICAL_OPERATING_DAY')
        joint = expected['identity']['inputs']['voltage_generation']['frozen_April_joint_authority']
        source = verify_file(joint)
        target = repo / CAMPAIGN / 'april_joint_authority' / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            from dayahead.paper_analysis.storage import sha
            require(sha(target) == joint['sha256'], 'FROZEN_APRIL_AUTHORITY_DRIFT')
        else: shutil.copyfile(source, target)
        kernel = _kernel(); result = kernel['rebuild_day'](repo, day)
        context = kernel['planning_context'](repo, day)
        try:
            coefficients = out / 'PLANNING_ELECTRICAL_COEFFICIENTS.npz'
            write_npz(coefficients, **_arrays(context))
        finally: context.electrical.voltage.close(); context.electrical.current.close()
        return {'AC_anchor': result['outputs']['voltage']['new']['path'],
                'voltage_sensitivity': result['outputs']['voltage']['new']['path'],
                'line_current_sensitivity': result['outputs']['current']['new']['path'],
                'transformer_sensitivity': coefficients}
    return generate(certificate, expected_builder, producer)


def load_planning_context(repo, day, expected_builder):
    repo = Path(repo).resolve(); certificate = repo / CAMPAIGN / 'electrical' / day / 'GENERATION_CERTIFICATE.json'
    expected = expected_builder(); verify_bound_files(expected)
    outputs = load(certificate, expected_builder)
    context = _kernel()['planning_context'](repo, day)
    try:
        require(context.electrical.voltage_path.resolve() == outputs['voltage_sensitivity'].resolve(), 'CONTEXT_VOLTAGE_PATH')
        require(context.electrical.current_path.resolve() == outputs['line_current_sensitivity'].resolve(), 'CONTEXT_CURRENT_PATH')
        with np.load(outputs['transformer_sensitivity'], allow_pickle=False) as stored:
            for key, values in _arrays(context).items():
                require(np.array_equal(values, stored[key]), 'CONTEXT_GENERATED_COEFFICIENT_DRIFT:' + key)
        from dayahead.paper_analysis.storage import sha
        context.V40H_electrical_input_SHA = expected['identity_SHA']
        context.V40H_repository = str(repo)
        context.V40H_electrical_certificate_SHA = sha(certificate)
        return context
    except Exception:
        context.electrical.voltage.close(); context.electrical.current.close(); raise


def require_attested_context(context, certificate, expected_builder):
    from dayahead.paper_analysis.storage import sha
    load(certificate, expected_builder)
    require(getattr(context, 'V40H_electrical_input_SHA', None) == expected_builder()['identity_SHA'], 'UNATTESTED_NUMERICAL_CONTEXT')
    require(getattr(context, 'V40H_electrical_certificate_SHA', None) == sha(certificate), 'NUMERICAL_CONTEXT_CERTIFICATE_DRIFT')
    with np.load(load(certificate, expected_builder)['transformer_sensitivity'], allow_pickle=False) as stored:
        for key, values in _arrays(context).items(): require(np.array_equal(values, stored[key]), 'NUMERICAL_CONTEXT_ARRAY_DRIFT')
