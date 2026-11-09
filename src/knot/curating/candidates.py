"""Prepare and publish owner-local assertion candidates using existing evidence/review APIs."""

import argparse
import fcntl
import json
from datetime import datetime
from pathlib import Path

from pyoxigraph import Literal, NamedNode, RdfFormat, Store

from knot.curating.provenance import _Sources, _validate_pins
from knot.curating.rules import relationship_warnings, validate_relationship
from knot.graph.query import identity_bindings
from knot.graph.rdf import (
    ATTRIBUTED,
    DERIVED,
    META,
    RDF_TYPE,
    VOCAB,
    Dataset,
    identifier,
    write_bytes,
)
from knot.reviewing.state import apply_reviews
from knot.shared.datasets import cli_data_root
from knot.writing.notes import REVISION

FIELDS = {
    'id',
    'subject',
    'predicate',
    'object',
    'origin',
    'rationale',
    'agent',
    'generated_at',
    'sources',
}


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Candidate requires nonempty {field}')
    return value


def _iri(value, field):
    return NamedNode(_text(value, field))


def _endpoint(value, *, literal=False):
    if not isinstance(value, dict):
        raise ValueError('Candidate endpoints require explicit identifiers and labels')
    _text(value.get('label'), 'endpoint label')
    if set(value) == {'id', 'label'}:
        return _iri(value['id'], 'endpoint IRI')
    if not literal or 'value' not in value or not isinstance(value['value'], str):
        raise ValueError('Invalid candidate endpoint fields')
    if set(value) not in (
        {'value', 'label'},
        {'value', 'label', 'datatype'},
        {'value', 'label', 'language'},
    ):
        raise ValueError('Literal requires value and optional datatype or language, not both')
    if 'datatype' in value:
        return Literal(value['value'], datatype=_iri(value['datatype'], 'literal datatype'))
    if 'language' in value:
        return Literal(value['value'], language=_text(value['language'], 'literal language'))
    return Literal(value['value'])


def _safe_path(root, relative):
    from knot.shared.storage import managed_path

    return managed_path(root, relative)


def _raw_store(root):
    store = Store()
    for path in sorted(_safe_path(root, 'graph').glob('*.trig')):
        store.load(path=_safe_path(root, path.relative_to(root)), format=RdfFormat.TRIG)
    return store


def validate_classification(root, classification):
    if classification is not None:
        from knot.shared.vocabulary import KINDS
        from knot.writing.navigation import theme_choices

        if (
            not isinstance(classification, dict)
            or set(classification) != {'kind', 'themes'}
            or classification['kind'] not in KINDS
            or not isinstance(classification['themes'], list)
            or any(
                t not in {v['id'] for v in theme_choices(root)} for t in classification['themes']
            )
        ):
            raise ValueError('Invalid candidate classification')


