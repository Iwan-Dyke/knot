"""Read-only, bounded retrieval of existing source-backed assertion paths."""

import argparse
from dataclasses import asdict
from pathlib import Path

from knot.retrieval_engine.context import lookup
from knot.retrieval_engine.policy import Policy
from knot.retrieval_engine.response import serialise
from knot.retrieval_engine.service import retrieve
from knot.shared.datasets import cli_data_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('lookup', 'get', 'discover', 'gather'))
    parser.add_argument('seed', nargs='?')
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--question')
    parser.add_argument('--note-revision')
    parser.add_argument(
        '--compact', action='store_true', help='Share repeated provenance without removing evidence'
    )
    parser.add_argument(
        '--no-diagnostics',
        action='store_true',
        help='Omit ranking and work diagnostics for get/gather',
    )
    parser.add_argument('--mode', choices=('graph', 'text', 'hybrid'), default='graph')
    from knot.retrieval_engine.search import Limits

    for key, value in asdict(Limits()).items():
        parser.add_argument('--' + key.replace('_', '-'), type=int, default=value)
    parser.add_argument('--accepted-only', action='store_true')
    parser.add_argument('--include-frameworks', action='store_true')
    parser.add_argument('--subject', action='append', default=[])
    parser.add_argument(
        '--objective', choices=('relationships', 'context', 'qualifications'), action='append'
    )
    parser.add_argument('--exclude', action='append', default=[])
    for key, value in asdict(Policy()).items():
        if key.startswith('max_') or key in ('hub_degree', 'seed_hub_degree'):
            parser.add_argument('--' + key.replace('_', '-'), type=int, default=value)
    args = parser.parse_args()
    args.data_root = cli_data_root(parser, args.data_root)
    try:
        if args.command == 'lookup':
            if args.seed is None:
                raise ValueError('Lookup requires text or an IRI')
            result = lookup(args.data_root, args.seed, limit=args.limit)
        elif args.command in ('discover', 'gather'):
            from knot.retrieval_engine.discovery import discover, gather

            limits = Limits(**{key: getattr(args, key) for key in asdict(Limits())})
            if args.command == 'discover':
                result = discover(
                    args.data_root,
                    args.question,
                    max_chars=args.max_chars,
                    limit=args.limit,
                    limits=limits,
                    accepted_only=args.accepted_only,
                    include_frameworks=args.include_frameworks,
                )
            else:
                result = gather(
                    args.data_root,
                    args.subject + ([args.seed] if args.seed else []),
                    args.question,
                    Policy(
                        **{
                            key: getattr(args, key)
                            for key in asdict(Policy())
                            if hasattr(args, key)
                        }
                    ),
                    limits=limits,
                    objectives=args.objective,
                    exclude=args.exclude,
                )
        else:
            policy = Policy(
                **{key: getattr(args, key) for key in asdict(Policy()) if hasattr(args, key)}
            )
            limits = (
                Limits(**{key: getattr(args, key) for key in asdict(Limits())})
                if (
                    args.question is not None
                    or args.note_revision is not None
                    or args.mode == 'text'
                    or (args.seed is not None and args.seed.startswith('urn:knot:note:'))
                )
                else None
            )
            result = retrieve(
                args.data_root,
                args.seed,
                policy,
                question=args.question,
                mode=args.mode,
                limits=limits,
                note_revision=args.note_revision,
            )
        if args.no_diagnostics and args.command in ('get', 'gather'):
            from knot.retrieval_engine.wire import evidence_view

            result = evidence_view(result)
        if args.compact and args.command in ('get', 'gather'):
            from knot.retrieval_engine.wire import compact

            result = compact(result)
        print(serialise(result), end='')
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f'{error}\n')
