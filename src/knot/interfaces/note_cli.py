"""Capture and read native notes through the owner-local note API."""

import argparse
import importlib
import json
import shlex
import sys
from pathlib import Path

from knot.interfaces.console import _ask as _ask
from knot.interfaces.console import _wizard
from knot.shared.datasets import cli_data_root
from knot.shared.vocabulary import KINDS
from knot.writing.notes import create_note, list_notes, note_history, read_note, save_note


def _view_hint(result, data_root):
    if result.get('note') and result.get('revision'):
        command = shlex.join(['knot', 'view', '--data-root', str(data_root), '--open'])
        print(
            f'The graph is a snapshot. Refresh it to see this note:\n  {command}', file=sys.stderr
        )


DELEGATES = {
    'theme': ('knot.interfaces.visual_theme_cli', False, 'Choose or create a visual theme'),
    'view': (
        'knot.interfaces.view_cli',
        True,
        'Open Graph and Library; use knot view example for a demo',
    ),
    'browse': ('knot.presentation.library', True, 'Export the offline Graph and Library'),
    'themes': (
        'knot.interfaces.theme_cli',
        True,
        'List, add or import knowledge theme definitions',
    ),
    'mcp': (
        'knot.interfaces.mcp_server',
        False,
        'Serve MCP; use knot mcp --help for startup options',
    ),
    'dataset': ('knot.interfaces.dataset_cli', False, 'Initialise, select or clone a dataset'),
}


def _delegated_command(arguments):
    prefix, routed = [], arguments
    if arguments and arguments[0] == '--data-root' and len(arguments) > 2:
        prefix, routed = arguments[:2], arguments[2:]
    elif arguments and arguments[0].startswith('--data-root='):
        prefix, routed = arguments[:1], arguments[1:]
    if routed and routed[0] in DELEGATES:
        module, accepts_prefix, _ = DELEGATES[routed[0]]
        if not prefix or accepts_prefix:
            return module, [*prefix, *routed[1:]]
    return None


def _refresh(args):
    from knot.writing.sync import refresh

    refresh(args.data_root)


def _push(args):
    from knot.writing.sync import push

    push(args.data_root)


def _serve(args):
    from knot.interfaces.mcp_server import main

    main(['--data-root', str(args.data_root)])


def _agent_task(args):
    from knot.writing.authoring import agent_task

    print(agent_task(args.data_root, args.note, revision=args.revision), end='')


def _metadata(args, fields):
    return {key: getattr(args, key) for key in fields if hasattr(args, key)}


def _curate(args):
    from knot.interfaces.authoring_cli import run_workflow

    return run_workflow(
        args.data_root, _metadata(args, ('title', 'author', 'kind', 'agent')), curate=True
    )


def _resume(args):
    from knot.interfaces.authoring_cli import choose_draft, run_workflow

    path = args.draft if args.draft is not None else choose_draft(args.data_root)
    if path is not None:
        return run_workflow(args.data_root, {}, draft_path=path)
    return None


def _write(args):
    metadata = _metadata(args, ('format', 'title', 'author', 'kind', 'entities', 'agent', 'reason'))
    for field in ('navigation', 'derivation'):
        path = getattr(args, field)
        if path is not None:
            metadata[field] = json.loads(path.read_bytes())
    if args.file is None and not args.writing_only:
        from knot.interfaces.authoring_cli import run_workflow

        return run_workflow(args.data_root, metadata)
    if args.file is None:
        body = _wizard(metadata)
    elif args.file == '-':
        body = sys.stdin.buffer.read()
    else:
        body = Path(args.file).read_bytes()
    if args.action == 'save':
        return save_note(args.data_root, args.note, body, expected=args.expected, **metadata)
    metadata.setdefault(
        'format', 'org' if args.file and Path(args.file).suffix.lower() == '.org' else 'markdown'
    )
    return create_note(args.data_root, body, **metadata)


def _show(args):
    result = read_note(args.data_root, args.note, revision=args.revision)
    if args.body_only:
        sys.stdout.buffer.write(result['body'].encode('utf-8'))
        return None
    return result


def _history(args):
    return note_history(args.data_root, args.note)


def _list(args):
    result = list_notes(args.data_root)
    if args.theme:
        result = [
            n
            for n in result
            if args.theme in {t['id'] for t in n.get('navigation', {}).get('themes', [])}
        ]
    if args.linked_to:
        result = [
            n
            for n in result
            if args.linked_to in {link['note'] for link in n.get('navigation', {}).get('links', [])}
        ]
    return result


