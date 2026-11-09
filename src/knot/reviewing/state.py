"""Read and replay immutable review events before identity projection."""

from pathlib import Path

from pyoxigraph import NamedNode, Quad, RdfFormat, Store

from knot.graph.rdf import DERIVED, META, RDF_TYPE, VOCAB, one, values
from knot.shared.storage import digest, managed_path

EVENTS = NamedNode('urn:knot:review-events')


def fingerprint(store, target):
    triples = list(store.quads_for_pattern(None, None, None, NamedNode(target)))
    if len(triples) != 1:
        raise ValueError(f'Unknown assertion or invalid domain triple count: {target}')
    ignored = {VOCAB + 'reviewStatus', VOCAB + 'lifecycle'}
    metadata = [
        q
        for q in store.quads_for_pattern(NamedNode(target), None, None, META)
        if q.predicate.value not in ignored
    ]
    for evidence in values(store, target, DERIVED):
        metadata.extend(store.quads_for_pattern(evidence, None, None, META))
        for revision in values(store, evidence.value, VOCAB + 'revision'):
            metadata.extend(store.quads_for_pattern(revision, None, None, META))
    return digest('\n'.join(sorted(map(str, triples + metadata))).encode())


def set_value(store, target, predicate, value):
    for quad in list(store.quads_for_pattern(NamedNode(target), NamedNode(predicate), None, META)):
        store.remove(quad)
    store.add(Quad(NamedNode(target), NamedNode(predicate), NamedNode(value), META))


def read_events(root):
    root = Path(root).resolve()
    events = []
    for path in sorted(managed_path(root, 'reviews/events').glob('*.trig')):
        path = managed_path(root, path.relative_to(root))
        store = Store()
        store.load(path=path, format=RdfFormat.TRIG)
        subjects = [
            q.subject.value
            for q in store.quads_for_pattern(
                None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'ReviewEvent'), EVENTS
            )
        ]
        if len(subjects) != 1:
            raise ValueError(f'Invalid review event: {path}')
        event = {'id': subjects[0], 'store': store}
        for key in ('target', 'fingerprint', 'action', 'reviewer', 'time', 'reason', 'previous'):
            event[key] = one(store, event['id'], VOCAB + key, EVENTS).value
        replacement = values(store, event['id'], VOCAB + 'replacement', EVENTS)
        if replacement:
            event['replacement_id'] = replacement[0].value
        events.append(event)
    # Time is descriptive, not an ordering authority. The predecessor chain orders events.
    ordered, previous = [], 'urn:knot:review:start'
    while events:
        next_events = [e for e in events if e['previous'] == previous]
        if len(next_events) != 1:
            raise ValueError('Conflicting or disconnected review history; reconcile events')
        event = next_events[0]
        ordered.append(event)
        events.remove(event)
        previous = event['id']
    return ordered


def apply_reviews(store, root, history=False):
    for event in read_events(root):
        target = event['target']
        if fingerprint(store, target) != event['fingerprint']:
            raise ValueError(f'Reviewed assertion changed; reconcile before querying: {target}')
        if one(store, target, VOCAB + 'lifecycle').value != VOCAB + 'Active':
            raise ValueError(f'Review targets a superseded assertion: {target}')
        for quad in event['store']:
            store.add(quad)
        if event['action'] == 'correct':
            set_value(store, target, VOCAB + 'lifecycle', VOCAB + 'Superseded')
        elif event['action'] in ('accept', 'reject'):
            set_value(
                store,
                target,
                VOCAB + 'reviewStatus',
                VOCAB + ('Accepted' if event['action'] == 'accept' else 'Rejected'),
            )
        else:
            raise ValueError(f'Unknown review action: {event["action"]}')
    if not history:
        targets = [
            q.subject.value
            for q in store.quads_for_pattern(
                None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Assertion'), META
            )
        ]
        for target in targets:
            if (
                one(store, target, VOCAB + 'reviewStatus').value == VOCAB + 'Rejected'
                or one(store, target, VOCAB + 'lifecycle').value != VOCAB + 'Active'
            ):
                for quad in list(store.quads_for_pattern(None, None, None, NamedNode(target))):
                    store.remove(quad)
    return store


def inspect_assertion(store, target):
    if NamedNode(VOCAB + 'Assertion') not in values(store, target, RDF_TYPE):
        raise ValueError(f'Unknown assertion: {target}')
    result = {
        'id': target,
        'status': one(store, target, VOCAB + 'reviewStatus').value.removeprefix(VOCAB),
        'lifecycle': one(store, target, VOCAB + 'lifecycle').value.removeprefix(VOCAB),
        'rationale': one(store, target, VOCAB + 'rationale').value,
        'origin': one(store, target, VOCAB + 'origin').value.removeprefix(VOCAB),
        'subject_label': one(store, target, VOCAB + 'subjectLabel').value,
        'object_label': one(store, target, VOCAB + 'objectLabel').value,
        'triples': [str(q) for q in store.quads_for_pattern(None, None, None, NamedNode(target))],
        'evidence': [],
        'history': [],
    }
    for evidence in values(store, target, DERIVED):
        revision = one(store, evidence.value, VOCAB + 'revision')
        result['evidence'].append(
            {
                'id': evidence.value,
                'quote': one(store, evidence.value, VOCAB + 'quote').value,
                'snapshot': one(store, revision.value, VOCAB + 'snapshotPath').value,
                'sha256': one(store, revision.value, VOCAB + 'sha256').value,
            }
        )
    for quad in store.quads_for_pattern(
        None, NamedNode(VOCAB + 'target'), NamedNode(target), EVENTS
    ):
        event_id = quad.subject.value
        result['history'].append(
            {
                'id': event_id,
                **{
                    key: one(store, event_id, VOCAB + key, EVENTS).value
                    for key in ('action', 'reviewer', 'time', 'reason', 'previous')
                },
            }
        )
    result['history'].sort(key=lambda e: (e['time'], e['id']))
    event_ids = {
        q.subject.value
        for q in store.quads_for_pattern(
            None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'ReviewEvent'), EVENTS
        )
    }
    predecessors = {
        q.object.value
        for q in store.quads_for_pattern(None, NamedNode(VOCAB + 'previous'), None, EVENTS)
    }
    heads = event_ids - predecessors
    result['latest_event'] = next(iter(heads)) if heads else 'urn:knot:review:start'
    return result
