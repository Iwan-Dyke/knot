"""Synthetic source-first retrieval corpus, shared with the evaluation harness."""

from knot.inventory import digest
from knot.knowledge import build_organisation
from knot.query import load_store
from knot.rdf import DERIVED, LABEL, RDF_TYPE, VOCAB, Dataset

SEED = 'urn:project:orion'
WORK = 'urn:work:recovery'
SOURCE_WORK = 'urn:mention:recovery'
CLAIM_SOURCE = 'urn:mention:dependency'
ROUTE = 'urn:assertion:association'
CLAIM = 'urn:assertion:dependency'
MISSING = 'urn:assertion:unlinked'

# Labels were chosen from these source accounts before running any retrieval mode.
QUESTIONS = [
    {'query': 'Orion survey feed', 'seed': SEED, 'relevant': [CLAIM]},
    {'query': 'Orion retries', 'seed': SEED, 'relevant': [MISSING]},
    {'query': 'Orion budget constraints', 'seed': SEED, 'relevant': []},
]


def make_fixture(root):
    (root / 'graph').mkdir(parents=True)
    (root / 'sources').mkdir()
    dataset = Dataset()

    def claim(
        aid,
        subject,
        predicate,
        obj,
        quote,
        *,
        file=None,
        text=None,
        literal=False,
        status='Accepted',
    ):
        file = file or aid.rsplit(':', 1)[-1] + '.md'
        text = text or quote + '\n'
        (root / 'sources' / file).write_text(text)
        revision = 'urn:revision:' + digest(text.encode())
        evidence = aid + ':evidence'
        dataset.add(subject, predicate, obj, literal=literal, graph=aid)
        dataset.add(aid, RDF_TYPE, VOCAB + 'Assertion')
        for key, value in [
            ('reviewStatus', status),
            ('origin', 'Explicit'),
            ('lifecycle', 'Active'),
        ]:
            dataset.add(aid, VOCAB + key, VOCAB + value)
        for key, value in [
            ('subjectLabel', subject),
            ('objectLabel', obj),
            ('rationale', 'Source account'),
        ]:
            dataset.add(aid, VOCAB + key, value, literal=True)
        dataset.add(aid, DERIVED, evidence)
        dataset.add(evidence, VOCAB + 'revision', revision)
        dataset.add(evidence, VOCAB + 'quote', quote, literal=True)
        dataset.add(evidence, VOCAB + 'locatorKind', 'source_line', literal=True)
        dataset.add(evidence, VOCAB + 'characterOffset', text.index(quote), literal=True)
        dataset.add(revision, VOCAB + 'snapshotPath', 'sources/' + file, literal=True)
        dataset.add(revision, VOCAB + 'sha256', digest(text.encode()), literal=True)
        document = 'urn:document:' + file
        dataset.add(document, RDF_TYPE, VOCAB + 'Document')
        dataset.add(document, VOCAB + 'revision', revision)
        return evidence, revision

    claim(
        ROUTE,
        SOURCE_WORK,
        VOCAB + 'relatedTo',
        SEED,
        'Recovery belongs to Orion.',
        status='Unreviewed',
    )
    claim(
        CLAIM,
        CLAIM_SOURCE,
        VOCAB + 'dependsOn',
        'urn:dependency:feed',
        'The survey feed is missing.',
        text='# Orion recovery\nThe survey feed is missing.\n',
    )
    claim(
        MISSING,
        'urn:work:storage',
        VOCAB + 'reportedOutcome',
        'urn:outcome:retries',
        'Retries remain untested.',
        text='# Orion support\nRetries remain untested.\n',
    )
    claim(
        'urn:assertion:distractor',
        'urn:project:other',
        VOCAB + 'madeDecision',
        'urn:decision:budget',
        'Budget constraints concern the unrelated telescope.',
        text='# Orion telescope\nBudget constraints concern the unrelated telescope.\n',
    )
    claim(
        'urn:assertion:author', 'urn:person:alex', VOCAB + 'workedOn', SEED, 'Alex worked on Orion.'
    )
    claim(
        'urn:assertion:other-work',
        'urn:person:alex',
        VOCAB + 'workedOn',
        'urn:project:other',
        'Alex worked on the telescope.',
    )
    claim(
        'urn:assertion:framework',
        'urn:competency:review',
        'http://www.w3.org/2004/02/skos/core#definition',
        'Review evidence carefully.',
        'Review evidence carefully.',
        literal=True,
    )
    dataset.add('urn:assertion:framework', VOCAB + 'recordKind', VOCAB + 'FrameworkDefinition')
    dataset.add('urn:person:alex', RDF_TYPE, VOCAB + 'Person')
    for eid, label in [
        (SEED, 'Orion'),
        ('urn:project:other', 'Orion'),
        (SOURCE_WORK, 'Recovery'),
        ('urn:person:alex', 'Alex'),
    ]:
        dataset.add(eid, LABEL, label, literal=True)
    for mid, source, target, status in [
        ('urn:mapping:recovery', SOURCE_WORK, WORK, 'Accepted'),
        ('urn:mapping:dependency', CLAIM_SOURCE, WORK, 'Accepted'),
        ('urn:mapping:other', 'urn:project:other', SEED, 'Unreviewed'),
    ]:
        dataset.add(mid, VOCAB + 'sourceEntity', source)
        dataset.add(mid, VOCAB + 'entity', target)
        dataset.add(mid, VOCAB + 'reviewStatus', VOCAB + status)
        dataset.add(mid, VOCAB + 'rationale', 'Source identity', literal=True)
    (root / 'graph/claims.trig').write_text(dataset.text())
    catalogue = {
        'themes': [{'id': 'shared', 'label': 'Shared', 'keywords': ['Orion']}],
        'entity_types': {'Person': ['urn:person:alex']},
        'overrides': {CLAIM: {'kind': 'Thought'}},
    }
    (root / 'graph/organisation.trig').write_bytes(
        build_organisation(load_store(root / 'graph'), catalogue)
    )
    return dataset
