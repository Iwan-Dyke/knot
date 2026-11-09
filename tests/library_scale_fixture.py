"""Deterministic browser-load fixtures, not authoritative knowledge datasets."""

import random
import sys
from html import escape
from pathlib import Path

from knot.presentation.library import render_snapshot


def model_for(profile):
    count, entity_count, claim_count, link_count = {
        'M': (1000, 3000, 10000, 3000),
        'L': (5000, 10000, 50000, 15000),
    }[profile]
    randomizer = random.Random(20261108)
    themes = [{'id': t, 'label': t.title()} for t in ('learning', 'projects', 'concepts')]
    bodies, notes, entities, claims, sources, relations = {}, {}, {}, {}, {}, []
    for i in range(count):
        id, revision, sha = f'urn:example:note:{i}', f'urn:example:revision:{i}', f'body-{i}'
        prose = f'Synthetic note {i}. Search token needle{i}. '
        body = '# Example\n\n' + prose * (
            102400 // len(prose) if i % 1000 == 1 else 2048 // len(prose)
        )
        bodies[sha] = {
            'text': body,
            'html': {'markdown': '<h1>Example</h1><p>' + escape(body) + '</p>'},
        }
        note = {
            'id': id,
            'revision': revision,
            'title': f'Example note {i}',
            'author': 'Synthetic author',
            'agent': 'Fixture',
            'reason': 'Browser performance fixture',
            'kind': 'Thought',
            'format': 'markdown',
            'body': sha,
            'created_at': '2026-01-01T00:00:00Z',
            'modified_at': '2026-01-01T00:00:00Z',
            'method': None,
            'sources': [],
            'history': [],
            'navigation': {'themes': themes[: i % 3], 'links': [], 'declarations': []},
            'entities': [],
        }
        note['history'] = [
            {
                key: note[key]
                for key in (
                    'revision',
                    'title',
                    'author',
                    'agent',
                    'reason',
                    'format',
                    'modified_at',
                )
            }
        ]
        note['history'][0]['body_sha256'] = sha
        notes[id] = note
        sources[revision] = {
            'revision': revision,
            'title': note['title'],
            'author': note['author'],
            'note': id,
            'format': 'markdown',
            'body': sha,
            'sha256': sha,
            'text_sha256': sha,
            'snapshot': 'synthetic-text',
            'text_path': 'synthetic-text',
        }
    for i in range(entity_count):
        id = f'urn:example:entity:{i}'
        entities[id] = {
            'id': id,
            'title': 'Shared label' if i % 30 == 0 else f'Example project {i}',
            'types': ['Project'],
            'aliases': [f'Historic {i}'],
            'typing': [],
            'themes': [],
        }
    for i in range(claim_count):
        id = f'urn:example:claim:{i}'
        subject = f'urn:example:entity:{0 if i < 400 else randomizer.randrange(entity_count)}'
        target = f'urn:example:entity:{randomizer.randrange(entity_count)}'
        status, origin = (
            ('Accepted' if i % 3 else 'Unreviewed'),
            ('Explicit' if i % 4 else 'Inferred'),
        )
        pin = {
            'revision': f'urn:example:revision:{i % count}',
            'quote': f'Synthetic note {i % count}.',
            'sha256': f'body-{i % count}',
            'text_sha256': f'body-{i % count}',
            'locator': {'characterOffset': 11, 'startLine': 3},
        }
        claims[id] = {
            'id': id,
            'subject': {'id': subject, 'label': entities[subject]['title']},
            'object': {'id': target, 'label': entities[target]['title'], 'literal': False},
            'predicate': 'urn:knot:vocab:relatedTo',
            'status': status,
            'origin': origin,
            'kind': 'Thought',
            'lifecycle': 'Active',
            'themes': [],
            'rationale': 'Synthetic connection.',
            'evidence': [pin],
            'evidence_accounts': [],
        }
        relations.append(
            {
                'id': id,
                'from': subject,
                'to': target,
                'kind': 'claim',
                'label': 'relatedTo',
                'status': status,
                'origin': origin,
                'knowledge_kind': 'Thought',
                'themes': [],
            }
        )
    for i in range(link_count):
        source, target = (
            f'urn:example:note:{i % (count - 20)}',
            f'urn:example:note:{(i * 7 + 1) % (count - 20)}',
        )
        relations.append(
            {
                'id': f'link-{i}',
                'from': source,
                'to': target,
                'kind': 'link',
                'label': 'links to',
                'reason': 'Synthetic navigation.',
            }
        )
    return {
        'manifest': {
            'schema_version': 1,
            'generated_at': '2026-01-01T00:00:00Z',
            'fingerprint': 'synthetic-profile-' + profile,
            'history': 'SYNTHETIC BENCHMARK FIXTURE',
            'boundary': 'synthetic browser benchmark; not a verified knowledge dataset',
            'counts': {'notes': count, 'entities': entity_count, 'claims': claim_count},
        },
        'notes': notes,
        'entities': entities,
        'claims': claims,
        'bodies': bodies,
        'sources': sources,
        'relations': relations,
        'themes': themes,
        'reviews': [],
        'historical_claims': {},
    }


if __name__ == '__main__':
    Path(sys.argv[2]).write_text(render_snapshot(model_for(sys.argv[1]), visual_theme='paper'))
