"""Synthetic offline page for the optional Playwright interaction checks."""

import sys
from pathlib import Path

from pyvis.network import Network

from knot.visualise import add_claim, add_themes, write_view


def write_note_fixture(path):
    from knot.notes import create_note
    from knot.visualise import main

    root = path.parent / 'note-data'
    entity = 'urn:knot:entity:00000000-0000-4000-8000-000000000001'
    target = create_note(
        root,
        'Citizen developer foundations remain an open question.',
        title='Citizen developer foundations',
        author='Owner',
        kind='Question',
        navigation={
            'themes': [],
            'links': [],
            'declarations': [
                {
                    'id': entity,
                    'label': 'Citizen developer foundations',
                    'type': 'Concept',
                    'quote': 'Citizen developer foundations',
                    'offset': 0,
                }
            ],
        },
    )
    create_note(
        root,
        'Small modules help me review AI coding.\n</script><script>window.injected=true</script>',
        title='AI coding reflection',
        author='Owner',
        kind='Thought',
        navigation={
            'themes': [],
            'declarations': [],
            'links': [
                {'note': target['note'], 'reason': 'Suggests practical foundations, not proof.'}
            ],
        },
    )
    create_note(root, 'An idea without links.', title='Unlinked thought', author='Owner')
    sys.argv = [
        'visualise',
        '--graph',
        str(root / 'graph'),
        '--output',
        str(path),
        '--visual-theme',
        'matrix',
    ]
    main()


def write_fixture(path, *, visual_theme='matrix'):
    network = Network(directed=True, cdn_resources='in_line')
    entities = {
        'a': ('Alex', ['Person']),
        'b': ('Shared name', ['Project']),
        'c': ('Shared name', ['Project', 'Concept']),
        'd': ('Untyped', ['Entity']),
    }
    records = []
    for aid, source, target, themes, status, origin, kind in [
        ('ab', 'a', 'b', ['learning'], 'Accepted', 'Explicit', 'Observation'),
        ('bc', 'b', 'c', ['delivery'], 'Unreviewed', 'Inferred', 'Question'),
        ('ac', 'a', 'c', [], 'Accepted', 'Explicit', 'Observation'),
        ('cd', 'c', 'd', ['learning', 'delivery'], 'Accepted', 'Explicit', 'Question'),
    ]:
        theme_details = [
            {'id': t, 'label': t.title(), 'status': 'Accepted' if aid == 'ab' else 'Unreviewed'}
            for t in themes
        ]
        add_claim(
            network,
            {
                'id': aid,
                'source': source,
                'target': target,
                'subject': entities[source][0],
                'object': entities[target][0],
                'source_types': entities[source][1],
                'target_types': entities[target][1],
                'relation': 'relatedTo',
                'status': status,
                'origin': origin,
                'kind': kind,
                'theme_ids': themes,
                'theme_details': theme_details,
                'themes': '; '.join(t['label'] + ' [' + t['status'] + ']' for t in theme_details),
                'quote': '<img src=x onerror="window.injected=true">\n'
                '</script><script>window.injected=true</script>',
                'snapshot': 'sources/synthetic.txt',
                'rationale': 'A qualified synthetic account, not a personal claim.',
            },
        )
        records.append(
            {
                'id': aid,
                'subject': {'id': source},
                'object': {'id': target},
                'themes': theme_details,
            }
        )
    add_claim(
        network,
        {
            'id': 'count',
            'source': 'b',
            'subject': 'Shared name',
            'target': 'literal:count',
            'object': '18',
            'literal': True,
            'literal_value': '18',
            'object_datatype': 'http://www.w3.org/2001/XMLSchema#integer',
            'relation': 'eventCount',
            'status': 'Unreviewed',
            'origin': 'Explicit',
            'kind': 'Observation',
            'theme_ids': ['delivery'],
            'quote': 'Eighteen events were reported.',
            'snapshot': 'sources/count.txt',
        },
    )
    network.get_node('b')['aliases'] = ['Historical project heading']
    add_themes(network, records)
    note = {
        'id': 'note:plan',
        'revision': 'revision:plan',
        'title': 'Recovery remains a plan',
        'author': 'Codex',
        'kind': 'Observation',
        'body': 'Recovery is planned. Completion is not established.\n\n'
        '<img src=x onerror="window.injected=true">\n'
        '</script><script>window.injected=true</script>',
        'method': 'faithful_restatement',
        'qualification': 'No completed recovery established.',
        'sources': [
            {
                'title': 'Original capture',
                'author': 'Owner',
                'revision': 'revision:original',
                'quote': 'Please record that recovery remains planned.',
                'text_path': 'sources/original.txt',
                'start_line': 1,
            }
        ],
    }
    other = {
        **note,
        'id': 'note:review',
        'title': 'Review the plan',
        'body': 'A review is proposed.',
    }
    write_view(
        network,
        path,
        visual_theme=visual_theme,
        notes={
            'notes': {note['id']: note, other['id']: other},
            'entities': {'a': [note['id']], 'b': [note['id'], other['id']]},
        },
    )


if __name__ == '__main__':
    write_fixture(Path(sys.argv[1]))