HANDLERS = {
    'refresh': _refresh,
    'push': _push,
    'mcp': _serve,
    'agent-task': _agent_task,
    'curate': _curate,
    'resume': _resume,
    'add': _write,
    'save': _write,
    'show': _show,
    'history': _history,
    'list': _list,
}


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    commands = parser.add_subparsers(dest='action', required=True)
    for name, (_, _, help_text) in DELEGATES.items():
        commands.add_parser(name, help=help_text)
    commands.add_parser('push', help='Commit knowledge data and push to the configured upstream')
    commands.add_parser('refresh', help='Pull upstream changes with a fast-forward only')
    listing = commands.add_parser('list', help='List verified current note metadata')
    listing.add_argument('--theme')
    listing.add_argument('--linked-to')
    resume = commands.add_parser('resume', help='Review and resume a saved authoring draft')
    resume.add_argument('draft', type=Path, nargs='?', help='Omit to choose from saved drafts')
    curate = commands.add_parser('curate', help='Write a separate curated note from saved sources')
    for field in ('title', 'author'):
        curate.add_argument('--' + field, default=argparse.SUPPRESS)
    curate.add_argument('--kind', choices=sorted(KINDS), default=argparse.SUPPRESS)
    curate.add_argument(
        '--agent', default='knot-cli', help='Actual saving agent (default: knot-cli)'
    )
    task = commands.add_parser('agent-task', help='Print a task for a separately invoked CLI agent')
    task.add_argument('note')
    task.add_argument('--revision')
    for action in ('show', 'history'):
        command = commands.add_parser(action)
        command.add_argument('note', help='Logical note IRI')
        if action == 'show':
            command.add_argument('--revision', help='Read an exact committed revision IRI')
            command.add_argument('--body-only', action='store_true', help='Write exact body bytes')
    for action in ('add', 'save'):
        command = commands.add_parser(action)
        if action == 'add':
            command.add_argument(
                '--writing-only',
                action='store_true',
                help='Capture prose without organisation steps',
            )
        if action == 'save':
            command.add_argument('note', help='Logical note IRI')
            command.add_argument('--expected', required=True, help='Last observed revision IRI')
        command.add_argument(
            'file',
            nargs='?' if action == 'add' else None,
            help='UTF-8 body file, or - for stdin; omit for guided capture',
        )
        command.add_argument('--format', choices=('markdown', 'org'), default=argparse.SUPPRESS)
        for field in ('title', 'author', 'kind'):
            group = command.add_mutually_exclusive_group()
            group.add_argument('--' + field, default=argparse.SUPPRESS)
            if action == 'save':
                group.add_argument(
                    '--clear-' + field,
                    dest=field,
                    action='store_const',
                    const=None,
                    default=argparse.SUPPRESS,
                )
        group = command.add_mutually_exclusive_group()
        group.add_argument('--entity', dest='entities', action='append', default=argparse.SUPPRESS)
        if action == 'save':
            group.add_argument(
                '--clear-entities',
                dest='entities',
                action='store_const',
                const=[],
                default=argparse.SUPPRESS,
            )
        command.add_argument(
            '--navigation', type=Path, help='JSON note themes, links and declarations'
        )
        command.add_argument('--agent', help='Actual saving agent, if known')
        command.add_argument('--reason', help='Reason for this capture or revision')
        command.add_argument(
            '--derivation', type=Path, help='JSON provenance for a separate curated note'
        )
    for action, handler in HANDLERS.items():
        commands.choices[action].set_defaults(handler=handler)
    return parser


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    delegated = _delegated_command(arguments)
    if delegated:
        module, forwarded = delegated
        # Keep optional MCP and viewer dependencies lazy for ordinary note commands.
        return importlib.import_module(module).main(forwarded)
    parser = _parser()
    args = parser.parse_args(arguments)
    if not hasattr(args, 'handler'):
        parser.error(f"Use knot {args.action} --help for this command's options")
    args.data_root = cli_data_root(parser, args.data_root)
    try:
        result = args.handler(args)
        if result is None:
            return
        if args.action != 'show':
            # Capture receipts and history retain provenance without repeating long bodies.
            result = (
                [{key: value for key, value in note.items() if key != 'body'} for note in result]
                if isinstance(result, list)
                else {key: value for key, value in result.items() if key != 'body'}
            )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.action in ('add', 'save', 'resume', 'curate'):
            _view_hint(result, args.data_root)
    except (ValueError, OSError, TypeError, KeyError) as error:
        parser.exit(1, f'Notes failed: {error}\n')
    except KeyboardInterrupt:
        parser.exit(
            130,
            '\nInterrupted. A full-workflow draft is retained at the displayed path; resume it before retrying.\n',
        )


if __name__ == '__main__':
    main()
