"""Answer supported questions through checked routing and artifact selection."""

import argparse
import json
from pathlib import Path

from knot.evaluation.answering import answer, revalidate
from knot.shared.datasets import cli_data_root


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--question')
    mode.add_argument('--revalidate', type=Path, help='Saved checked-answer JSON receipt')
    parser.add_argument('--explanation-revision')
    args = parser.parse_args(argv)
    if args.revalidate and args.explanation_revision is not None:
        parser.error('A saved receipt already specifies its selection')
    root = cli_data_root(parser, args.data_root)
    try:
        result = (
            revalidate(root, json.loads(args.revalidate.read_bytes()))
            if args.revalidate
            else answer(root, args.question, explanation_revision=args.explanation_revision)
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as error:
        parser.exit(1, f'Checked answer failed: {error}\n')


if __name__ == '__main__':
    main()
