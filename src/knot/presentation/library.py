"""Export a verified, read-only Knowledge Library and focused Graph snapshot."""

import argparse
import json
import re
import subprocess
import tempfile
from html import escape
from pathlib import Path

from knot.graph.rdf import write_bytes
from knot.presentation.browser import open_view
from knot.presentation.library_snapshot import build_snapshot, input_signature
from knot.presentation.styles import load_theme, selected_theme, stylesheet
from knot.presentation.viewer_assets import (
    VIS_SCRIPT,
    VIS_STYLE,
    load_viewer_assets,
    software_notices,
)
from knot.shared.datasets import cli_data_root
from knot.shared.storage import managed_path

ASSETS = Path(__file__).parent


def render_snapshot(model, *, visual_theme='matrix'):
    """Render a built read projection; owner export verifies before publication."""
    theme = load_theme(visual_theme)
    payload = json.dumps(
        {**model, 'palette': theme}, ensure_ascii=False, separators=(',', ':')
    ).replace('<', '\\u003c')
    assets = load_viewer_assets()
    html = (ASSETS / 'library.html').read_text()
    replacements = {
        '/* KNOT_STYLES */': stylesheet(theme) + (ASSETS / 'library.css').read_text(),
        '/* VIS_STYLES */': assets[VIS_STYLE],
        '/* VIS_SCRIPT */': assets[VIS_SCRIPT],
        '/* GRAPH_FILTERS */': (ASSETS / 'graph_filters.js').read_text(),
        '/* LIBRARY_SCRIPT */': '\n'.join(
            (ASSETS / name).read_text()
            for name in (
                'library_model.js',
                'library_idle_model.js',
                'library_idle_scene.js',
                'library_dom.js',
                'library_reader.js',
                'library_layout.js',
                'library_graph_style.js',
                'library_graph.js',
                'library_idle.js',
                'library_navigation.js',
                'library.js',
            )
        ),
        'KNOT_DATA': payload,
        'KNOT_NOTICES': escape(software_notices()),
    }
    # Substitute only the original template. Note text containing a placeholder
    # must never be interpreted as a second template expansion.
    return re.sub('|'.join(map(re.escape, replacements)), lambda m: replacements[m[0]], html)


def export_library(root, output, *, visual_theme='matrix', initial_search='', initial_record=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.suffix.lower() != '.html' or any(
        output.is_relative_to(root / name)
        for name in (
            'graph',
            'notes',
            'sources',
            'reviews',
            'organisation',
            'curation',
            'migration',
        )
    ):
        raise ValueError('Export to an HTML file outside authoritative dataset directories')
    before = input_signature(root)
    model = build_snapshot(root)
    model['manifest']['fingerprint'] = before
    if initial_search:
        model['initial_search'] = initial_search
    if initial_record is not None:
        if initial_record not in model['notes'] and initial_record not in model['entities']:
            raise ValueError('Initial record must be included in the snapshot')
        model['initial_record'] = initial_record
    html = render_snapshot(model, visual_theme=visual_theme)
    if input_signature(root) != before:
        raise ValueError('Dataset changed during export; regenerate the snapshot')
    write_bytes(output, html.encode('utf-8'))
    return model


def main(argv=None, *, open_browser=False):
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='Use knot view --legacy for the previous full-network viewer and its filters.',
    )
    parser.add_argument(
        'target', nargs='?', help="'example' for synthetic data, or initial search text"
    )
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--visual-theme')
    parser.add_argument(
        '--focus', help='Start with this search text; all knowledge stays available'
    )
    opening = parser.add_mutually_exclusive_group()
    opening.add_argument('--open', action='store_true', help='Open the generated file in a browser')
    opening.add_argument(
        '--no-open', dest='open', action='store_false', help='Generate without opening'
    )
    parser.set_defaults(open=open_browser)
    args = parser.parse_args(argv)
    if args.target == 'example' and args.data_root is not None:
        parser.error('example uses its own disposable dataset; omit --data-root')
    try:
        initial_record = None
        if args.target == 'example':
            from knot.writing.examples import build_examples

            # Keep the generated file after launch: browsers read it asynchronously.
            root = Path(tempfile.mkdtemp(prefix='knot-example-'))
            ids = build_examples(root)
            if not args.focus:
                initial_record = ids['project']
        else:
            root = cli_data_root(parser, args.data_root)
        output = (
            args.output if args.output is not None else managed_path(root, 'views/library.html')
        )
        snapshot = export_library(
            root,
            output,
            visual_theme=args.visual_theme or selected_theme(),
            initial_search=args.focus or (args.target if args.target != 'example' else '') or '',
            initial_record=initial_record,
        )
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(f'{output.resolve()} ({snapshot["manifest"]["counts"]["notes"]} notes; offline snapshot)')
    if args.open:
        try:
            open_view(output)
        except (OSError, subprocess.SubprocessError, RuntimeError) as error:
            parser.exit(1, f'Snapshot generated, but browser launch failed: {error}\n')


if __name__ == '__main__':
    main()
