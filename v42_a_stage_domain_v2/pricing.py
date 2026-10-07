"""Separate exact infeasibility rescue from relaxation improvement search.

Root reduced costs never certify integer-domain closure. Unsupported rows,
an incomplete scan or unverifiable certificates produce UNKNOWN, never cuts.
"""
from dataclasses import dataclass
from fractions import Fraction
from .screening import ScientificColumn


@dataclass(frozen=True)
class PricingEvidence:
    mode: str
    authority_hash: str
    row_multipliers: tuple
    independently_verified: bool
    restricted_status: str
    contradiction: str = '0'
    objective_name: str = ''
    lp_direction_coverage_verified: bool = False
    lp_direction_coverage_evidence_hash: str = ''
    lp_representation: str = ''

    def require(self):
        if not self.independently_verified or len(self.authority_hash) != 64:
            raise ValueError('INDEPENDENT_EXACT_PRICING_EVIDENCE_REQUIRED')
        if self.mode == 'FEASIBILITY_RESCUE':
            if self.restricted_status != 'EXACTLY_PROVEN_INFEASIBLE' or Fraction(self.contradiction) >= 0:
                raise ValueError('EXACT_FARKAS_CONTRADICTION_REQUIRED')
        elif self.mode == 'IMPROVEMENT_SEARCH':
            if self.restricted_status != 'INDEPENDENTLY_FEASIBLE' or not self.objective_name:
                raise ValueError('FEASIBLE_IMPROVEMENT_AUTHORITY_REQUIRED')
        else:
            raise ValueError('PRICING_MODE')
        if len({n for n,_ in self.row_multipliers}) != len(self.row_multipliers):
            raise ValueError('DUPLICATE_PRICING_ROW')


def price_column(column: ScientificColumn, evidence: PricingEvidence):
    evidence.require()
    column.signature()  # complete exact row vector mandatory
    if column.authority_hash != evidence.authority_hash:
        raise ValueError('PRICING_AUTHORITY_MISMATCH')
    rows = dict(column.rows)
    weighted = sum((Fraction(w) * Fraction(rows.get(n,0)) for n,w in evidence.row_multipliers), Fraction(0))
    if evidence.mode == 'FEASIBILITY_RESCUE':
        return dict(mode=evidence.mode, price=str(weighted),
                    classification='CERTIFICATE_BREAKING' if weighted < 0 else 'CERTIFICATE_NEUTRAL' if not weighted else 'CERTIFICATE_WORSENING',
                    permanent_cut=False)
    objectives = dict(column.objectives)
    if evidence.objective_name not in objectives:
        raise ValueError('OBJECTIVE_COLUMN_REQUIRED')
    reduced = Fraction(objectives[evidence.objective_name]) - weighted
    return dict(mode=evidence.mode, price=str(reduced), may_improve_LP=reduced < 0,
                integer_closure_proven=False, permanent_cut=False)


def scan(columns, evidence, complete_finite_scan=False):
    """Streams a pool without materializing migration Option objects."""
    evidence.require()
    rows, unknown = [], []
    for column in columns:
        try:
            rows.append(dict(candidate_id=column.candidate_id, **price_column(column, evidence)))
        except ValueError as error:
            unknown.append(dict(candidate_id=column.candidate_id, reason=str(error)))
    closed = (evidence.mode == 'IMPROVEMENT_SEARCH' and complete_finite_scan and not unknown
              and evidence.lp_direction_coverage_verified
              and len(evidence.lp_direction_coverage_evidence_hash)==64
              and evidence.lp_representation in ('EXACT_PATH_COLUMN_MASTER','VERIFIED_NATIVE_LP_PROJECTION')
              and all(not r['may_improve_LP'] for r in rows))
    return dict(results=rows, unknown=unknown, LP_PRICING_CLOSED=closed,
                physical_column_scan_is_native_LP_closure=False,
                INTEGER_DOMAIN_CLOSURE_PROVEN=False, PRODUCTION_DOMAIN_ACCEPTED=False)
