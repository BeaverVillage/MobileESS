"""Inject source-owned grid authority and constant fixed controls.

No voltage, current, PCS or power formula is reimplemented here. The selected
source coefficient constructors, complete grid row builders and independent
auditors remain the owners of those equations. IEEE123 is the default source
profile; another feeder supplies a pinned hook profile and its validity packet.
"""
from contextlib import contextmanager
from fractions import Fraction
import json
import math

from .contracts import canonical, digest, require, require_sha
from .source_runtime import jsonable


DEFAULT_HOOKS = {
    "load_power": ["v42_temporal/native.py", "load_power"],
    "coefficient_constructor": ["v42_pr134_b1/native.py", "original_coefficients_for_day"],
    "coefficient_module": "v42_may01.prepare",
    "coefficient_verifier": ["v42_may_campaign_native90/bindings.py", "check_coefficients"],
    "physical_scope": ["v42_integrated/contract.py", "physical_authority"],
    "transformer_wrapper": ["v42_integrated/contract.py", "all_transformer_rows"],
    "native_grid": ["v42_native/grid.py", "add_grid"],
    "compressed_grid": ["v42_m1_sparse/grid.py", "add_compressed"],
    "grid_audit": ["v42_integrated/contract.py", "grid_audit"],
    "native_authority": ["v42_native/grid.py", "GridAuthority"],
    "voltage": ["v42_native/voltage.py", "voltage_for"],
    "stage_module": "v42_native.voltage",
}


