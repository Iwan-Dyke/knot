"""Organise and inspect one knowledge base through overlapping themes."""

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from pyoxigraph import Literal, NamedNode, RdfFormat, Store

from knot.graph.query import assertion_query, load_store
from knot.graph.rdf import BASE, LABEL, RDF_TYPE, VOCAB, Dataset, values, write_bytes
from knot.graph.resources import ONTOLOGY_PATH
from knot.graph.themes import memberships, read_memberships, validate_reviews, write_memberships
from knot.shared.datasets import cli_data_root
from knot.shared.storage import digest, managed_path
from knot.shared.theme_definitions import validate_themes
from knot.shared.vocabulary import KINDS as KINDS
from knot.shared.vocabulary import TYPES as TYPES
from knot.shared.vocabulary import local_name as local_name

ORG = NamedNode(BASE + 'organisation')
SCHEMA = BASE + 'ontology'
METHOD = 'catalogue-and-keywords-v1'
TYPE_MAP = {'Competency': 'Capability', 'MasteryCriterion': 'Concept', 'RoleGrade': 'RoleGrade'}


def _records(store):
    records = {}
    for row in store.query(assertion_query(all_knowledge=True)):
        aid = row['assertion'].value
        if aid not in records:
            records[aid] = {
                'id': aid,
                'subject': {'id': row['s'].value, 'label': row['subject'].value},
                'predicate': row['p'].value,
                'object': {
                    'id': row['o'].value,
                    'label': row['object'].value,
                    'literal': isinstance(row['o'], Literal),
                },
                'status': local_name(row['status'].value),
                'origin': local_name(row['origin'].value),
                'rationale': row['rationale'].value,
                'framework': NamedNode(VOCAB + 'FrameworkDefinition')
                in values(store, aid, VOCAB + 'recordKind'),
                'evidence': [],
            }
        evidence = {'quote': row['quote'].value, 'snapshot': row['snapshot'].value}
        if evidence not in records[aid]['evidence']:
            records[aid]['evidence'].append(evidence)
    for record in records.values():
        authored = values(store, record['id'], VOCAB + 'authorClassification')
        if authored:
            record['author_classification'] = json.loads(authored[0].value)
        record['evidence'].sort(key=lambda e: (e['snapshot'], e['quote']))
    return list(records.values())


def _signature(record):
    # Review acceptance alone does not change a record's meaning or classification.
    return digest(
        json.dumps(
            {k: v for k, v in record.items() if k != 'status'}, sort_keys=True, ensure_ascii=False
        ).encode()
    )


def _input_signature(records):
    return digest('\n'.join(_signature(r) for r in records).encode())


def _validate(catalogue, records):
    themes = catalogue['themes']
    validate_themes(themes)
    ids = [t['id'] for t in themes]
    unknown = set(catalogue.get('entity_types', {})) - TYPES
    if unknown:
        raise ValueError(f'Unknown entity types: {sorted(unknown)}')
    endpoints = {
        r[end]['id'] for r in records for end in ('subject', 'object') if not r[end].get('literal')
    }
    type_overrides = catalogue.get('entity_type_overrides', {})
    if not isinstance(type_overrides, dict):
        raise ValueError('Entity type overrides must map exact IRIs to supported types')
    for entity, kinds in type_overrides.items():
        if entity not in endpoints:
            raise ValueError(f'Unknown entity type override: {entity}')
        if (
            not isinstance(kinds, list)
            or not kinds
            or any(not isinstance(k, str) or k not in TYPES for k in kinds)
            or len(kinds) != len(set(kinds))
            or ('Entity' in kinds and len(kinds) > 1)
        ):
            raise ValueError(f'Invalid entity types for {entity}')
    assertions = {r['id'] for r in records}
    for aid, override in catalogue.get('overrides', {}).items():
        if aid not in assertions:
            raise ValueError(f'Unknown assertion in catalogue: {aid}')
        if override.get('kind', 'Unspecified') not in KINDS:
            raise ValueError(f'Unknown knowledge kind for {aid}')
        if set(override.get('themes', [])) - set(ids):
            raise ValueError(f'Unknown theme for {aid}')


