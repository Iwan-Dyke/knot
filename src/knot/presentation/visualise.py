"""Export claim relationships and their evidence to an offline PyVis view."""

import argparse
import json
import re
import subprocess
from collections import Counter, defaultdict
from html import escape
from pathlib import Path

from jinja2 import DictLoader, Environment
from pyoxigraph import NamedNode
from pyvis.network import Network

from knot.curating.entity_labels import apply_entity_labels
from knot.graph.knowledge import entries
from knot.graph.query import load_store
from knot.presentation.browser import open_view
from knot.presentation.note_records import curated_notes
from knot.presentation.styles import (
    apply_theme,
    edge_style,
    load_theme,
    node_style,
    selected_theme,
    stylesheet,
)
from knot.presentation.viewer_assets import load_viewer_assets, software_notices
from knot.retrieval_engine.context import _labels
from knot.shared.datasets import cli_data_root
from knot.shared.storage import managed_path
from knot.shared.vocabulary import KINDS, local_name


def add_note_navigation(
    network, payload, labels, *, focus='', themes=(), kind=None, show_themes=True
):
    """Draw saved note relationships without manufacturing reviewed claims."""
    notes = payload['notes']
    # Capture claim endpoints before navigation adds note and subject nodes.
    claim_nodes = {n['id'] for n in network.nodes if n.get('role') == 'entity'}
    selected = {
        id
        for id, note in notes.items()
        if (not kind or note['kind'] == kind)
        and (not themes or set(themes) & {t['id'] for t in note['navigation']['themes']})
        and focus.casefold()
        in ' '.join(
            [
                note['title'],
                note['body'],
                *[label for entity in note['entities'] for label in labels.get(entity, [entity])],
            ]
        ).casefold()
    }
    # Keep immediate linked context, including incoming links to a matching note.
    included = set(selected)
    for id, note in notes.items():
        for link in note['navigation']['links']:
            if id in selected or link['note'] in selected:
                included.update((id, link['note']))
    included &= notes.keys()
    for id in sorted(included):
        note = notes[id]
        network.add_node(id, label=note['title'])
        network.get_node(id).update(
            role='note',
            shape='ellipse' if id in claim_nodes else 'box',
            noteRole='entity' if id in claim_nodes else 'associated',
            entityTypes=['Note'],
            **node_style('note', note_role='entity' if id in claim_nodes else 'associated'),
            title=escape(note['title']),
            kind=note['kind'] or 'Unspecified',
            themeIds=[t['id'] for t in note['navigation']['themes']],
            themeDetails=note['navigation']['themes'],
        )
    for id in sorted(included):
        note = notes[id]
        connections = [
            (link['note'], 'links to', link['reason'])
            for link in note['navigation']['links']
            if link['note'] in included
        ]
        connections += [
            (entity, 'about', 'Saved association between this note and this subject.')
            for entity in note['entities']
            if entity != id
        ]
        for target, relation, reason in connections:
            if target not in network.node_ids:
                network.add_node(
                    target,
                    label=sorted(labels.get(target) or [target])[0],
                    role='entity',
                    shape='dot',
                    entityTypes=['Entity'],
                    **node_style('entity'),
                )
            network.add_edge(
                id,
                target,
                id='navigation:' + json.dumps([id, relation, target]),
                label=relation,
                navigation=True,
                arrows='to',
                dashes=[6, 4],
                **edge_style({'navigation': True}),
                title=escape(reason),
                kind=note['kind'] or 'Unspecified',
                themeIds=[t['id'] for t in note['navigation']['themes']],
                themeDetails=note['navigation']['themes'],
                detail={'rationale': reason, 'note': id, 'revision': note['revision']},
            )
    if show_themes:
        add_themes(
            network,
            [
                {
                    'id': id,
                    'subject': {'id': id},
                    'object': {'id': id},
                    'themes': notes[id]['navigation']['themes'],
                }
                for id in included
                if notes[id]['navigation']['themes']
            ],
        )
    return included