def prepare_candidate(root, candidate):
    """Validate explicit caller-supplied knowledge and return a read-only publication preview.

    No extraction, identity resolution by label, acceptance or semantic truth checking
    occurs. Callers must provide a stable ID and timestamp and retain them on retry.
    This is an owner operation, never an alternative to a denied scoped MCP request.
    """
    root = Path(root).resolve()
    if not isinstance(candidate, dict) or set(candidate) - {'classification'} != FIELDS:
        raise ValueError('Candidate requires exactly: ' + ', '.join(sorted(FIELDS)))
    classification = candidate.get('classification')
    validate_classification(root, classification)
    aid = _iri(candidate['id'], 'assertion IRI')
    if not aid.value.startswith('urn:knot:assertion:') or aid.value == 'urn:knot:assertion:':
        raise ValueError('New candidate IDs must use the urn:knot:assertion: namespace')
    subject = _endpoint(candidate['subject'])
    obj = _endpoint(candidate['object'], literal=True)
    predicate = _iri(candidate['predicate'], 'predicate IRI')
    agent = _iri(candidate['agent'], 'generating agent IRI')
    validate_relationship(subject, predicate, obj)
    if candidate['origin'] not in ('Explicit', 'Inferred'):
        raise ValueError('Candidate origin must be Explicit or Inferred')
    _text(candidate['rationale'], 'rationale')
    stamp = datetime.fromisoformat(_text(candidate['generated_at'], 'generation time'))
    if stamp.tzinfo is None:
        raise ValueError('Candidate generation time requires a timezone')
    _validate_pins(candidate['sources'])
    if aid in {subject, obj, agent, predicate} or aid.value in {
        pin['revision'] for pin in candidate['sources']
    }:
        raise ValueError('Assertion identifier collision with another resource role')

    # The source verifier owns hashes, locators, ancestry and derived input closure.
    verifier = _Sources(root, None)
    accounts = set()
    for pin in candidate['sources']:
        accounts.update(verifier.verify(pin, set()))
    dataset = Dataset()
    dataset.graphs[aid.value].add(f'{subject} {predicate} {obj} .')
    dataset.add(aid.value, RDF_TYPE, VOCAB + 'Assertion')
    for key, value in (
        ('reviewStatus', 'Unreviewed'),
        ('lifecycle', 'Active'),
        ('origin', candidate['origin']),
    ):
        dataset.add(aid.value, VOCAB + key, VOCAB + value)
    for key, value in (
        ('subjectLabel', candidate['subject']['label']),
        ('objectLabel', candidate['object']['label']),
        ('rationale', candidate['rationale']),
        ('generatedAt', candidate['generated_at']),
    ):
        dataset.add(aid.value, VOCAB + key, value, literal=True)
    dataset.add(aid.value, ATTRIBUTED, agent.value)
    if classification is not None:
        dataset.add(
            aid.value,
            VOCAB + 'authorClassification',
            json.dumps(classification, sort_keys=True),
            literal=True,
        )
    evidence_ids = set()
    for pin in candidate['sources']:
        eid = identifier('evidence', aid.value + '\0' + json.dumps(pin, sort_keys=True))
        evidence_ids.add(NamedNode(eid))
        dataset.add(aid.value, DERIVED, eid)
        dataset.add(eid, VOCAB + 'revision', pin['revision'])
        for key, value in (
            ('quote', pin['quote']),
            ('characterOffset', pin['character_offset']),
            ('startLine', pin['start_line']),
            ('locatorKind', 'source_character_offset'),
        ):
            dataset.add(eid, VOCAB + key, value, literal=True)
        if pin['revision'].startswith(REVISION):
            _, source = verifier.read(pin['revision'])
            # Only durable source registration belongs in additions. The native
            # adapter supplies manifest and author metadata in eligible read views.
            dataset.add(pin['revision'], VOCAB + 'snapshotPath', source['snapshot'], literal=True)
            dataset.add(pin['revision'], VOCAB + 'sha256', source['sha256'], literal=True)
    roles = {aid, subject, obj, agent, predicate}
    roles.update(NamedNode(pin['revision']) for pin in candidate['sources'])
    if evidence_ids & roles:
        raise ValueError('Evidence identifier collision with another resource role')
    rdf = dataset.text()
    proposed = Store()
    proposed.load(input=rdf, format=RdfFormat.TRIG)
    raw = _raw_store(root)
    owned = {aid, *evidence_ids}

    def fragment(store):
        return {
            quad
            for quad in store
            if quad.graph_name == aid or (quad.graph_name == META and quad.subject in owned)
        }

    existing = bool(fragment(raw))
    if existing:
        if fragment(raw) != fragment(proposed) or not set(proposed) <= set(raw):
            raise ValueError('Assertion identifier collision; use the explicit correction workflow')
    elif any(
        q.subject in owned or q.graph_name in owned or q.object in owned for q in verifier.store
    ):
        raise ValueError('Assertion/evidence identifier collision with an existing resource')

    bindings = identity_bindings(verifier.store)
    canonical_subject, canonical_object = bindings.get(subject, subject), bindings.get(obj, obj)

    def types(node):
        return {
            q.object.value
            for q in verifier.store
            if q.predicate == NamedNode(RDF_TYPE) and bindings.get(q.subject, q.subject) == node
        }

    warnings = relationship_warnings(
        predicate.value,
        types(canonical_subject),
        object_types=types(canonical_object),
        quotes=[pin['quote'] for pin in candidate['sources']],
        object_label=candidate['object']['label'],
        subject=canonical_subject,
        object=canonical_object,
    )
    from knot.diagnostics.quality import name_warnings

    for endpoint in ('subject', 'object'):
        if 'id' in candidate[endpoint]:
            warnings.extend(
                {'endpoint': endpoint, **warning}
                for warning in name_warnings(candidate[endpoint]['label'])
            )
    return {
        'assertion': aid.value,
        'rdf': rdf,
        'warnings': warnings,
        'source_accounts': sorted(accounts),
        'already_published': existing,
    }


def publish_candidate(root, candidate):
    """Append a validated candidate atomically; never replace assertions or accept claims."""
    root = Path(root).resolve()
    # Fail invalid input before even creating a lock. Recheck under the same lock
    # used by review writes so retry cannot undo an intervening owner decision.
    prepare_candidate(root, candidate)
    path = _safe_path(root, 'graph/additions.trig')
    lock_path = _safe_path(root, 'reviews/.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        prepared = prepare_candidate(root, candidate)
        if not prepared['already_published']:
            original = path.read_bytes() if path.exists() else b''
            content = original + b'\n' + prepared['rdf'].encode('utf-8')
            combined = Store()
            combined.load(input=content, format=RdfFormat.TRIG)
            replay = _raw_store(root)
            replay.load(input=prepared['rdf'], format=RdfFormat.TRIG)
            apply_reviews(replay, root, history=True)
            write_bytes(path, content)
    return {
        key: value for key, value in prepared.items() if key not in ('rdf', 'already_published')
    } | {'created': not prepared['already_published']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('action', choices=('check', 'publish'))
    parser.add_argument(
        'file', type=Path, help='JSON assertion candidate with verified source pins'
    )
    args = parser.parse_args(argv)
    args.data_root = cli_data_root(parser, args.data_root)
    try:
        candidate = json.loads(args.file.read_bytes())
        function = prepare_candidate if args.action == 'check' else publish_candidate
        result = function(args.data_root, candidate)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, OSError, TypeError) as error:
        parser.exit(1, f'Curation failed: {error}\n')


if __name__ == '__main__':
    main()
