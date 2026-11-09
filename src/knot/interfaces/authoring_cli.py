"""Terminal orchestration of the shared draft and publication APIs."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from knot.curating.rules import DOMAIN_PREDICATES, relationship_warnings
from knot.graph.rdf import VOCAB, write_bytes
from knot.graph.resources import ONTOLOGY_PATH
from knot.interfaces.console import _ask, _choose, _evidence, _required, _wizard
from knot.retrieval_engine.context import lookup
from knot.shared.storage import atomic_json, managed_path
from knot.shared.vocabulary import KINDS, TYPES
from knot.writing.authoring import (
    _draft_path,
    agent_task,
    draft_warnings,
    new_draft,
    publish_draft,
    validate_draft,
)
from knot.writing.navigation import theme_choices
from knot.writing.notes import list_notes, read_note


def _entities(root, draft):
    navigation = draft['metadata']['navigation']
    while True:
        query = _ask('Find an entity by name (Enter when done):').strip()
        if not query:
            return
        found = lookup(root, query, limit=20)
        choices = [
            (f'{" / ".join(c["labels"])} — {c["id"]}', c['id'])
            for c in found['candidates']
            if not c['id'].startswith('urn:knot:note:')
        ]
        choices.append(('Create a distinct new entity', 'new'))
        selected = _choose('Select an existing identity, or create a distinct referent', choices)
        if selected == 'new':
            name = _required('Specific entity name:')
            matches = [
                c
                for c in lookup(root, name)['candidates']
                if not c['id'].startswith('urn:knot:note:')
            ]
            if matches:
                print(json.dumps(matches, ensure_ascii=False, indent=2), file=sys.stderr)
                if _ask(
                    'These names already exist. Create a distinct referent anyway? [y/N]'
                ).lower() not in ('y', 'yes'):
                    continue
            kind = _choose('Entity type', [(t, t) for t in sorted(TYPES)])
            if kind is None:
                continue
            evidence = _evidence(draft['body'])
            if evidence:
                navigation['declarations'].append(
                    {
                        'id': 'urn:knot:entity:' + str(uuid4()),
                        'label': name,
                        'type': kind,
                        'quote': evidence[0],
                        'offset': evidence[1],
                    }
                )
        elif selected and selected not in draft['metadata']['entities']:
            draft['metadata']['entities'].append(selected)


def _relationships(root, draft):
    from pyoxigraph import NamedNode, RdfFormat, Store

    ontology = Store()
    ontology.load(path=ONTOLOGY_PATH, format=RdfFormat.TURTLE)
    predicates = []
    for name in sorted(DOMAIN_PREDICATES - {'eventCount', 'occurredOn'}):
        comments = list(
            ontology.quads_for_pattern(
                NamedNode(VOCAB + name),
                NamedNode('http://www.w3.org/2000/01/rdf-schema#comment'),
                None,
                None,
            )
        )
        predicates.append((name + ': ' + comments[0].object.value, VOCAB + name))
    metadata = draft['metadata']
    endpoints = [{'id': draft['note'], 'label': metadata.get('title') or 'This note'}]
    endpoints += [
        {'id': e['id'], 'label': e['label']} for e in metadata['navigation']['declarations']
    ]
    for eid in metadata['entities'] + [link['note'] for link in metadata['navigation']['links']]:
        candidates = lookup(root, eid)['candidates']
        endpoints.append({'id': eid, 'label': candidates[0]['labels'][0] if candidates else eid})
    choices = [(e['label'] + ' — ' + e['id'], e) for e in endpoints]
    while _ask('Add a substantive relationship? [y/N]').lower() in ('y', 'yes'):
        subject = _choose('Subject: the relationship starts here', choices)
        predicate = _choose('Relationship meaning', predicates)
        obj = _choose('Object: the relationship points here', choices)
        if not all((subject, predicate, obj)):
            continue
        print(
            f'{subject["label"]} → {predicate.removeprefix(VOCAB)} → {obj["label"]}',
            file=sys.stderr,
        )
        evidence = _evidence(draft['body'])
        if not evidence:
            continue
        origin = _choose(
            'Is this stated in the note or inferred?',
            [('Explicit', 'Explicit'), ('Inferred', 'Inferred')],
        )
        if origin is None:
            continue
        rationale = _required('Why is this relationship supported? Retain qualifications:')
        kind = _choose(
            'Relationship kind (skip to inherit note kind)', [(k, k) for k in sorted(KINDS)]
        )
        print(
            'Relationship themes inherit the note selections unless overridden here.',
            file=sys.stderr,
        )
        selected_themes = _choose(
            'Relationship themes (skip to inherit)',
            [(t['label'], t['id']) for t in theme_choices(root)],
            multiple=True,
        )
        relation = {
            'classification': {
                'kind': kind or metadata.get('kind') or 'Unspecified',
                'themes': selected_themes or [t['id'] for t in metadata['navigation']['themes']],
            },
            'id': 'urn:knot:assertion:' + str(uuid4()),
            'subject': subject,
            'predicate': predicate,
            'object': obj,
            'origin': origin,
            'rationale': rationale,
            'quote': evidence[0],
            'offset': evidence[1],
            'generated_at': datetime.now(timezone.utc).isoformat(),
        }
        print(
            json.dumps(
                relationship_warnings(
                    predicate,
                    [],
                    quotes=[evidence[0]],
                    subject=NamedNode(subject['id']),
                    object=NamedNode(obj['id']),
                ),
                indent=2,
            ),
            file=sys.stderr,
        )
        if _ask('Keep this relationship as an Unreviewed candidate? [y/N]').lower() in ('y', 'yes'):
            draft['relationships'].append(relation)


def choose_draft(root):
    root = Path(root).resolve()
    paths = sorted(
        (
            managed_path(root, path.relative_to(root))
            for path in managed_path(root, 'drafts').glob('*.json')
        ),
        key=lambda p: (p.stat().st_mtime_ns, p.name),
        reverse=True,
    )
    choices = []
    for path in paths:
        try:
            draft = json.loads(path.read_bytes())
            if draft['root'] != str(root):
                continue
            title = draft['metadata'].get('title') or 'Untitled'
            status = 'note saved' if draft.get('saved') else 'draft'
            choices.append((f'{title} [{status}] ({path.stem})', path))
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            print(f'Cannot list draft {path.name}: {exc}', file=sys.stderr)
    if not choices:
        print('No drafts found. Start a note with knot add.', file=sys.stderr)
        return None
    print('Saved drafts (newest first):', file=sys.stderr)
    return _choose('Choose a draft to continue', choices)


def _review_draft(root, draft):
    metadata = draft['metadata']
    nav = metadata['navigation']
    lines = ['\nReview your note', f'Title: {metadata.get("title") or "Untitled"}']
    lines += [f'{key.title()}: {metadata.get(key) or "Unspecified"}' for key in ('author', 'kind')]
    lines += [
        '',
        draft['body'],
        'Themes: ' + (', '.join(t['label'] for t in nav['themes']) or 'None'),
    ]
    if metadata.get('derivation') is not None:
        from knot.writing.curation_workflow import review_sources

        lines.extend(review_sources(root, metadata['derivation']))
    lines.append('Related notes:')
    for link in nav['links']:
        target = read_note(root, link['note'])
        lines.append(f'  {target.get("title") or link["note"]} — {link["reason"]}')
    if not nav['links']:
        lines.append('  None')
    lines.append('Existing entities: ' + (', '.join(metadata['entities']) or 'None'))
    for entity in nav['declarations']:
        lines += [
            f'New entity: {entity["label"]} ({entity["type"]})',
            f'  Evidence: {entity["quote"]}',
        ]
    lines.append(f'Relationship candidates: {len(draft["relationships"])} (Unreviewed)')
    for relation in draft['relationships']:
        lines += [
            f'  {relation["subject"]["label"]} → {relation["predicate"].removeprefix(VOCAB)}'
            f' → {relation["object"]["label"]} ({relation["origin"]})',
            f'  Reason: {relation["rationale"]}',
            f'  Evidence: {relation["quote"]}',
        ]
        if relation.get('classification'):
            lines.append(f'  Classification: {json.dumps(relation["classification"])}')
    print('\n'.join(lines), file=sys.stderr)


def _select_themes(navigation, themes):
    selected = _choose('Choose themes (comma-separated numbers)', themes, multiple=True)
    if selected:
        navigation['themes'] = selected


def _link_note(root, navigation):
    query = _ask('Find a related note by title or text:').casefold()
    choices = [
        (n['title'] or n['note'], n['note'])
        for n in list_notes(root)
        if query and query in ((n['title'] or '') + '\n' + n['body']).casefold()
    ]
    target = _choose('Link to note', choices)
    if target:
        reason = _required('Why is this note connected?')
        navigation['links'] = [link for link in navigation['links'] if link['note'] != target] + [
            {'note': target, 'reason': reason}
        ]


def _edit_text(draft):
    metadata = draft['metadata']
    if metadata['navigation']['declarations'] or draft['relationships']:
        print(
            'Remove declarations and relationships before editing their supporting text.',
            file=sys.stderr,
        )
        return
    curated = metadata.get('derivation') is not None
    metadata['title'] = _required('Title:') if curated else _ask('Title:') or None
    draft['body'] = _wizard(metadata, confirm=False, curated=curated)


def _remove_selection(draft):
    metadata = draft['metadata']
    choices = [
        (f'{field}: {item}', (items, item))
        for field, items in [
            *metadata['navigation'].items(),
            ('entities', metadata['entities']),
            ('relationships', draft['relationships']),
        ]
        for item in items
    ]
    selected = _choose('Remove selection', choices)
    if selected:
        selected[0].remove(selected[1])


def run_workflow(root, metadata, *, draft_path=None, curate=False):
    from knot.interfaces.curation_cli import edit_curation

    if draft_path is not None:
        path = _draft_path(root, draft_path)
        draft = json.loads(path.read_bytes())
        if draft['root'] != str(Path(root).resolve()):
            raise ValueError('Draft belongs to another dataset; supply its --data-root')
        metadata = draft['metadata']
        existing = next((n for n in list_notes(root) if n['note'] == draft['note']), None)
        if existing:
            draft['saved'] = draft['saved'] or existing['revision']
    else:
        if curate:
            metadata['derivation'] = {'method': None, 'qualification': '', 'sources': []}
        body = '' if curate else _wizard(metadata, confirm=False)
        metadata.setdefault('entities', [])
        metadata.setdefault('navigation', {'themes': [], 'links': [], 'declarations': []})
        draft = new_draft(body, metadata, root=root)
        path = managed_path(root, 'drafts/' + draft['note'].rsplit(':', 1)[-1] + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, draft)
    print(f'Draft saved to {path}. Resume with: knot resume', file=sys.stderr)
    if metadata.get('derivation') is not None and not draft['saved']:
        from knot.interfaces.curation_cli import prepare_curation

        prepare_curation(root, draft, path)
    themes = [(t['label'], {'id': t['id'], 'label': t['label']}) for t in theme_choices(root)]
    mode = (
        None
        if draft_path
        else _choose(
            'Section 3: Organise your note',
            [
                ('Organise manually now', 'guided'),
                ('Save for a CLI agent to organise later', 'handoff'),
                ('Choose steps from a menu', 'menu'),
            ],
        )
    )
    pending = (
        []
        if draft_path or mode in (None, 'menu')
        else ['handoff']
        if mode == 'handoff'
        else ['themes', 'links', 'entities', 'relationships']
    )
    editors = {
        'themes': lambda: _select_themes(metadata['navigation'], themes),
        'links': lambda: _link_note(root, metadata['navigation']),
        'entities': lambda: _entities(root, draft),
        'relationships': lambda: _relationships(root, draft),
        'sources': lambda: edit_curation(root, draft, path),
        'edit': lambda: _edit_text(draft),
        'remove': lambda: _remove_selection(draft),
    }
    try:
        while True:
            action = (
                pending.pop(0)
                if pending
                else _choose(
                    'Next step',
                    [
                        (label, value)
                        for label, value in [
                            ('Choose themes', 'themes'),
                            ('Link related notes', 'links'),
                            ('Find or create entities', 'entities'),
                            ('Create relationships', 'relationships'),
                            ('Save for a CLI agent later', 'handoff'),
                            ('Review draft', 'review'),
                            ('Edit title or writing', 'edit'),
                            ('Remove a selection', 'remove'),
                            ('Save note and publish candidates', 'save'),
                            ('Leave draft for later', 'leave'),
                        ]
                        + (
                            [('Edit sources and qualification', 'sources')]
                            if metadata.get('derivation') is not None
                            else []
                        )
                    ],
                )
            )
            if draft['saved'] and action not in ('save', 'handoff', 'review', 'leave', None):
                print(
                    'This draft already saved a note. Review and resume publication; use notes save for revisions.',
                    file=sys.stderr,
                )
                continue
            if action in (None, 'leave'):
                return {'draft': str(path), 'published': False}
            if action in editors:
                editors[action]()
            elif action in ('review', 'save', 'handoff'):
                try:
                    validate_draft(root, draft)
                except (ValueError, TypeError, KeyError) as error:
                    print(
                        f'Draft needs correction: {error}. Use Remove or Edit, then review again.',
                        file=sys.stderr,
                    )
                    continue
                _review_draft(root, draft)
                warnings = draft_warnings(root, draft)
                if warnings:
                    print('Review these semantic warnings before saving:', file=sys.stderr)
                    print(json.dumps(warnings, ensure_ascii=False, indent=2), file=sys.stderr)
                if action in ('save', 'handoff') and _ask(
                    'Save this note and publish the listed Unreviewed relationships? [y/N]'
                    if draft['relationships']
                    else 'Save this note? [y/N]'
                ).lower() in ('y', 'yes'):
                    atomic_json(path, draft)
                    result = publish_draft(root, path)
                    draft['saved'] = result['revision']
                    if action == 'handoff':
                        task_path = path.with_suffix('.agent.txt')
                        write_bytes(
                            task_path,
                            agent_task(root, result['note'], revision=result['revision']).encode(
                                'utf-8'
                            ),
                        )
                        result['agent_task'] = str(task_path)
                        print(
                            f'Give this task file to your CLI agent in this repository: {task_path}',
                            file=sys.stderr,
                        )
                    return result
            atomic_json(path, draft)
    finally:
        # Publication may already have saved the note before a later step failed.
        committed = json.loads(path.read_bytes()).get('saved')
        if committed:
            draft['saved'] = committed
        atomic_json(path, draft)