def add_claim(network, claim):
    for key, label in (('source', 'subject'), ('target', 'object')):
        if key == 'target' and claim.get('literal'):
            continue
        network.add_node(
            claim[key],
            label=claim[label],
            title=escape(claim[label] + ' · ' + ', '.join(claim.get(key + '_types', []))),
            shape='dot',
            role='entity',
            entityTypes=claim.get(key + '_types') or ['Entity'],
            aliases=claim.get(key + '_aliases', []),
            **node_style('entity'),
        )
    title = '<br>'.join(
        f'<b>{escape(key)}:</b> {escape(str(claim[key]))}'
        for key in (
            'subject',
            'relation',
            'object',
            'status',
            'origin',
            'kind',
            'themes',
            'kind_type_review',
            'quote',
            'snapshot',
            'rationale',
            'id',
        )
        if key in claim
    )
    metadata = dict(
        id=claim['id'],
        label=claim['relation'],
        title=title,
        **edge_style(claim),
        width=2.5 if claim['status'] == 'Accepted' else 1,
        dashes=claim['origin'] == 'Inferred',
        arrows='to',
        status=claim['status'],
        origin=claim['origin'],
        kind=claim.get('kind', 'Unspecified'),
        themeIds=claim.get('theme_ids', []),
        themeDetails=claim.get('theme_details', []),
        detail={
            **claim,
            'evidence': claim.get('evidence')
            or [{'quote': claim.get('quote', ''), 'snapshot': claim.get('snapshot', '')}],
        },
    )
    if claim.get('literal'):
        # A value belongs to its subject. It has assertion identity and evidence,
        # but must not acquire entity identity or participate in graph physics.
        network.get_node(claim['source']).setdefault('attributes', []).append(
            {**metadata, 'from': claim['source']}
        )
    else:
        network.add_edge(claim['source'], claim['target'], **metadata)


def add_themes(network, records):
    """Add navigation links separately from evidence-bearing claim edges."""
    links = defaultdict(dict)
    for record in records:
        for theme in record['themes']:
            tid = 'urn:knot:theme:' + theme['id']
            network.add_node(
                tid,
                label='THEME · ' + theme['label'],
                shape='diamond',
                role='theme',
                themeId=theme['id'],
                **node_style('theme'),
                title='Theme: overlapping navigation category; membership review is separate from claim review',
                size=18,
            )
            for position in ('subject', 'object'):
                entity = record[position]
                if entity.get('literal'):
                    continue
                pair = (tid, entity['id'])
                links[pair][record.get('id', str(pair))] = theme.get('status', 'Unreviewed')
    for pair, support in links.items():
        statuses = Counter(support.values())
        network.add_edge(
            *pair,
            id='theme:' + pair[0] + ':' + pair[1],
            organisation=True,
            memberships=support,
            label='',
            arrows='',
            dashes=[2, 8],
            **edge_style({'organisation': True, 'memberships': support}),
            width=0.5,
            physics=False,
            title='Theme membership: '
            + ', '.join(f'{k} ({v})' for k, v in sorted(statuses.items()))
            + '; not a factual relationship or acceptance of the supporting claims',
        )


