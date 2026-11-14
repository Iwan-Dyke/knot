"""Prepare, explicitly review and reuse decision-explanation revisions."""

import argparse
import json
from pathlib import Path

from knot.evaluation.explanations import answer, approve, history, prepare, revalidate, withdraw
from knot.shared.datasets import cli_data_root


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'approve', 'withdraw', 'history', 'answer', 'revalidate'):
        command = commands.add_parser(name)
        command.add_argument(
            'input', type=Path, help='JSON request, approval preview or saved receipt'
        )
        if name == 'prepare':
            wording = command.add_mutually_exclusive_group()
            wording.add_argument(
                '--wording',
                action='append',
                help='Complete alternative question; repeat for each wording',
            )
            wording.add_argument('--clear-wordings', action='store_true')
        if name in ('approve', 'withdraw'):
            command.add_argument('--reviewer', required=True)
            command.add_argument('--reason', required=True)
        if name == 'withdraw':
            command.add_argument('--expected', required=True, help='Current approval event hash')
    args = parser.parse_args(argv)
    root = cli_data_root(parser, args.data_root)
    try:
        value = json.loads(args.input.read_bytes())
        if args.command == 'prepare':
            result = prepare(root, value, wordings=[] if args.clear_wordings else args.wording)
        elif args.command == 'approve':
            result = approve(root, value, reviewer=args.reviewer, reason=args.reason)
        elif args.command == 'withdraw':
            result = withdraw(
                root, value, expected=args.expected, reviewer=args.reviewer, reason=args.reason
            )
        else:
            result = {
                'history': history,
                'answer': answer,
                'revalidate': revalidate,
            }[args.command](root, value)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as error:
        parser.exit(1, f'Explanation failed: {error}\n')


if __name__ == '__main__':
    main()
