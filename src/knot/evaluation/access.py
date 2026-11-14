"""Build an evidence-granted evaluation view without global currentness metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyoxigraph import Literal, NamedNode, Store

from knot.curating.evidence_accounts import _validate_group
from knot.evaluation.snapshot import Snapshot, canonical_hash, implementation
from knot.graph.knowledge import ORG, _records, _signature
from knot.graph.query import load_store
from knot.graph.rdf import ATTRIBUTED, DERIVED, META, RDF_TYPE, VOCAB, one, values
from knot.interfaces.access import AccessScope
from knot.reviewing.state import read_events
from knot.shared.storage import managed_path
from knot.writing.sources import add_note_sources, curated_scope


@dataclass
class View:
    store: Store
    records: list[dict[str, Any]]
    events: list[dict[str, Any]]
    scope: AccessScope
    signature: str


def _qualifications(
    root: Path, records: list[dict[str, Any]], scope: AccessScope
) -> tuple[set[str], list[dict[str, Any]]]:
    """Withhold a witness whose required qualification is outside the grant."""
    path = managed_path(root, 'curation/evidence-accounts.json')
    if not path.exists():
        return set(), []
    data = json.loads(path.read_bytes())
    if (
        not isinstance(data, dict)
        or set(data) != {'schema_version', 'groups'}
        or type(data['schema_version']) is not int
        or data['schema_version'] != 1
        or not isinstance(data['groups'], list)
    ):
        raise ValueError('Invalid evidence account catalogue')
    visible = {record['id'] for record in records}
    grants = None if scope.whole_dataset else dict(scope.revisions)
    blocked, groups = set(), []
    for group in data['groups']:
        if not isinstance(group, dict):
            raise ValueError('Invalid evidence account group')
        members, pins = group.get('assertions'), group.get('sources')
        present = (
            visible.intersection(member for member in members if isinstance(member, str))
            if isinstance(members, list)
            else set()
        )
        if not present:
            continue
        if grants is not None and (
            not isinstance(pins, list)
            or not pins
            or any(
                not isinstance(pin, dict)
                or not isinstance(pin.get('revision'), str)
                or grants.get(pin.get('revision')) != pin.get('sha256')
                or pin.get('revision') not in grants
                for pin in pins
            )
        ):
            blocked.update(present)
            continue
        _validate_group(group)
        groups.append({**group, 'assertions': sorted(present)})
    return blocked, groups


def _records_for_evaluation(store: Store) -> list[dict[str, Any]]:
    records = sorted(_records(store), key=lambda record: record['id'])
    for record in records:
        # Kind is local to the assertion. Global organisation freshness and
        # aggregated entity types would reveal changes to unrelated hidden data.
        current = values(store, record['id'], VOCAB + 'organisationFingerprint', ORG) == [
            Literal(_signature(record))
        ]
        kinds = values(store, record['id'], VOCAB + 'knowledgeKind', ORG) if current else []
        record['kind'] = kinds[0].value.removeprefix(VOCAB) if kinds else 'Unspecified'
        record['classification'] = {'status': 'Unreviewed' if current else 'Missing'}
        for end in ('subject', 'object'):
            record[end]['types'] = []
    return records


def load_view(root: Path, scope: AccessScope) -> View:
    scope = curated_scope(root, scope)
    raw = load_store(root / 'graph', history=True, include_notes=False, allow_empty=True)
    records = _records_for_evaluation(raw)
    if not scope.whole_dataset:
        grants = dict(scope.revisions)
        available = {record['id'] for record in records}
        # The standard retrieval selector can omit malformed records. A corrupt
        # admitted Accepted assertion must instead fail evaluation explicitly.
        for quad in raw.quads_for_pattern(
            None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META
        ):
            aid = quad.subject.value
            evidence = values(raw, aid, DERIVED)
            if not evidence or any(
                one(raw, eid.value, VOCAB + 'revision').value not in grants for eid in evidence
            ):
                continue
            if (
                one(raw, aid, VOCAB + 'reviewStatus').value == VOCAB + 'Accepted'
                and one(raw, aid, VOCAB + 'lifecycle').value == VOCAB + 'Active'
                and aid not in available
            ):
                raise ValueError('Invalid admitted assertion metadata')
    projected, _, records, labels = scope.apply(
        raw, raw, records, {}, include_framework_stubs=False
    )
    blocked, groups = _qualifications(root, records, scope)
    if blocked:
        records = [record for record in records if record['id'] not in blocked]
        projected, _, records, labels = scope.apply(
            raw, raw, records, {}, include_framework_stubs=False
        )
    admitted = {record['id'] for record in records}
    for aid in admitted:
        for field in (ATTRIBUTED, VOCAB + 'framework'):
            for quad in raw.quads_for_pattern(NamedNode(aid), NamedNode(field), None, META):
                projected.add(quad)
    for record in records:
        authored = values(projected, record['id'], VOCAB + 'authorClassification')
        if authored:
            record['author_classification'] = json.loads(authored[0].value)
    # Do not return predecessor links into the dataset-wide review chain, or
    # correction links to assertions whose evidence may not be granted.
    events = [
        {key: event[key] for key in ('id', 'target', 'action', 'reviewer', 'time', 'reason')}
        for event in read_events(root)
        if event['target'] in admitted
    ]
    add_note_sources(root, projected, projected, labels, scope=scope)
    conversion = managed_path(root, 'migration/conversion.json')
    outputs = json.loads(conversion.read_bytes()).get('outputs', {}) if conversion.exists() else {}
    extraction_hashes = {
        quad.object.value: outputs.get(quad.object.value)
        for quad in projected.quads_for_pattern(None, NamedNode(VOCAB + 'textPath'), None, META)
    }
    signature = canonical_hash(
        {
            'graph': sorted(map(str, projected)),
            'reviews': events,
            'classifications': [
                {key: r[key] for key in ('id', 'kind', 'classification')} for r in records
            ],
            'qualifications': [
                {**group, 'assertions': sorted(set(group['assertions']) & admitted)}
                for group in groups
                if set(group['assertions']) & admitted
            ],
            'extraction_hashes': extraction_hashes,
            'whole_dataset': scope.whole_dataset,
        }
    )
    return View(projected, records, events, scope, signature)


class ScopedSnapshot(Snapshot):
    def __init__(self, root: Path, scope: AccessScope):
        # Never invoke the owner snapshot's filesystem census in a scoped call.
        self.root, self.scope = root, scope
        self.implementation = implementation()
        self.sources: dict[str, str] = {}
        self.view = load_view(root, scope)

    def verify(self) -> None:
        if (
            self.view.signature != load_view(self.root, self.scope).signature
            or self.implementation != implementation()
        ):
            raise ValueError('Inputs changed during evaluation; retry with stable inputs')
        self.verify_sources()

    def manifest(self) -> dict[str, Any]:
        return {
            'view_sha256': self.view.signature,
            'verified_files': dict(sorted(self.sources.items())),
        }
