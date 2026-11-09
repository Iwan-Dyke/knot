"""Explicit source-account qualifications, separate from claims and identity."""

import json

from pyoxigraph import NamedNode

from knot.curating.provenance import validate_sources
from knot.graph.rdf import DERIVED, RDF_TYPE, VOCAB, one, values
from knot.shared.storage import managed_path

CONTEXT_FIELDS = ('id', 'relationship', 'qualification', 'reviewer')


def _validate_group(group):
    if set(group) != {*CONTEXT_FIELDS, 'assertions', 'sources'}:
        raise ValueError('Evidence account groups require members, qualification and provenance')
    for key in ('id', 'qualification', 'reviewer'):
        if not isinstance(group[key], str) or not group[key].strip():
            raise ValueError(f'Evidence account group requires a nonempty {key}')
    if group['relationship'] not in ('RepeatedAccount', 'OverlapUnresolved'):
        raise ValueError('Invalid evidence account relationship')
    members = group['assertions']
    if (
        not isinstance(members, list)
        or not members
        or any(not isinstance(member, str) for member in members)
        or len(set(members)) != len(members)
    ):
        raise ValueError('Evidence account members must be unique assertion IRIs')
    for member in members:
        NamedNode(member)


def _covered(reader, assertion, pins):
    revisions = {pin['revision'] for pin in pins}
    for evidence in values(reader.store, assertion, DERIVED):
        if one(reader.store, evidence.value, VOCAB + 'revision').value not in revisions:
            continue
        quote, source = reader.citation(evidence.value)
        offset = source['locator'].get('characterOffset')
        if offset is None:
            text, _ = reader.revision(source['revision'])
            offset = text.index(quote)
            if text.find(quote, offset + 1) != -1:
                continue
        offset = int(offset)
        for pin in pins:
            relative = offset - pin['character_offset']
            if (
                pin['revision'] == source['revision']
                and pin['sha256'] == source['sha256']
                and pin['text_sha256'] == source['text_sha256']
                and relative >= 0
                and pin['quote'][relative : relative + len(quote)] == quote
            ):
                return True
    return False


def annotate_accounts(root, store, records, *, scope=None):
    """Copy qualified records after access filtering; never infer account equivalence."""
    from knot.retrieval_engine.evidence import _Evidence

    result = [
        {
            key: value
            for key, value in record.items()
            if key not in ('evidence_accounts', '_evidence_account_spans')
        }
        for record in records
    ]
    path = managed_path(root, 'curation/evidence-accounts.json')
    if not path.exists():
        return result
    data = json.loads(path.read_text(encoding='utf-8'))
    if (
        not isinstance(data, dict)
        or set(data) != {'schema_version', 'groups'}
        or type(data['schema_version']) is not int
        or data['schema_version'] != 1
        or not isinstance(data['groups'], list)
    ):
        raise ValueError('Invalid evidence account catalogue')
    grants = dict(scope.revisions) if scope is not None and not scope.whole_dataset else None
    visible = {record['id'] for record in result}
    contexts, spans, seen, reader = {}, {}, set(), None
    for group in data['groups']:
        if not isinstance(group, dict):
            raise ValueError('Invalid evidence account group')
        members, pins = group.get('assertions'), group.get('sources')
        present = (
            visible.intersection(m for m in members if isinstance(m, str))
            if isinstance(members, list)
            else set()
        )
        if grants is not None and (
            not present
            or not isinstance(pins, list)
            or not pins
            or any(
                not isinstance(pin, dict)
                or not isinstance(pin.get('revision'), str)
                or pin['revision'] not in grants
                or grants.get(pin['revision']) != pin.get('sha256')
                for pin in pins
            )
        ):
            # A hidden group must not expose qualifications or cause source reads.
            continue
        _validate_group(group)
        if group['id'] in seen:
            raise ValueError('Duplicate evidence account group')
        seen.add(group['id'])
        for member in members if grants is None else present:
            if NamedNode(VOCAB + 'Assertion') not in values(store, member, RDF_TYPE):
                raise ValueError('Unknown evidence account assertion')
        if not present:
            continue
        reader = reader or _Evidence(root, store, verify_derivation=False)
        validate_sources(root, pins, store=store, reader=reader)
        context = {key: group[key] for key in CONTEXT_FIELDS}
        verified_spans = [
            {
                **{key: pin[key] for key in ('revision', 'sha256', 'text_sha256')},
                'start': pin['character_offset'],
                'end': pin['character_offset'] + len(pin['quote']),
                'context': context,
            }
            for pin in pins
        ]
        for member in present:
            if not _covered(reader, member, pins):
                raise ValueError('Evidence account pin does not cover a member citation')
            contexts.setdefault(member, []).append(context)
            spans.setdefault(member, []).extend(verified_spans)
    for record in result:
        if record['id'] in contexts:
            record['evidence_accounts'] = contexts[record['id']]
            # Text selection reuses verified spans without rereading the catalogue or sources.
            record['_evidence_account_spans'] = spans[record['id']]
    return result
