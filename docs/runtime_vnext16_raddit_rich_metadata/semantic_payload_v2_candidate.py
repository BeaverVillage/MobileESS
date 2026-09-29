"""Additive PR89 payload extension. Not activated by importing the research study."""
from dataclasses import dataclass
from v42.semantic_adapter import SubmissionSemanticPayload

VERSION='SUBMISSION_SEMANTIC_PAYLOAD_V2'
FIELD_MISSING='<FIELD_MISSING>'
APPROVED_FIELDS=('user','submit_line')
CONCEPT_FIELDS=('user','account','partition','qos','job_type','name','submit_line','script','modules','conda_envs','workdir','array_index','array_range')

@dataclass(frozen=True,repr=False)
class SubmissionSemanticPayloadV2(SubmissionSemanticPayload):
    workdir: str | None = None
    array_index: str | None = None
    array_range: str | None = None

    def __post_init__(self):
        if not isinstance(self.identity_namespace,str) or not self.identity_namespace:
            raise ValueError('IDENTITY_NAMESPACE_REQUIRED')
        for name in CONCEPT_FIELDS:
            value=getattr(self,name)
            if value is not None and name not in APPROVED_FIELDS:
                raise ValueError('SOURCE_UNAUTHORIZED_FIELD:'+name)
            if name in APPROVED_FIELDS and value is not None and not isinstance(value,str):
                raise ValueError('PSEUDONYM_STRING_REQUIRED')

    def __repr__(self):return 'SubmissionSemanticPayloadV2(<redacted>)'

    @property
    def support_level(self):
        n=sum(isinstance(getattr(self,c),str) and bool(getattr(self,c).strip()) for c in APPROVED_FIELDS)
        return 'MINIMAL' if n==0 else 'FULL' if n==len(APPROVED_FIELDS) else 'PARTIAL'

    def category_projection(self):
        return {c:(getattr(self,c) if getattr(self,c) is not None and getattr(self,c).strip() else FIELD_MISSING) for c in APPROVED_FIELDS}

    def as_legacy(self):
        return SubmissionSemanticPayload(user=self.user,submit_line=self.submit_line,identity_namespace=self.identity_namespace)

    @classmethod
    def from_mapping(cls,values):
        if set(values)-set(CONCEPT_FIELDS)-{'identity_namespace'}:
            raise ValueError('OUTCOME_OR_UNKNOWN_FIELD')
        return cls(**values)
