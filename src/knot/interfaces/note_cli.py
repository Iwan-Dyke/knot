"""Capture and read native notes through the owner-local note API."""

import argparse
import json
import shlex
import sys
from pathlib import Path

from knot.shared.datasets import cli_data_root
from knot.shared.vocabulary import KINDS
from knot.writing.notes import create_note, list_notes, note_history, read_note, save_note


def _view_hint(result, data_root):
    if result.get('note') and result.get('revision'):
        command = shlex.join(['knot', 'view', '--data-root', str(data_root), '--open'])
        print(
            f'The graph is a snapshot. Refresh it to see this note:\n  {command}', file=sys.stderr
        )


def _ask(prompt, *, end='\n'):
    print(prompt, file=sys.stderr, flush=True, end=end)
    line = sys.stdin.readline()
    if not line:
        raise ValueError('Capture cancelled: input ended before saving')
    return line.rstrip('\r\n')


def _wizard(metadata, *, confirm=True, curated=False):
    if metadata.get('format', 'markdown') != 'markdown' or (
        'derivation' in metadata and not curated
    ):
        raise ValueError('Guided capture uses Markdown; use a file for Org or curated notes')
    print('Section 1: Note details (optional)', file=sys.stderr)
    for field, prompt in (
        ('title', 'Title (optional):'),
        ('author', 'Your name / author (optional; left unknown if skipped):'),
        ('kind', f'Kind (optional: {", ".join(sorted(KINDS))}):'),
    ):
        if field not in metadata:
            while True:
                value = _ask(prompt).strip()
                if field != 'kind' or not value or value in KINDS:
                    metadata[field] = value or None
                    break
                print(
                    'Choose a listed kind or press Enter to leave it unclassified.', file=sys.stderr
                )
    print(
        '\nSection 2: Your note\n'
        'Write one continuous note in your own words. Things to consider:\n'
        '  • What prompted this? Include context or a source where useful.\n'
        '  • What do you think, and why? What matters to you here?\n'
        '  • What does it connect to? What is uncertain or has changed your mind?\n'
        '  • Is there anything you want to try or revisit?\n'
        'These are prompts to think about, not separate answers to fill in.\n'
        'Enter keeps writing; blank lines keep paragraph breaks.\n'
        'Type /done on its own line to finish, or /cancel to cancel.\n'
        'No headings or guidance will be added to your note.',
        file=sys.stderr,
    )
    lines = []
    while True:
        line = _ask('note> ', end='')
        if line == '/cancel':
            raise ValueError('Capture cancelled: nothing saved')
        if line == '/done':
            break
        lines.append(line)
    if not any(line.strip() for line in lines):
        raise ValueError('Capture cancelled: no note text entered')
    body = '\n'.join(lines) + '\n'
    print('\nPreview', file=sys.stderr)
    print(json.dumps(metadata, ensure_ascii=False, indent=2), file=sys.stderr)
    print(body, file=sys.stderr)
    if confirm and _ask('Save this note? [y/N]').strip().lower() not in ('y', 'yes'):
        raise ValueError('Capture cancelled: nothing saved')
    return body


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == 'theme':
        from knot.interfaces.visual_theme_cli import main as visual_theme_main

        return visual_theme_main(arguments[1:])
    prefix, routed = [], arguments
    if arguments and arguments[0] == '--data-root' and len(arguments) > 2:
        prefix, routed = arguments[:2], arguments[2:]
    elif arguments and arguments[0].startswith('--data-root='):
        prefix, routed = arguments[:1], arguments[1:]
    if routed and routed[0] == 'view':
        from knot.interfaces.view_cli import main as view_main

        return view_main([*prefix, *routed[1:]])
    if routed and routed[0] == 'browse':
        from knot.presentation.library import main as library_main

        return library_main([*prefix, *routed[1:]])
    if routed and routed[0] == 'themes':
        from knot.interfaces.theme_cli import main as theme_main

        return theme_main([*prefix, *routed[1:]])
    if arguments and arguments[0] == 'dataset':
        from knot.interfaces.dataset_cli import main as dataset_main

        return dataset_main(arguments[1:])
    if arguments and arguments[0] == 'mcp':
        from knot.interfaces.mcp_server import main as mcp_main

        return mcp_main(arguments[1:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('theme', help='Choose or create a visual theme; use knot theme --help')
    commands.add_parser('view', help='Open Graph and Library; use knot view example for a demo')
    commands.add_parser(
        'browse', help='Export the offline Graph and Library; use knot browse --help'
    )
    commands.add_parser('themes', help='List, add or import knowledge theme definitions')
    commands.add_parser('mcp', help='Serve MCP; use knot mcp --help for startup options')
    commands.add_parser('dataset', help='Initialise, select or clone a dataset')
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
    args = parser.parse_args(argv)
    args.data_root = cli_data_root(parser, args.data_root)
    try:
        if args.action == 'refresh':
            from knot.writing.sync import refresh

            refresh(args.data_root)
            return
        if args.action == 'push':
            from knot.writing.sync import push

            push(args.data_root)
            return
        if args.action == 'mcp':
            from knot.interfaces.mcp_server import main as mcp_main

            return mcp_main(['--data-root', str(args.data_root)])
        if args.action == 'agent-task':
            from knot.writing.authoring import agent_task

            print(agent_task(args.data_root, args.note, revision=args.revision), end='')
            return
        if args.action == 'curate':
            from knot.writing.authoring import run_workflow

            metadata = {
                key: getattr(args, key)
                for key in ('title', 'author', 'kind', 'agent')
                if hasattr(args, key)
            }
            result = run_workflow(args.data_root, metadata, curate=True)
        elif args.action == 'resume':
            from knot.writing.authoring import choose_draft, run_workflow

            path = args.draft if args.draft is not None else choose_draft(args.data_root)
            if path is None:
                return
            result = run_workflow(args.data_root, {}, draft_path=path)
        elif args.action in ('add', 'save'):
            metadata = {
                key: getattr(args, key)
                for key in ('format', 'title', 'author', 'kind', 'entities', 'agent', 'reason')
                if hasattr(args, key)
            }
            if args.navigation is not None:
                metadata['navigation'] = json.loads(args.navigation.read_bytes())
            if args.derivation is not None:
                metadata['derivation'] = json.loads(args.derivation.read_bytes())
            if args.file is None and not args.writing_only:
                from knot.writing.authoring import run_workflow

                result = run_workflow(args.data_root, metadata)
                print(json.dumps(result, indent=2, ensure_ascii=False))
                _view_hint(result, args.data_root)
                return
            if args.file is None:
                body = _wizard(metadata)
            else:
                body = sys.stdin.buffer.read() if args.file == '-' else Path(args.file).read_bytes()
            if args.action == 'add':
                metadata.setdefault(
                    'format',
                    'org' if args.file and Path(args.file).suffix.lower() == '.org' else 'markdown',
                )
                result = create_note(args.data_root, body, **metadata)
            else:
                result = save_note(
                    args.data_root, args.note, body, expected=args.expected, **metadata
                )
        elif args.action == 'show':
            result = read_note(args.data_root, args.note, revision=args.revision)
            if args.body_only:
                sys.stdout.buffer.write(result['body'].encode('utf-8'))
                return
        elif args.action == 'history':
            result = note_history(args.data_root, args.note)
        else:
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
                    if args.linked_to
                    in {link['note'] for link in n.get('navigation', {}).get('links', [])}
                ]
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
