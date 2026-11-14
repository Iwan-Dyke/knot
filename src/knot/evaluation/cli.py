"""Evaluate recorded framework coverage in the selected owner-local dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from knot.evaluation import CoverageRequest, answer_question, evaluate, render, revalidate
from knot.shared.datasets import cli_data_root


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path, nargs='?', help='JSON CoverageRequest')
    parser.add_argument('--question', help='A supported quoted-name coverage question')
    parser.add_argument(
        '--revalidate',
        dest='saved_receipt',
        type=Path,
        help='Recompute a saved JSON receipt using current inputs and access',
    )
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--format', choices=('json', 'text'), default='json')
    args = parser.parse_args(argv)
    if sum(value is not None for value in (args.request, args.question, args.saved_receipt)) != 1:
        parser.error('Supply exactly one of a request file, --question or --revalidate')
    root = cli_data_root(parser, args.data_root)
    try:
        if args.saved_receipt is not None:
            result = revalidate(root, json.loads(args.saved_receipt.read_bytes()))
        elif args.question is not None:
            result = answer_question(root, args.question)
        else:
            request = CoverageRequest.from_dict(json.loads(args.request.read_bytes()))
            result = evaluate(root, request)
        print(
            render(result)
            if args.format == 'text'
            else json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        )
    except (ValueError, OSError, TypeError, KeyError, SyntaxError) as error:
        parser.exit(1, f'Evaluation failed: {error}\n')


if __name__ == '__main__':
    main()
