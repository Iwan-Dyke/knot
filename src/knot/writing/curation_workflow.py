"""Owner-local source selection for the shared, resumable note authoring workflow."""

import re
import sys

from pyoxigraph import NamedNode

from knot.curating.provenance import _Sources, source_pin
from knot.graph.rdf import LABEL, META, VOCAB, values
from knot.shared.storage import atomic_json
from knot.writing.notes import REVISION, list_notes

METHODS = [('Faithful restatement', 'faithful_restatement'), ('Synthesis', 'synthesis')]


def source_choices(root):
    choices = [
        {
            'title': note['title'] or 'Untitled',
            'revision': note['revision'],
            'search': ' '.join([note['title'] or '', note['note'], note['revision']]),
        }
        for note in list_notes(root)
    ]
    store = _Sources(root, None).store
    for quad in store.quads_for_pattern(None, NamedNode(VOCAB + 'snapshotPath'), None, META):
        revision = quad.subject.value
        if revision.startswith(REVISION):
            continue
        labels = {
            label.value
            for ref in store.quads_for_pattern(
                None, NamedNode(VOCAB + 'revision'), quad.subject, META
            )
            for label in values(store, ref.subject.value, LABEL)
        }
        title = ' / '.join(sorted(labels)) or quad.object.value
        choices.append(
            {
                'title': title,
                'revision': revision,
                'search': ' '.join([title, revision, quad.object.value]),
            }
        )
    return sorted(choices, key=lambda source: (source['title'].casefold(), source['revision']))


def _passage(text):
    from knot.interfaces.note_cli import _ask
    from knot.writing.authoring import _choose, _evidence

    method = _choose(
        'Select supporting evidence', [('Line range', 'lines'), ('Exact text', 'text')]
    )
    if method == 'text':
        return _evidence(text, name='source')
    if method != 'lines':
        return None
    lines = text.splitlines(keepends=True)
    while True:
        answer = _ask('Line number or range, e.g. 2-4 (Enter to cancel):').strip()
        if not answer:
            return None
        match = re.fullmatch(r'(\d+)(?:-(\d+))?', answer)
        if match:
            start, end = int(match[1]), int(match[2] or match[1])
            if 1 <= start <= end <= len(lines):
                return ''.join(lines[start - 1 : end]), len(''.join(lines[: start - 1]))
        print('Choose an existing line or an inclusive range in order.', file=sys.stderr)


def select_sources(root, draft, path):
    from knot.interfaces.note_cli import _ask
    from knot.writing.authoring import _choose

    choices = source_choices(root)
    if not choices:
        raise ValueError(
            'No saved sources. Capture original text with knot add FILE, then knot curate.'
        )
    pins = draft['metadata']['derivation']['sources']
    print(
        'Choose preserved sources. Use * to list all, /remove to remove a passage, '
        'or /cancel to leave this draft. Enter finishes source selection.',
        file=sys.stderr,
    )
    while True:
        print(f'{len(pins)} supporting passage(s) selected.', file=sys.stderr)
        query = _ask('Find a source by title or ID:').strip()
        if query == '/cancel':
            raise ValueError('Curation cancelled; the draft is retained for knot resume')
        if query == '/remove':
            selected = _choose(
                'Remove a passage',
                [
                    (f'{pin["revision"]}, line {pin["start_line"]}: {pin["quote"]!r}', pin)
                    for pin in pins
                ],
            )
            if selected:
                pins.remove(selected)
                atomic_json(path, draft)
            continue
        if not query:
            if pins:
                return
            print('Select at least one supporting passage before continuing.', file=sys.stderr)
            continue
        matches = [
            source
            for source in choices
            if query == '*' or query.casefold() in source['search'].casefold()
        ]
        selected = _choose(
            'Choose a source',
            [(f'{source["title"]} — {source["revision"]}', source) for source in matches],
        )
        if selected is None:
            continue
        try:
            text, source = _Sources(root, None).read(selected['revision'])
        except (ValueError, OSError) as error:
            print(
                f'Cannot use this source: {error}. Select another source or preserve readable '
                'text first.',
                file=sys.stderr,
            )
            continue
        author = source.get('native_note', {}).get('author') or 'Unknown'
        print(
            f'\nSource: {selected["title"]}\nAuthor: {author}\n'
            f'Evidence text: {source["verification"]}\n',
            file=sys.stderr,
        )
        for number, line in enumerate(text.splitlines(), 1):
            print(f'{number}: {line}', file=sys.stderr)
        while True:
            evidence = _passage(text)
            if evidence:
                try:
                    pin = source_pin(root, selected['revision'], *evidence)
                except (ValueError, OSError) as error:
                    print(
                        f'Cannot use this source: {error}. Select another source.', file=sys.stderr
                    )
                    break
                if pin not in pins:
                    pins.append(pin)
                    atomic_json(path, draft)
            if _ask('Add another passage from this source? [y/N]').lower() not in ('y', 'yes'):
                break


def prepare_curation(root, draft, path):
    from knot.interfaces.note_cli import _wizard
    from knot.writing.authoring import _choose, _required

    metadata = draft['metadata']
    derivation = metadata['derivation']
    if not derivation['method'] or not derivation['sources']:
        select_sources(root, draft, path)
        while not derivation['method']:
            derivation['method'] = _choose('How are you using these sources?', METHODS)
        atomic_json(path, draft)
    for fields, key, prompt in (
        (derivation, 'qualification', 'What do the sources establish, and what remains uncertain?'),
        (metadata, 'title', 'Title for the separate curated note:'),
        (metadata, 'author', 'Actual author of this curated writing:'),
        (metadata, 'agent', 'Actual saving agent:'),
    ):
        if not fields.get(key) or not fields[key].strip():
            fields[key] = _required(prompt)
            atomic_json(path, draft)
    if not draft['body']:
        print(
            'Write your own restatement or synthesis. Keep qualifications and source attribution; '
            'the original writing will be preserved.',
            file=sys.stderr,
        )
        draft['body'] = _wizard(metadata, confirm=False, curated=True)
        atomic_json(path, draft)


def edit_curation(root, draft, path):
    from knot.interfaces.note_cli import _ask
    from knot.writing.authoring import _choose

    select_sources(root, draft, path)
    derivation = draft['metadata']['derivation']
    derivation['method'] = (
        _choose('Curation method (Enter keeps current)', METHODS) or derivation['method']
    )
    derivation['qualification'] = (
        _ask('Qualification (Enter keeps current):').strip() or derivation['qualification']
    )
    atomic_json(path, draft)


def review_sources(root, derivation):
    lines = [f'Derivation: {derivation["method"]}', f'Qualification: {derivation["qualification"]}']
    reader = _Sources(root, None)
    for pin in derivation['sources']:
        _, source = reader.read(pin['revision'])
        note = source.get('native_note', {})
        lines += [
            f'Source: {note.get("title") or source["snapshot"]} '
            f'(author: {note.get("author") or "Unknown"})',
            f'  Revision: {pin["revision"]}',
            f'  Line {pin["start_line"]}, character {pin["character_offset"]}: {pin["quote"]!r}',
        ]
    return lines
