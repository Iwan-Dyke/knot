"""The finite request contract for the first coverage rule."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from pyoxigraph import NamedNode


@dataclass(frozen=True)
class CoverageRequest:
    subject: str
    framework: str
    framework_revision: str
    criteria: tuple[str, ...]
    rule: str = 'framework-coverage'
    version: str = '1'
    max_assertions: int = 1000
    max_sources: int = 100
    as_of: str | None = None

    def __post_init__(self) -> None:
        if self.rule != 'framework-coverage' or self.version != '1':
            raise ValueError('Unsupported rule or version')
        if (
            not isinstance(self.criteria, tuple)
            or not 1 <= len(self.criteria) <= 100
            or any(not isinstance(item, str) for item in self.criteria)
            or len(set(self.criteria)) != len(self.criteria)
        ):
            raise ValueError('Supply 1 to 100 distinct criterion IRIs')
        for iri in (self.subject, self.framework, self.framework_revision, *self.criteria):
            if not isinstance(iri, str):
                raise ValueError('Endpoints and revisions must be explicit IRIs')
            NamedNode(iri)
        for value, maximum in ((self.max_assertions, 10000), (self.max_sources, 1000)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError(f'Execution limit must be an integer between 1 and {maximum}')
        if self.as_of is not None and (not isinstance(self.as_of, str) or not self.as_of.strip()):
            raise ValueError('as_of must be a nonempty string or null')

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), 'criteria': list(self.criteria)}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> 'CoverageRequest':
        if not isinstance(value, dict):
            raise ValueError('Evaluation request must be an object')
        unknown = value.keys() - {field.name for field in fields(cls)}
        if unknown:
            raise ValueError(f'Unknown request fields: {sorted(unknown)}')
        if not isinstance(value.get('criteria'), list):
            raise ValueError('criteria must be an array of IRIs')
        return cls(**{**value, 'criteria': tuple(value['criteria'])})