class InjectionAuthority:
    def __init__(self, registry, authority, *, validity_json, hooks_json=None,
                 expected_transformer_rows=None):
        self.registry, self.authority = registry, authority
        self.validity_json = canonical(json.loads(validity_json))
        self.hooks_json = canonical(json.loads(hooks_json) if hooks_json else DEFAULT_HOOKS)
        self.expected_transformer_rows = expected_transformer_rows
        self.validate("A1", authority)

    @property
    def validity(self):
        return json.loads(self.validity_json)

    @property
    def hooks(self):
        return json.loads(self.hooks_json)

    @property
    def sha(self):
        return digest({"authority_sha": self.authority.sha, "validity": self.validity,
                       "hooks": self.hooks, "expected_transformer_rows": self.expected_transformer_rows})

    def _api(self, name):
        hook = self.hooks[name]
        require(isinstance(hook, list) and len(hook) == 2, "PINNED_GRID_SOURCE_HOOK_REQUIRED")
        return self.registry.callable(hook[0], hook[1])

    def stage_enum(self, stage):
        require(stage in ("A1", "M1", "A2", "M2"), "GRID_STAGE_REQUIRED")
        return getattr(self.registry.resolve(self.hooks["stage_module"]).Stage, stage)

    def validate(self, stage, authority, *, bundle=None, coefficients=None, controls=None):
        require(stage in ("A1", "M1", "A2", "M2") and authority.sha == self.authority.sha,
                "GRID_STAGE_AUTHORITY_DRIFT")
        validity = self.validity
        for key, expected in (("grid_sha", authority.grid_sha),
                              ("pcc_mapping_sha", authority.pcc_mapping_sha),
                              ("producer_source_sha", authority.source_sha)):
            require(validity.get(key) == expected, "GRID_VALIDITY_SHA_DRIFT:" + key)
        require(validity.get("units") == "kW_kvar" and
                validity.get("sign_convention") == "ORIGINAL_NATIVE_CONTROL_SIGN",
                "SOURCE_GRID_UNITS_SIGN_AUTHORITY_REQUIRED")
        require(validity.get("sensitivity_scope") in
                ("ORIGINAL_FULL_CONTROL_DOMAIN", "SOURCE_CERTIFIED_CONTROL_BOUNDS"),
                "SOURCE_SENSITIVITY_VALIDITY_REQUIRED")
        require_sha(validity.get("phase_mapping_sha"))
        require_sha(validity.get("verifier_source_sha"))
        if bundle is not None:
            require(bundle.get("day") == authority.day, "GRID_BUNDLE_DATE_DRIFT")
        if coefficients is not None:
            require(len(coefficients) == 96, "GRID_96_COEFFICIENTS_REQUIRED")
            names = tuple(coefficients[0].control_names)
            require(len(names) == len(set(names)), "GRID_CONTROL_NAMES_UNIQUE_REQUIRED")
            expected = validity.get("coefficient_sha256_by_slot")
            require(isinstance(expected, list) and len(expected) == 96,
                    "SOURCE_COEFFICIENT_SHA_ROSTER_REQUIRED")
            for index, coefficient in enumerate(coefficients):
                require(coefficient.slot == index and tuple(coefficient.control_names) == names,
                        "GRID_SLOT_OR_CONTROL_AXIS_DRIFT")
                require(coefficient.coefficient_sha256 == expected[index],
                        "SOURCE_COEFFICIENT_SHA_DRIFT")
            if "control_names" in validity:
                require(tuple(validity["control_names"]) == names, "GRID_PHASE_CONTROL_MAPPING_DRIFT")
        if controls is not None:
            require(coefficients is not None and len(controls) == 96, "GRID_CONTROL_COEFFICIENT_AXIS_REQUIRED")
            bounds = validity.get("control_bounds", {})
            for coefficient, row in zip(coefficients, controls):
                require(len(row) == len(coefficient.control_names), "GRID_CONTROL_WIDTH_DRIFT")
                for name, value in zip(coefficient.control_names, row):
                    if name.startswith(("mess_p_kw[", "mess_q_kvar[")):
                        require(type(value) in (int, float) and math.isfinite(value),
                                "FIXED_MESS_NUMERIC_CONTROL_REQUIRED")
                        if validity["sensitivity_scope"] == "SOURCE_CERTIFIED_CONTROL_BOUNDS":
                            require(name in bounds and len(bounds[name]) == 2 and
                                    bounds[name][0] <= value <= bounds[name][1],
                                    "FIXED_MESS_OUTSIDE_SOURCE_SENSITIVITY_DOMAIN")
        return True

    def coefficients(self, bundle, day):
        require(day == self.authority.day == bundle["day"], "GRID_COEFFICIENT_DATE_DRIFT")
        certificate, _, _, _ = self._api("load_power")(bundle)
        original = self.registry.resolve(self.hooks["coefficient_module"])
        coefficients = self._api("coefficient_constructor")(original, certificate, day)
        # Reloads the source archive and independently checks all unchanged
        # arrays, current denominators, branches and phase/control identities.
        receipt = self._api("coefficient_verifier")(day, certificate, coefficients)
        require(receipt.get("PASS") is True, "SOURCE_COEFFICIENT_INDEPENDENT_VERIFICATION_FAILED")
        self.validate("A1", self.authority, bundle=bundle, coefficients=coefficients)
        return coefficients

    @contextmanager
    def physical_scope(self, stage, bundle):
        self.validate(stage, self.authority, bundle=bundle)
        with self._api("physical_scope")() as source_authority:
            yield source_authority

    def make_native_authority(self, stage, bundle, coefficients):
        self.validate(stage, self.authority, bundle=bundle, coefficients=coefficients)
        certificate, _, _, _ = self._api("load_power")(bundle)
        voltage = self._api("voltage")(self.stage_enum(stage))
        inputs = certificate["input_identity"]["identity"]["inputs"]
        authority = self._api("native_authority")(
            inputs["OpenDSS_master"]["sha256"], digest(bundle["capacities"]), digest(bundle),
            digest(bundle["battery"]), voltage.lower_squared, voltage.upper_squared, True,
            stage=self.stage_enum(stage),
            transformer_current_authority_sha256=coefficients[0].transformer_current_authority_sha256)
        authority.validate()
        return authority

    def transformer_wrapper(self, stage, builder, thermal=None):
        self.validate(stage, self.authority)
        return self._api("transformer_wrapper")(builder, thermal)

    def grid_builder(self, stage, *, compressed=False, bindings=None, cost=None,
                     thermal=None, thermal_rows=None):
        self.validate(stage, self.authority)
        if compressed:
            require(bindings is not None and cost is not None, "ORIGINAL_COMPRESSED_BINDINGS_REQUIRED")
            source = self._api("compressed_grid")
            def builder(model, coefficients, controls, authority):
                self.validate(stage, self.authority, coefficients=coefficients)
                return source(model, coefficients, controls, authority, stage + "-F3", bindings, cost)
        else:
            source = self._api("native_grid")
            def builder(model, coefficients, controls, authority):
                self.validate(stage, self.authority, coefficients=coefficients)
                return source(model, coefficients, controls, authority)
        return self.transformer_wrapper(stage, builder, thermal if thermal is not None else thermal_rows)

    def thermal_rows_expected(self, bundle):
        self.validate("A1", self.authority, bundle=bundle)
        count = self.expected_transformer_rows
        if count is None:
            count = self.validity.get("transformer_phase_rows_per_slot")
        require(type(count) is int and count > 0, "SOURCE_TRANSFORMER_PHASE_ROW_COUNT_REQUIRED")
        return 96 * count

    def audit(self, stage, coefficients, controls, rho):
        self.validate(stage, self.authority, coefficients=coefficients, controls=controls)
        with self.physical_scope(stage, {"day": self.authority.day}):
            return self._api("grid_audit")(coefficients, controls, rho)

    def fixed_site_injections(self, packet, fixed_mess, coefficients):
        require(packet.get("decision_sha") == fixed_mess.sha and
                packet.get("authority_sha") == self.authority.sha,
                "A2_FIXED_MESS_PACKET_IDENTITY_DRIFT")
        names = tuple(packet["control_names"])
        require(names == tuple(coefficients[0].control_names), "A2_FIXED_MESS_PHASE_CONTROL_AXIS_DRIFT")
        controls = packet["controls"]
        self.validate("A2", self.authority, coefficients=coefficients, controls=controls)
        p, q = {}, {}
        for slot, row in enumerate(controls):
            for name, value in zip(names, row):
                if name.startswith("mess_p_kw["):
                    p[name[len("mess_p_kw["):-1], slot] = value
                elif name.startswith("mess_q_kvar["):
                    q[name[len("mess_q_kvar["):-1], slot] = value
                elif not name.startswith("aidc_load_kw["):
                    raise ValueError("UNKNOWN_ORIGINAL_GRID_CONTROL_FAMILY")
        require(p and set(p) == set(q), "A2_BOTH_FIXED_MESS_P_Q_SITE_AXES_REQUIRED")
        return p, q


def fold_fixed_affine_rows(rows, rhs, fixed_values):
    """Exact substitution of fixed columns, useful for independent small QA.

    rows are sparse {column: original binary64 coefficient} maps. Fraction
    preserves the original coefficients exactly; no row or free term is dropped.
    Native source builders perform the same substitution through constants in
    their unchanged linear expressions rather than constructing new equations.
    """
    require(len(rows) == len(rhs), "FIXED_AFFINE_ROW_AXIS_REQUIRED")
    folded, bounds = [], []
    fixed = {key: Fraction(value) for key, value in fixed_values.items()}
    for row, bound in zip(rows, rhs):
        terms = {key: Fraction(value) for key, value in row.items()}
        offset = sum((terms[key] * value for key, value in fixed.items() if key in terms), Fraction())
        folded.append({key: value for key, value in terms.items() if key not in fixed})
        bounds.append(Fraction(bound) - offset)
    return tuple(folded), tuple(bounds)
