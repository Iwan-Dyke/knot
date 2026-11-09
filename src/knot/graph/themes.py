"""Apply explicit topic-membership decisions without accepting source claims."""

import json
import re

from knot.graph.rdf import BASE, RDF_TYPE, VOCAB, identifier, one, values
from knot.shared.storage import digest

REVIEW_FIELDS = {
    'rationale': 'rationale',
    'reviewer': 'reviewer',
    'reviewer_kind': 'reviewerKind',
    'reviewed_at': 'reviewedAt',
    'recorded_status': 'recordedStatus',
    'record_fingerprint': 'recordFingerprint',
    'theme_fingerprint': 'themeFingerprint',
}


def definition_fingerprint(theme):
    # Keyword changes suggest new candidates; they do not change an explicit
    # judgement about a theme's meaning.
    definition = {key: theme.get(key, '') for key in ('id', 'label', 'description')}
    return digest(json.dumps(definition, sort_keys=True, ensure_ascii=False).encode())


def validate_reviews(reviews, themes):
    if reviews is None:
        return
    if reviews.get('schema_version') != 1:
        raise ValueError('Unsupported theme review schema')
    for key in ('reviewer', 'reviewer_kind', 'reviewed_at'):
        if not isinstance(reviews.get(key), str) or not reviews[key].strip():
            raise ValueError(f'Missing theme review {key}')
    if reviews['reviewer_kind'] not in ('Assistant', 'Human'):
        raise ValueError('Invalid theme reviewer kind')
    for record in reviews['records'].values():
        if not re.fullmatch(r'[a-f0-9]{64}', record['fingerprint']):
            raise ValueError('Invalid theme review record fingerprint')
        for theme, decision in record['decisions'].items():
            if theme not in themes:
                raise ValueError(f'Unknown reviewed theme: {theme}')
            if not re.fullmatch(r'[a-f0-9]{64}', reviews['theme_fingerprints'].get(theme, '')):
                raise ValueError(f'Missing theme definition fingerprint: {theme}')
            if decision['status'] not in ('Accepted', 'Rejected', 'Unreviewed'):
                raise ValueError(f'Invalid theme review status: {decision["status"]}')
            if not decision.get('rationale', '').strip():
                raise ValueError('Theme review requires a rationale')
            for key in ('reviewer', 'reviewer_kind', 'reviewed_at'):
                if key in decision and (
                    not isinstance(decision[key], str) or not decision[key].strip()
                ):
                    raise ValueError(f'Invalid theme decision {key}')
            if decision.get('reviewer_kind', reviews['reviewer_kind']) not in (
                'Assistant',
                'Human',
            ):
                raise ValueError('Invalid theme decision reviewer kind')


def memberships(aid, fingerprint, themes, suggestions, reviews=None):
    reviewed = (reviews or {}).get('records', {}).get(aid, {})
    decisions = reviewed.get('decisions', {})
    result = []
    for tid in sorted(set(suggestions) | decisions.keys()):
        decision = decisions.get(tid)
        item = {
            'id': tid,
            'status': 'Unreviewed',
            'review_state': 'Missing',
            'rationale': 'Catalogue suggestion; topic relevance has not been reviewed.',
        }
        if decision:
            current = reviewed['fingerprint'] == fingerprint and (
                reviews['theme_fingerprints'][tid] == definition_fingerprint(themes[tid])
            )
            item.update(
                status=decision['status'] if current else 'Unreviewed',
                review_state='Current' if current else 'Stale',
                rationale=decision['rationale']
                if current
                else 'Previous theme review is stale; review changed inputs. '
                + decision['rationale'],
                reviewer=decision.get('reviewer', reviews['reviewer']),
                reviewer_kind=decision.get('reviewer_kind', reviews['reviewer_kind']),
                reviewed_at=decision.get('reviewed_at', reviews['reviewed_at']),
                recorded_status=decision['status'],
                record_fingerprint=reviewed['fingerprint'],
                theme_fingerprint=reviews['theme_fingerprints'][tid],
            )
        result.append(item)
    return result


def write_memberships(add, aid, items):
    """Store decisions as resources so rejected suggestions remain inspectable."""
    for item in items:
        mid = identifier('theme-membership', aid + '\0' + item['id'])
        add(aid, VOCAB + 'themeMembership', mid)
        add(mid, RDF_TYPE, VOCAB + 'ThemeMembership')
        add(mid, VOCAB + 'targetAssertion', aid)
        add(mid, VOCAB + 'theme', BASE + 'theme:' + item['id'])
        add(mid, VOCAB + 'origin', VOCAB + 'Inferred')
        for key, prop in [('status', 'reviewStatus'), ('review_state', 'reviewState')]:
            add(mid, VOCAB + prop, VOCAB + item[key])
        for key, predicate in REVIEW_FIELDS.items():
            if key in item:
                add(mid, VOCAB + predicate, item[key], literal=True)


def read_memberships(store, aid, graph, labels):
    result = []
    for term in values(store, aid, VOCAB + 'themeMembership', graph):
        mid = term.value
        tid = one(store, mid, VOCAB + 'theme', graph).value
        item = {'id': tid.removeprefix(BASE + 'theme:'), 'label': labels[tid]}
        for key, prop in [('status', 'reviewStatus'), ('review_state', 'reviewState')]:
            item[key] = one(store, mid, VOCAB + prop, graph).value.removeprefix(VOCAB)
        for key, predicate in REVIEW_FIELDS.items():
            found = values(store, mid, VOCAB + predicate, graph)
            if found:
                item[key] = found[0].value
        result.append(item)
    return sorted(result, key=lambda t: t['id'])
