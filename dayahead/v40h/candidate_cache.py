"""Worker-safe cache validation before unpickling any restricted result."""
from pathlib import Path
from dayahead.paper_analysis.storage import read, write_json
from dayahead.v37.execution_acceleration import CandidateResultCache as LegacyCache
from dayahead.v37.execution_acceleration import canonical_sha256, file_sha256
from dayahead.v37.execution_acceleration import full_child_identity as legacy_child_identity
from .identity import require, verify_file, file_record
from .cache import mark_non_reusable


def require_context(context):
    value = context.get('V40H_execution_identity') if context else None
    require(value and value['identity']['schema'] == 'V40H_M1_EXECUTION_V1', 'M1_TRANSITIVE_IDENTITY_REQUIRED')
    from dayahead.v40a.invariants import digest
    require(value['identity_SHA'] == digest(value['identity']) == context.get('execution_fingerprint_sha256'), 'M1_CONTEXT_FINGERPRINT_DRIFT')
    return value


class CandidateResultCache(LegacyCache):
    def __init__(self, root, context):
        require_context(context)
        require(all(context.get(k) for k in ('beam_parent_fingerprint', 'fixed_previous_MESS_trajectory_SHA',
            'parent_state_content_SHA', 'fixed_previous_MESS_trajectory_exact_SHA')), 'RESTRICTED_PARENT_IDENTITY_MISSING')
        super().__init__(root, context)

    @staticmethod
    def load(specification):
        require_context(specification['identity'])
        path = Path(specification['path']); meta = path.with_suffix('.V40H.json')
        if not path.exists(): return None
        try:
            require(meta.is_file(), 'RESTRICTED_PROVENANCE_MISSING')
            certificate = read(meta)
            require(certificate['identity'] == specification['identity'] and
                    certificate['identity_sha256'] == specification['identity_sha256'], 'RESTRICTED_IDENTITY_DRIFT')
            require(Path(certificate['file']['path']).resolve() == path.resolve(), 'RESTRICTED_FILE_REFERENCE_MISMATCH')
            verify_file(certificate['file'])
            return LegacyCache.load(specification)
        except (ValueError, KeyError, OSError, TypeError) as error:
            mark_non_reusable(path, str(error)); return None

    @staticmethod
    def store(specification, result):
        require_context(specification['identity'])
        path = Path(specification['path'])
        if path.exists() and CandidateResultCache.load(specification) is None:
            import shutil
            archive = path.parent / 'non_reusable' / (file_sha256(path) + path.suffix)
            archive.parent.mkdir(parents=True, exist_ok=True)
            if not archive.exists(): shutil.copyfile(path, archive)
        value = LegacyCache.store(specification, result)
        write_json(path.with_suffix('.V40H.json'), {'identity': specification['identity'],
            'identity_sha256': specification['identity_sha256'], 'file': file_record(path)})
        return value


def full_child_identity(context, **kwargs):
    require_context(context)
    content = kwargs.pop('parent_content_sha256'); exact = kwargs.pop('fixed_trajectory_exact_sha256')
    require(content and exact, 'FULL_CHILD_EXACT_PARENT_IDENTITY_REQUIRED')
    return {**legacy_child_identity(context, **kwargs), 'parent_state_content_SHA': content,
            'fixed_previous_MESS_trajectory_exact_SHA': exact}


def verify_full_child(child, parent):
    from dayahead.v35r3e_r1.beam import trajectory_equivalence_sha
    require(child.parent_state_id == parent.beam_state_id, 'FULL_CHILD_PARENT_MISMATCH')
    require(child.trajectory_equivalence_sha256 == trajectory_equivalence_sha(child.trajectory_slots), 'FULL_CHILD_TRAJECTORY_DRIFT')
    require(tuple(child.trajectory_slots[:len(parent.trajectory_slots)]) == tuple(parent.trajectory_slots), 'FULL_CHILD_FIXED_PARENT_TRAJECTORY_DRIFT')
    require(tuple(child.completed_vehicles[:-1]) == tuple(parent.completed_vehicles), 'FULL_CHILD_COMPLETED_PARENT_DRIFT')
    return child
