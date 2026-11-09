"""Persist human review decisions as immutable RDF events."""

import argparse
import fcntl
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pyoxigraph import Literal, NamedNode, RdfFormat, Store

from knot.curating.rules import validate_relationship
from knot.graph.rdf import (
    ATTRIBUTED,
    DERIVED,
    META,
    RDF_TYPE,
    VOCAB,
    Dataset,
    one,
    values,
    write_bytes,
)
from knot.reviewing.state import EVENTS as EVENTS
from knot.reviewing.state import apply_reviews as apply_reviews
from knot.reviewing.state import fingerprint as fingerprint
from knot.reviewing.state import inspect_assertion as inspect_assertion
from knot.reviewing.state import read_events as read_events
from knot.reviewing.state import set_value as set_value
from knot.shared.datasets import cli_data_root
from knot.shared.storage import digest, managed_path


def decide(
    root,
    target,
    action,
    *,
    reviewer,
    reason,
    replacement=None,
    accept_replacement=False,
    expected=None,
):
    from knot.graph.query import load_store

    root = Path(root).resolve()
    if not reviewer.strip() or not reason.strip() or action not in ('accept', 'reject', 'correct'):
        raise ValueError('A valid action, reviewer and reason are required')
    if action == 'correct':
        required = ('subject', 'predicate', 'object', 'subject_label', 'object_label', 'rationale')
        if not isinstance(replacement, dict) or any(
            not isinstance(replacement.get(key), str) or not replacement[key].strip()
            for key in required
        ):
            raise ValueError(f'Replacement requires: {", ".join(required)}')
        literal = replacement.get('object_is_literal', False)
        if type(literal) is not bool:
            raise ValueError('Replacement object_is_literal must be a boolean')
        validate_relationship(
            NamedNode(replacement['subject']),
            NamedNode(replacement['predicate']),
            Literal(replacement['object']) if literal else NamedNode(replacement['object']),
        )
    directory = managed_path(root, 'reviews/events')
    directory.mkdir(parents=True, exist_ok=True)
    with managed_path(root, 'reviews/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        store = load_store(root / 'graph', history=True, include_notes=False)
        detail = inspect_assertion(store, target)
        if detail['lifecycle'] != 'Active':
            raise ValueError('Cannot review a superseded assertion')
        events = read_events(root)
        previous = events[-1]['id'] if events else 'urn:knot:review:start'
        if expected is not None and expected != previous:
            raise ValueError('Review state changed; inspect the assertion again')
        additional_sources = []
        if action == 'correct':
            additional_sources = replacement.get('additional_sources', [])
            if not isinstance(additional_sources, list):
                raise ValueError('Additional correction sources must be a list of source pins')
            if additional_sources:
                from knot.curating.provenance import _validate_pins

                _validate_pins(additional_sources)
        if action in ('accept', 'correct'):
            from knot.retrieval_engine.evidence import _Evidence
            from knot.writing.notes import REVISION
            from knot.writing.sources import add_note_sources

            if not detail['evidence']:
                raise ValueError('Acceptance and correction require source evidence')
            # Native adapter metadata belongs only in this verification view;
            # fingerprints must retain the original, replayable assertion inputs.
            verification = Store()
            for quad in store:
                verification.add(quad)
            revisions = {
                one(store, evidence['id'], VOCAB + 'revision').value
                for evidence in detail['evidence']
            }
            for pin in additional_sources:
                # Corrections may extend context within registered immutable sources;
                # they cannot ingest a new revision or silently change its source hash.
                if one(store, pin['revision'], VOCAB + 'sha256').value != pin['sha256']:
                    raise ValueError('Additional correction source hash mismatch')
                revisions.add(pin['revision'])
            for revision in sorted(revisions):
                if revision.startswith(REVISION):
                    add_note_sources(root, verification, verification, {}, note_revision=revision)
            reader = _Evidence(root, verification)
            for evidence in detail['evidence']:
                reader.citation(evidence['id'])
            if additional_sources:
                from knot.curating.provenance import validate_sources

                validate_sources(root, additional_sources, reader=reader)
        else:
            for evidence in detail['evidence']:
                snapshot = managed_path(root, evidence['snapshot'])
                if (
                    not snapshot.is_relative_to(root.resolve())
                    or digest(snapshot.read_bytes()) != evidence['sha256']
                ):
                    raise ValueError('Evidence snapshot missing, unsafe or changed')
                if snapshot.suffix.lower() in ('.org', '.md', '.txt') and evidence[
                    'quote'
                ] not in snapshot.read_bytes().decode('utf-8-sig'):
                    raise ValueError('Evidence quotation does not match its source')
        event_id = 'urn:knot:review:' + str(uuid4())
        dataset = Dataset()
        data = {
            'target': target,
            'fingerprint': fingerprint(store, target),
            'action': action,
            'reviewer': reviewer,
            'reason': reason,
            'time': datetime.now(timezone.utc).isoformat(),
            'previous': previous,
        }
        dataset.add(event_id, RDF_TYPE, VOCAB + 'ReviewEvent', graph=EVENTS.value)
        for key, value in data.items():
            dataset.add(
                event_id,
                VOCAB + key,
                value,
                literal=key not in ('target', 'previous'),
                graph=EVENTS.value,
            )
        if action == 'correct':
            new_id = event_id + ':replacement'
            dataset.add(event_id, VOCAB + 'replacement', new_id, graph=EVENTS.value)
            dataset.add(new_id, VOCAB + 'supersedes', target)
            dataset.add(
                replacement['subject'],
                replacement['predicate'],
                replacement['object'],
                literal=replacement.get('object_is_literal', False),
                graph=new_id,
            )
            for key, value in [
                ('reviewStatus', 'Accepted' if accept_replacement else 'Unreviewed'),
                ('origin', 'Inferred'),
                ('lifecycle', 'Active'),
            ]:
                dataset.add(new_id, VOCAB + key, VOCAB + value)
            dataset.add(new_id, RDF_TYPE, VOCAB + 'Assertion')
            # Corrections must stay in the original view and framework scope.
            for key in ('recordKind', 'framework'):
                for value in values(store, target, VOCAB + key):
                    dataset.add(new_id, VOCAB + key, value.value)
            for key, value in [
                ('subjectLabel', replacement['subject_label']),
                ('objectLabel', replacement['object_label']),
                ('rationale', replacement['rationale']),
                ('generatedAt', data['time']),
            ]:
                dataset.add(new_id, VOCAB + key, value, literal=True)
            dataset.add(new_id, ATTRIBUTED, event_id)
            for evidence in values(store, target, DERIVED):
                dataset.add(new_id, DERIVED, evidence.value)
            for index, pin in enumerate(additional_sources):
                eid = event_id + f':evidence:{index}'
                dataset.add(new_id, DERIVED, eid)
                dataset.add(eid, VOCAB + 'revision', pin['revision'])
                for key, value in (
                    ('quote', pin['quote']),
                    ('characterOffset', pin['character_offset']),
                    ('startLine', pin['start_line']),
                    ('locatorKind', 'correction_context'),
                ):
                    dataset.add(eid, VOCAB + key, value, literal=True)
            data['replacement_id'] = new_id
        serialised = dataset.text().encode()
        validation = Store()
        validation.load(input=serialised, format=RdfFormat.TRIG)
        path = managed_path(root, 'reviews/events/' + event_id.rsplit(':', 1)[-1] + '.trig')
        write_bytes(path, serialised)
        return {'id': event_id, **data}


def main():
    from knot.graph.query import load_store

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    listing = sub.add_parser('list')
    listing.add_argument('--status', choices=['Accepted', 'Rejected', 'Unreviewed'])
    listing.add_argument('--history', action='store_true', help='Include superseded assertions')
    sub.add_parser('summary')
    show = sub.add_parser('show')
    show.add_argument('assertion')
    for action in ('accept', 'reject', 'correct'):
        command = sub.add_parser(action)
        command.add_argument('assertion')
        command.add_argument('--reviewer', required=True)
        command.add_argument('--reason', required=True)
        command.add_argument(
            '--expected', help='Expected latest review event, for concurrent edits'
        )
        if action == 'correct':
            command.add_argument('--replacement', required=True, type=Path)
            command.add_argument('--accept-replacement', action='store_true')
    args = parser.parse_args()
    args.data_root = cli_data_root(parser, args.data_root)
    try:
        if args.action in ('list', 'show', 'summary'):
            store = load_store(args.data_root / 'graph', history=True, include_notes=False)
            if args.action == 'summary':
                counts = Counter()
                for quad in store.quads_for_pattern(
                    None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META
                ):
                    detail = inspect_assertion(store, quad.subject.value)
                    counts[
                        detail['status'] if detail['lifecycle'] == 'Active' else 'Superseded'
                    ] += 1
                print(json.dumps(dict(sorted(counts.items())), indent=2))
            elif args.action == 'show':
                print(
                    json.dumps(
                        inspect_assertion(store, args.assertion), indent=2, ensure_ascii=False
                    )
                )
            else:
                for quad in store.quads_for_pattern(
                    None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META
                ):
                    detail = inspect_assertion(store, quad.subject.value)
                    if not args.history and detail['lifecycle'] != 'Active':
                        continue
                    if args.status is None or detail['status'] == args.status:
                        print(
                            json.dumps(
                                {
                                    key: detail[key]
                                    for key in (
                                        'id',
                                        'status',
                                        'lifecycle',
                                        'subject_label',
                                        'object_label',
                                    )
                                },
                                ensure_ascii=False,
                            )
                        )
        else:
            replacement = (
                json.loads(args.replacement.read_text()) if args.action == 'correct' else None
            )
            print(
                json.dumps(
                    decide(
                        args.data_root,
                        args.assertion,
                        args.action,
                        reviewer=args.reviewer,
                        reason=args.reason,
                        replacement=replacement,
                        accept_replacement=getattr(args, 'accept_replacement', False),
                        expected=args.expected,
                    ),
                    indent=2,
                )
            )
    except (ValueError, OSError) as error:
        parser.exit(1, f'Review failed: {error}\n')


if __name__ == '__main__':
    main()
