"""SAFE screening needs complete scientific row identity; heuristic cuts fail closed."""
from dataclasses import dataclass
from fractions import Fraction
from .domain import digest


@dataclass(frozen=True)
class ScientificColumn:
    candidate_id: str
    class_id: str
    authority_hash: str
    rows: tuple  # every scientific row (name, exact coefficient)
    objectives: tuple  # every P1/P2 coefficient
    complete: bool = False

    def signature(self):
        if not self.complete or len(self.authority_hash) != 64:
            raise ValueError('COMPLETE_SCIENTIFIC_ROW_IDENTITY_REQUIRED')
        names = [name for name, _ in self.rows]
        objectives = [name for name,_ in self.objectives]
        if any(type(name) is not str for name in names+objectives):
            raise ValueError('CANONICAL_STRING_COEFFICIENT_AXIS_REQUIRED')
        if len(names) != len(set(names)) or len(objectives) != len(set(objectives)):
            raise ValueError('DUPLICATE_ROW_AXIS')
        rows = tuple(sorted((str(n), str(Fraction(v))) for n,v in self.rows if Fraction(v)))
        objectives = tuple(sorted((n, str(Fraction(v))) for n,v in self.objectives))
        return digest((self.class_id, self.authority_hash, rows, objectives))


def exact_duplicates(columns):
    """Keep lexicographic canonical representative; no float tolerance."""
    canonical, removed, ambiguous = {}, {}, []
    for column in sorted(columns, key=lambda c:c.candidate_id):
        try:
            signature = column.signature()
        except ValueError:
            ambiguous.append(column.candidate_id)
            continue
        if signature in canonical:
            removed[column.candidate_id] = canonical[signature].candidate_id
        else:
            canonical[signature] = column
    return dict(kept=[c.candidate_id for c in canonical.values()] + ambiguous,
                exact_duplicates=removed, ambiguous_keep_lazy=ambiguous,
                safe_dominance_count=0, dominance_rule='DISABLED_WITHOUT_FORMAL_PROOF')


def grid_priority(option, job, signed_sensitivities=None):
    """Stored signed row sensitivities order activation; membership is untouched."""
    signed_sensitivities = signed_sensitivities or {}
    score = sum(float(signed_sensitivities.get((site,t),0)) * job.gpu
                for site,a,b in option.segments for t in range(a,b))
    priority = 'HIGH_PRIORITY' if score < 0 else 'MEDIUM_PRIORITY' if score == 0 else 'LOW_PRIORITY'
    return dict(priority=priority, signed_grid_contribution=score,
                displacement_cost=abs(option.start-job.reference_start),
                scientific_member_unchanged=True, permanent_cut=False,
                stable_order=(score, abs(option.start-job.reference_start), option))
