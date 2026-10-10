"""Explicit, same-request B2 development binding for the common dual search.

No historical point, bound, solver, model or Native clock is imported here.
The original request, fixed input and FULL/selected case checks retain authority.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from weakref import WeakKeyDictionary

from v42_b2_seed_recovery_v19.common import read, record, digest

_RELATIVE = "v42_autonomous_b2/lb_research.py"
_COMMON_RELATIVE = "v42_m1_anytime/dual_stabilization.py"
_BOX_RELATIVE = "v42_b2_seed_recovery_v18/certificate_box.py"
_ISSUED = WeakKeyDictionary()
_KEYS = ("root", "run_id", "arm", "day", "attempt_id", "worker_slot",
         "manifest", "manifest_SHA", "implementation_SHA", "input_folder", "output")


def _require(value, message):
    if not value:
        raise PermissionError(message)


def _declared_file(worker, manifest, relative):
    declared = dict(manifest["builder_original_sources"])
    for name, value in manifest["execution_sources"].items():
        _require(name not in declared or declared[name] == value,
                 "B2_LB_RESEARCH_CONFLICTING_SOURCE_SHA")
        declared[name] = value
    expected = declared.get(relative)
    path = Path(worker.ROOT).resolve() / relative
    _require(isinstance(expected, str) and len(expected) == 64
             and sha256(path.read_bytes()).hexdigest() == expected,
             "B2_LB_RESEARCH_DECLARED_SOURCE_DRIFT:" + relative)
    return path, expected


class _StageFactory:
    def __init__(self, path):
        from . import worker
        self.path = Path(path).resolve()
        self.request = read(self.path)
        self.manifest = worker.verify_request(self.request)
        _require(self.path == Path(self.request["output"]).resolve().parent / "request.json",
                 "B2_LB_RESEARCH_OWN_REQUEST_PATH_REQUIRED")
        own, self.adapter_sha = _declared_file(worker, self.manifest, _RELATIVE)
        _require(Path(__file__).resolve() == own, "B2_LB_RESEARCH_IMPORTED_CHECKOUT_DRIFT")
        _declared_file(worker, self.manifest, _COMMON_RELATIVE)
        folder = Path(self.request["input_folder"]).resolve()
        self.inputs = {name: record(folder / name) for name in
                       ("NATIVE_INPUT.json", "B2_FIXED_AIDC.json", "PLANNING_PHYSICAL.npz")}
        fixed = read(folder / "B2_FIXED_AIDC.json")
        _require(fixed["physical"] == self.inputs["PLANNING_PHYSICAL.npz"]
                 and fixed["identity"].get("PASS") is True
                 and fixed["identity"].get("arm") == "B2"
                 and fixed["identity"].get("day") == self.request["day"],
                 "B2_LB_RESEARCH_FIXED_CURRENT_INPUT_REQUIRED")
        self.request_receipt, self.manifest_receipt = record(self.path), record(self.request["manifest"])
        _ISSUED[self] = (tuple((k, self.request[k]) for k in _KEYS),
                        digest(self.inputs), self.adapter_sha,
                        digest(self.request_receipt), digest(self.manifest_receipt))

    def __call__(self, case, request):
        from . import worker
        checked_factory(self, self.path)
        _require(all(request.get(k) == self.request[k] for k in _KEYS),
                 "B2_LB_RESEARCH_CURRENT_STAGE_REQUEST_DRIFT")
        from v42_may_campaign_native90 import m_model
        model_path, _ = _declared_file(worker, self.manifest, "v42_may_campaign_native90/m_model.py")
        _require(Path(m_model.__file__).resolve() == model_path,
                 "B2_LB_RESEARCH_ORIGINAL_MODEL_CHECKOUT_DRIFT")
        proof = m_model.verify_case(case)
        _require(proof.get("PASS") is True, "B2_LB_RESEARCH_ORIGINAL_CASE_NOT_VERIFIED")
        folder = Path(self.request["input_folder"]).resolve()
        fixed, bundle = read(folder / "B2_FIXED_AIDC.json"), read(folder / "NATIVE_INPUT.json")
        _require(case.identity.get("arm") == "B2" and case.identity.get("day") == self.request["day"]
                 and case.identity.get("input_identity") == fixed["identity"]
                 and case.bundle == bundle and case.output.resolve() == Path(self.request["output"]).resolve(),
                 "B2_LB_RESEARCH_FIXED_CASE_BINDING_DRIFT")
        import numpy as np
        with np.load(folder / "PLANNING_PHYSICAL.npz", allow_pickle=False) as planning:
            _require(set(planning.files) == set(case.planning)
                     and all(np.array_equal(planning[k], case.planning[k]) for k in planning.files),
                     "B2_LB_RESEARCH_ENTIRE_FIXED_PLANNING_DRIFT")
        from v42_m1_anytime import dual_stabilization as common
        common_path, _ = _declared_file(worker, self.manifest, _COMMON_RELATIVE)
        _require(Path(common.__file__).resolve() == common_path,
                 "B2_LB_RESEARCH_COMMON_MODULE_CHECKOUT_DRIFT")
        return common.DualSearch(common.StageIdentity(
            stage="B2_M", day=self.request["day"], source_sha=self.request["implementation_SHA"],
            input_sha=self.inputs["NATIVE_INPUT.json"]["sha256"],
            fixed_input_sha=self.inputs["B2_FIXED_AIDC.json"]["sha256"],
            case_sha=case.case_sha, matrix_sha=case.identity["selected_matrix_sha"],
            domain_sha=case.identity["selected_domain_sha"]), finite_box=_finite_box_provider(self, case))


def _finite_box_provider(factory, case):
    """Lazy original equality envelope, used only for an unbounded box view."""
    from . import worker
    from v42_b2_seed_recovery_v18 import certificate_box as box
    path, _ = _declared_file(worker, factory.manifest, _BOX_RELATIVE)
    _require(Path(box.__file__).resolve() == path, "B2_LB_RESEARCH_BOX_SOURCE_CHECKOUT_DRIFT")
    derive, verify = box.derive, box.verify
    derive_code, verify_code = derive.__code__, verify.__code__

    def finite_box(A, d):
        checked_factory(factory, factory.path)
        _declared_file(worker, factory.manifest, _BOX_RELATIVE)
        _require(Path(box.__file__).resolve() == path and box.derive is derive and box.verify is verify
                 and derive.__code__ is derive_code and verify.__code__ is verify_code,
                 "B2_LB_RESEARCH_ORIGINAL_BOX_DELEGATE_DRIFT")
        from v42_may_campaign_native90 import m_model
        from v42_m1_hybrid.blocks import matrix_sha
        _require(matrix_sha(A) == case.identity["selected_matrix_sha"]
                 and m_model._domain_sha(d) == case.identity["selected_domain_sha"],
                 "B2_LB_RESEARCH_BOX_CURRENT_CASE_AXIS_DRIFT")
        lo, hi, proof = derive(A, d)
        replay = verify(A, d, lo, hi, proof)
        _require(proof.get("PASS") is True and replay.get("PASS") is True
                 and replay.get("all_original_feasible_points_contained") is True
                 and proof.get("original_model_bounds_mutated") is False,
                 "B2_LB_RESEARCH_ORIGINAL_FINITE_BOX_NOT_PROVED")
        return lo, hi, dict(proof, independent_replay=replay)
    return finite_box


def checked_factory(factory, path):
    from . import worker
    _require(type(factory) is _StageFactory and factory in _ISSUED,
             "B2_LB_RESEARCH_OWN_FACTORY_REQUIRED")
    _require(factory.__call__.__self__ is factory and factory.__call__.__func__ is _FACTORY_CALL
             and _FACTORY_CALL.__code__ is _FACTORY_CALL_CODE,
             "B2_LB_RESEARCH_FACTORY_DELEGATE_DRIFT")
    _require(Path(path).resolve() == factory.path and read(factory.path) == factory.request
             and read(factory.request["manifest"]) == factory.manifest,
             "B2_LB_RESEARCH_CURRENT_REQUEST_FILE_DRIFT")
    _require(worker.verify_request(factory.request) == factory.manifest,
             "B2_LB_RESEARCH_CURRENT_MANIFEST_DRIFT")
    _, adapter_sha = _declared_file(worker, factory.manifest, _RELATIVE)
    _declared_file(worker, factory.manifest, _COMMON_RELATIVE)
    issued = (tuple((k, factory.request[k]) for k in _KEYS), digest(factory.inputs), adapter_sha,
              digest(record(factory.path)), digest(record(factory.request["manifest"])))
    _require(issued == _ISSUED[factory]
             and all(record(r["path"]) == r for r in factory.inputs.values()),
             "B2_LB_RESEARCH_ISSUED_SOURCE_OR_INPUT_DRIFT")
    return factory


def factory_for_request(path):
    """Read-only admission; the actual case/common search is created later."""
    return _StageFactory(path)


@contextmanager
def stage_scope(path, factory):
    from unittest.mock import patch
    from v42_may_campaign_native90 import m_stage
    from v42_may_campaign_native90.a_routing import rebound
    factory = checked_factory(factory, path)
    original = m_stage.run
    _require("lb_rescue" in (original.__kwdefaults__ or {}),
             "B2_LB_RESEARCH_COMMON_RUN_OPTIN_REQUIRED")
    # Existing V18/V19 route this function with rebound(..., prepare=...).
    # Preserve its code/globals/closure so those original overrides still work.
    routed = rebound(original, original.__globals__)
    routed.__kwdefaults__ = dict(original.__kwdefaults__, lb_rescue=factory)
    with patch.object(m_stage, "run", routed):
        yield


_FACTORY_CALL = _StageFactory.__call__
_FACTORY_CALL_CODE = _FACTORY_CALL.__code__
