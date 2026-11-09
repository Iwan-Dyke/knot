"""Owner-local source selection for the shared, resumable note authoring workflow."""

from pyoxigraph import NamedNode

from knot.curating.provenance import _Sources
from knot.graph.rdf import LABEL, META, VOCAB, values
from knot.writing.notes import REVISION, list_notes


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


def select_sources(root, draft, path):
    """Compatibility entry point for the terminal curation workflow."""
    from knot.interfaces.curation_cli import select_sources as run

    return run(root, draft, path)


def prepare_curation(root, draft, path):
    """Compatibility entry point for the terminal curation workflow."""
    from knot.interfaces.curation_cli import prepare_curation as run

    return run(root, draft, path)


def edit_curation(root, draft, path):
    """Compatibility entry point for the terminal curation workflow."""
    from knot.interfaces.curation_cli import edit_curation as run

    return run(root, draft, path)