def build_organisation(store, catalogue, *, theme_reviews=None):
    """Return deterministic navigation annotations without modifying source assertions."""
    records = _records(store)
    _validate(catalogue, records)
    definitions = {t['id']: t for t in catalogue['themes']}
    validate_reviews(theme_reviews, definitions)
    dataset = Dataset()

    def add(subject, predicate, obj, *, literal=False):
        dataset.add(subject, predicate, obj, literal=literal, graph=ORG.value)

    add(ORG.value, VOCAB + 'origin', VOCAB + 'Inferred')
    add(ORG.value, VOCAB + 'reviewStatus', VOCAB + 'Unreviewed')
    add(ORG.value, VOCAB + 'method', METHOD, literal=True)
    add(ORG.value, VOCAB + 'inputSha256', _input_signature(records), literal=True)
    if theme_reviews is not None:
        add(
            ORG.value,
            VOCAB + 'themeReviewsSha256',
            digest(json.dumps(theme_reviews, sort_keys=True, ensure_ascii=False).encode()),
            literal=True,
        )
    add(
        ORG.value,
        VOCAB + 'catalogueSha256',
        digest(json.dumps(catalogue, sort_keys=True, ensure_ascii=False).encode()),
        literal=True,
    )
    for theme in catalogue['themes']:
        tid = BASE + 'theme:' + theme['id']
        add(tid, RDF_TYPE, VOCAB + 'Theme')
        add(tid, LABEL, theme['label'], literal=True)
        if theme.get('description'):
            add(
                tid,
                'http://www.w3.org/2000/01/rdf-schema#comment',
                theme['description'],
                literal=True,
            )

    entity_types = defaultdict(set)
    for record in records:
        aid = record['id']
        predicate = local_name(record['predicate'])
        override = {
            **record.get('author_classification', {}),
            **catalogue.get('overrides', {}).get(aid, {}),
        }
        kind = 'Statement'
        if record['framework']:
            kind = 'Definition'
        elif predicate == 'reportedOutcome':
            kind = 'Observation'
        elif predicate in ('supports', 'demonstrates'):
            kind = 'Assessment'
        elif predicate == 'proposed':
            kind = 'Idea'
        kind = override.get('kind', kind)
        text = ' '.join(
            [
                record['subject']['label'],
                record['object']['label'],
                *(e['quote'] for e in record['evidence']),
            ]
        ).casefold()
        matches = {
            t['id']: [
                w
                for w in t.get('keywords', [])
                if re.search(r'(?<!\w)' + re.escape(w.casefold()) + r'(?!\w)', text)
            ]
            for t in catalogue['themes']
        }
        themes = override.get(
            'themes',
            [
                t['id']
                for t in catalogue['themes']
                if matches[t['id']] or (record['framework'] and t.get('include_frameworks'))
            ],
        )
        rationale = f'{METHOD}; kind {kind} from '
        rationale += (
            'catalogue override' if 'kind' in override else f'predicate/record kind ({predicate})'
        )
        rationale += '; initial theme suggestions from ' + (
            'catalogue override'
            if 'themes' in override
            else json.dumps(
                {t: matches[t] or ['framework record'] for t in themes},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        if override.get('rationale'):
            rationale += '; ' + override['rationale']
        add(aid, VOCAB + 'knowledgeKind', VOCAB + kind)
        add(aid, VOCAB + 'organisationFingerprint', _signature(record), literal=True)
        add(aid, VOCAB + 'organisationRationale', rationale, literal=True)
        reviewed = memberships(aid, _signature(record), definitions, themes, theme_reviews)
        write_memberships(add, aid, reviewed)
        themes = [t['id'] for t in reviewed if t['status'] != 'Rejected']
        for theme in themes:
            add(aid, VOCAB + 'theme', BASE + 'theme:' + theme)
        for position in ('subject', 'object'):
            entity = record[position]
            if entity.get('literal'):
                continue
            eid = entity['id']
            types = entity_types[eid]
            types.update(
                t
                for t, labels in catalogue.get('entity_types', {}).items()
                if entity['label'] in labels
            )
            for term in values(store, eid, RDF_TYPE):
                name = local_name(term.value)
                if name in TYPE_MAP:
                    types.add(TYPE_MAP[name])
                elif name == 'ConceptScheme':
                    types.add('Framework')
                elif name in TYPES:
                    types.add(name)
            if position == 'object' and predicate == 'reportedOutcome':
                types.add('Outcome')
            if position == 'object' and predicate == 'madeDecision':
                types.add('Decision')
            if position == 'subject' and predicate == 'decisionAbout':
                types.add('Decision')
            add(eid, VOCAB + 'organisedFrom', aid)
            for theme in themes:
                add(eid, VOCAB + 'theme', BASE + 'theme:' + theme)
    for eid, types in entity_types.items():
        types = catalogue.get('entity_type_overrides', {}).get(eid, types)
        for entity_type in types or {'Entity'}:
            add(eid, RDF_TYPE, VOCAB + entity_type)
    return dataset.text().encode()


def entries(store, *, themes=None, kind=None):
    """Return active source-backed records across all domains; themes use OR matching."""
    available = {
        q.subject.value: values(store, q.subject.value, LABEL, ORG)[0].value
        for q in store.quads_for_pattern(None, NamedNode(RDF_TYPE), NamedNode(VOCAB + 'Theme'), ORG)
    }
    selected = {BASE + 'theme:' + t for t in themes or []}
    if selected - available.keys():
        raise ValueError(f'Unknown theme: {sorted(selected - available.keys())}')
    if kind is not None and kind not in KINDS:
        raise ValueError(f'Unknown knowledge kind: {kind}')
    records = _records(store)
    # Entity types aggregate several assertions. A removed or changed premise can
    # invalidate classifications beyond that one record; rebuild the whole overlay.
    inputs_current = values(store, ORG.value, VOCAB + 'inputSha256', ORG) == [
        Literal(_input_signature(records))
    ]
    result = []
    for record in records:
        aid = record['id']
        saved = values(store, aid, VOCAB + 'organisationFingerprint', ORG)
        current = inputs_current and saved == [Literal(_signature(record))]
        kinds = values(store, aid, VOCAB + 'knowledgeKind', ORG) if current else []
        record['kind'] = local_name(kinds[0].value) if kinds else 'Unspecified'
        tids = sorted(t.value for t in values(store, aid, VOCAB + 'theme', ORG)) if current else []
        record['theme_reviews'] = read_memberships(store, aid, ORG, available) if current else []
        reviewed = {t['id']: t for t in record['theme_reviews']}
        record['themes'] = [
            reviewed.get(
                local_name(t),
                {
                    'id': local_name(t),
                    'label': available[t],
                    'status': 'Unreviewed',
                    'review_state': 'Missing',
                },
            )
            for t in tids
        ]
        reason = values(store, aid, VOCAB + 'organisationRationale', ORG) if current else []
        record['classification'] = {
            'status': 'Unreviewed' if current else 'Stale' if saved else 'Missing',
            'origin': 'Inferred' if current else None,
            'rationale': reason[0].value
            if reason
            else 'Run just organise to classify this record.',
        }
        for position in ('subject', 'object'):
            entity = record[position]
            types = (
                values(store, entity['id'], RDF_TYPE, ORG)
                if current and not entity.get('literal')
                else []
            )
            entity['types'] = sorted(t.value.removeprefix(VOCAB) for t in types) or (
                [] if entity.get('literal') else ['Entity']
            )
        if selected and not selected.intersection(tids):
            continue
        if kind is not None and record['kind'] != kind:
            continue
        result.append(record)
    return result


def rebuild(root):
    root = Path(root).resolve()
    catalogue = json.loads(managed_path(root, 'organisation/catalogue.json').read_text())
    review_path = managed_path(root, 'organisation/theme-reviews.json')
    theme_reviews = json.loads(review_path.read_text()) if review_path.exists() else None
    store = load_store(root / 'graph', allow_empty=True)
    schema = Store()
    schema.load(path=ONTOLOGY_PATH, format=RdfFormat.TURTLE)
    ontology = Dataset()
    for quad in schema:
        ontology.add(
            quad.subject.value,
            quad.predicate.value,
            quad.object.value,
            literal=isinstance(quad.object, Literal),
            graph=SCHEMA,
        )
    outputs = {
        'graph/organisation.trig': build_organisation(
            store, catalogue, theme_reviews=theme_reviews
        ),
        'graph/ontology.trig': ontology.text().encode(),
    }
    manifest_path = managed_path(root, 'organisation/generated.json')
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    for name in outputs:
        path = managed_path(root, name)
        if path.exists() and digest(path.read_bytes()) != previous.get(name):
            raise ValueError(f'Generated output changed; reconcile before rebuilding: {path}')
    for name, content in outputs.items():
        write_bytes(managed_path(root, name), content)
    write_bytes(
        manifest_path,
        (
            json.dumps({n: digest(c) for n, c in outputs.items()}, indent=2, sort_keys=True) + '\n'
        ).encode(),
    )
    return summary(load_store(root / 'graph'))


def summary(store):
    records = entries(store)
    return {
        'assertions': len(records),
        'review_status': dict(Counter(r['status'] for r in records)),
        'knowledge_kinds': dict(Counter(r['kind'] for r in records)),
        'classification_status': dict(Counter(r['classification']['status'] for r in records)),
        'without_theme': sum(not r['themes'] for r in records),
        'themes': dict(sorted(Counter(t['id'] for r in records for t in r['themes']).items())),
        'theme_review_status': dict(
            Counter(t['status'] for r in records for t in r['theme_reviews'])
        ),
        'stale_theme_reviews': sum(
            t['review_state'] == 'Stale' for r in records for t in r['theme_reviews']
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'command', choices=('build', 'show', 'summary'), nargs='?', default='summary'
    )
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--theme', action='append', default=[])
    parser.add_argument('--kind', choices=sorted(KINDS))
    parser.add_argument('--accepted-only', action='store_true')
    args = parser.parse_args()
    args.data_root = cli_data_root(parser, args.data_root)
    try:
        if args.command == 'build':
            print(json.dumps(rebuild(args.data_root), indent=2))
        else:
            store = load_store(args.data_root / 'graph')
            if args.command == 'summary':
                print(json.dumps(summary(store), indent=2))
            else:
                for record in entries(store, themes=args.theme, kind=args.kind):
                    if not args.accepted_only or record['status'] == 'Accepted':
                        print(json.dumps(record, ensure_ascii=False))
    except (ValueError, KeyError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