def write_view(network, path, *, notes=None, visual_theme='matrix'):
    # Render only the audited template/includes, even for a caller-created Network.
    network.templateEnv = Environment(loader=DictLoader(load_viewer_assets(legacy=True)))
    network.path = 'template.html'
    network.cdn_resources = 'in_line'
    theme = load_theme(visual_theme)
    apply_theme(network, theme)
    network.heading = ''
    # The live controls own selection and visibility; PyVis highlighting mutates
    # labels and colours and would compete with the filtered view.
    network.select_menu = False
    network.filter_menu = False
    network.neighborhood_highlight = False
    network.set_options(
        json.dumps(
            {
                'layout': {'randomSeed': 7},
                'interaction': {'hover': True, 'tooltipDelay': 180, 'hideEdgesOnDrag': True},
                'physics': {
                    'solver': 'barnesHut',
                    'barnesHut': {
                        'gravitationalConstant': -13500,
                        'springLength': 255,
                        'springConstant': 0.025,
                        'avoidOverlap': 0.5,
                        'damping': 0.25,
                    },
                    'stabilization': {'iterations': 250},
                },
                'edges': {'smooth': {'enabled': True, 'type': 'continuous'}},
                'nodes': {'size': 8, 'borderWidth': 1},
            }
        )
    )
    html = network.generate_html(notebook=False)
    # PyVis inlines vis-network, but its stock template still imports Bootstrap.
    # The viewer needs neither Bootstrap nor any network resources.
    html = re.sub(r'<link\b[^>]*\bhref=["\']https?://[^>]*>', '', html, flags=re.I)
    html = re.sub(r'<script\b[^>]*\bsrc=["\']https?://[^>]*>\s*</script>', '', html, flags=re.I)
    # Override the stock theme after its styles, keeping all assets self-contained.
    css = stylesheet(theme) + Path(__file__).with_name('viewer.css').read_text()
    html = html.replace(
        '</head>',
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>KNOT · Knowledge network</title><style>' + css + '</style></head>',
    )
    claims = sum(not e.get('organisation') and not e.get('navigation') for e in network.edges)
    attributes = sum(len(n.get('attributes', [])) for n in network.nodes)
    themes = sum(n['shape'] == 'diamond' for n in network.nodes)
    header = f"""<header class="knot-header"><div><h1>❯ KNOT</h1>
<p>KNOWLEDGE NETWORK OF OBSERVATIONS AND TRACES</p></div>
<div class="telemetry"><div id="graph-counts" role="status" aria-live="polite">{len(network.nodes) - themes:03d} ENTITIES / {claims:03d} CLAIMS / {themes} THEMES / {attributes} ATTRIBUTES</div>
<span>LOCAL SNAPSHOT · FILTERS CHANGE THIS VIEW ONLY</span></div></header>"""
    controls = Path(__file__).with_name('viewer.html').read_text()
    sidebar, inspector = controls.split('<!-- inspector -->')
    html = html.replace('<body>', '<body>' + header + '<main id="viewer">' + sidebar)
    footer = """<footer class="knot-footer"><div class="knot-legend">
<span class="accepted">━ ACCEPTED</span><span class="unreviewed">━ UNREVIEWED</span>
<span class="inferred">┄ INFERRED</span><span class="navigation">▭ NOTE · NOTE CONNECTION</span><span>◇ THEME (SEPARATE REVIEW)</span></div><span>DRAG TO EXPLORE · SCROLL TO ZOOM · SELECT FOR EVIDENCE</span></footer>"""
    script = (
        Path(__file__).with_name('graph_filters.js').read_text()
        + '\n'
        + Path(__file__).with_name('viewer.js').read_text()
    )
    # Evidence is literal text. Escaping '<' also prevents a quotation from closing
    # this inert JSON element and injecting markup into the offline document.
    note_json = json.dumps(notes or {'notes': {}, 'entities': {}}).replace('<', '\\u003c')
    note_data = '<script id="curated-notes" type="application/json">' + note_json + '</script>'
    notices = (
        '<details class="software-notices"><summary>Software licences</summary><pre>'
        + escape(software_notices(legacy=True))
        + '</pre></details>'
    )
    html = html.replace(
        '</body>',
        inspector
        + '</main>'
        + footer
        + notices
        + note_data
        + '<script>'
        + script
        + '</script></body>',
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding='utf-8')


def main(argv=None, *, open_browser=False):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--graph', type=Path)
    group.add_argument('--data-root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--focus', default='', help='Include claims matching this text')
    parser.add_argument('--accepted-only', action='store_true')
    parser.add_argument('--theme', action='append', default=[], help='Filter by a theme slug')
    parser.add_argument(
        '--visual-theme', help='Override the saved visual theme with a name or CSS/JSON file'
    )
    parser.add_argument('--kind', choices=sorted(KINDS))
    parser.add_argument('--no-themes', action='store_true', help='Hide organisational theme links')
    parser.add_argument(
        '--frameworks',
        action='store_true',
        help='Limit the unified view to framework definitions',
    )
    opening = parser.add_mutually_exclusive_group()
    opening.add_argument(
        '--open', action='store_true', help='Open the generated view in your default browser'
    )
    opening.add_argument(
        '--no-open', dest='open', action='store_false', help='Generate without opening'
    )
    parser.set_defaults(open=open_browser)
    args = parser.parse_args(argv)
    try:
        if args.visual_theme is None:
            args.visual_theme = selected_theme()
        load_theme(args.visual_theme)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    if args.graph is None:
        args.graph = cli_data_root(parser, args.data_root) / 'graph'
    if args.output is None:
        try:
            args.output = managed_path(
                args.graph.parent,
                'views/' + ('frameworks.html' if args.frameworks else 'graph.html'),
            )
        except ValueError as error:
            parser.error(str(error))
    network = Network(
        height='85vh',
        width='100%',
        directed=True,
        cdn_resources='in_line',
        heading='',
    )
    try:
        store = load_store(args.graph, allow_empty=True)
        records = entries(store, themes=args.theme, kind=args.kind)
        labels = _labels(store, records)
        from knot.writing.sources import add_note_sources

        add_note_sources(args.graph.parent, store, store, labels)
        records, labels = apply_entity_labels(args.graph.parent, store, records, labels)
        from knot.curating.evidence_accounts import annotate_accounts

        records = annotate_accounts(args.graph.parent, store, records)
    except ValueError as error:
        parser.error(str(error))
    displayed = []
    for record in records:
        if args.frameworks and not record['framework']:
            continue
        claim = {
            'subject': record['subject']['label'],
            'object': record['object']['label'],
            'quote': '\n\n'.join(e['quote'] for e in record['evidence']),
            'snapshot': '\n'.join(e['snapshot'] for e in record['evidence']),
            'rationale': record['rationale'],
            'kind': record['kind'],
            'themes': '; '.join(
                t['label']
                + ' ['
                + t['status']
                + ('; ' + t['reviewer'] + ' / ' + t['reviewer_kind'] if t.get('reviewer') else '')
                + ']'
                for t in record['themes']
            ),
            'kind_type_review': record['classification']['status']
            + ': '
            + record['classification']['rationale'],
        }
        for end in ('subject', 'object'):
            if 'original_label' in record[end]:
                claim['original_' + end] = record[end]['original_label']
        claim.update(
            id=record['id'],
            source=record['subject']['id'],
            target='literal:' + record['id']
            if record['object']['literal']
            else record['object']['id'],
            relation=local_name(record['predicate']),
            status=record['status'],
            origin=record['origin'],
        )
        if record['object']['literal']:
            term = next(store.quads_for_pattern(None, None, None, NamedNode(record['id']))).object
            claim.update(
                literal=True,
                literal_value=term.value,
                object_datatype=term.datatype.value,
                object_language=term.language,
            )
        if args.accepted_only and claim['status'] != 'Accepted':
            continue
        names = set(labels.get(record['subject']['id'], []))
        if not record['object']['literal']:
            names.update(labels.get(record['object']['id'], []))
        if (
            args.focus.casefold()
            not in ' '.join([*(str(v) for v in claim.values()), *names]).casefold()
        ):
            continue
        claim.update(
            source_types=record['subject']['types'],
            target_types=['Literal'] if record['object']['literal'] else record['object']['types'],
            source_aliases=sorted(labels.get(record['subject']['id'], set()) - {claim['subject']}),
            target_aliases=sorted(labels.get(record['object']['id'], set()) - {claim['object']})
            if not record['object']['literal']
            else [],
            theme_ids=[t['id'] for t in record['themes']],
            theme_details=record['themes'],
            evidence=record['evidence'],
            evidence_accounts=record.get('evidence_accounts', []),
        )
        add_claim(network, claim)
        displayed.append(record)
    if not args.no_themes and not args.accepted_only:
        add_themes(network, displayed)
    network.barnes_hut()
    try:
        notes = curated_notes(
            args.graph.parent,
            store,
            [node['id'] for node in network.nodes if node.get('role') == 'entity'],
            include_all=not (args.accepted_only or args.frameworks),
        )
        if not (args.accepted_only or args.frameworks):
            included = add_note_navigation(
                network,
                notes,
                labels,
                focus=args.focus,
                themes=args.theme,
                kind=args.kind,
                show_themes=not args.no_themes,
            )
            notes['notes'] = {id: note for id, note in notes['notes'].items() if id in included}
            notes['entities'] = {
                id: [n for n in ids if n in included] for id, ids in notes['entities'].items()
            }
        if not network.nodes:
            parser.error('No notes or claims match the selected filters')
        write_view(network, args.output, notes=notes, visual_theme=args.visual_theme)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f'{args.output.resolve()} ({len(network.nodes)} nodes, {len(displayed)} claims)')
    if args.open:
        try:
            open_view(args.output)
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            parser.exit(1, f'Graph generated, but browser launch failed: {error}\n')


if __name__ == '__main__':
    main()
