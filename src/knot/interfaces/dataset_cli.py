"""Create, select or clone a dataset; no automatic commits or pushes."""

import argparse
import json
from pathlib import Path

from knot.shared.datasets import config_path, read_config, resolve_data_root
from knot.writing.datasets import clone, initialise, select


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('init', 'use'):
        commands.add_parser(name).add_argument('path', type=Path)
    cloning = commands.add_parser('clone')
    cloning.add_argument('url')
    cloning.add_argument('path', type=Path, nargs='?')
    commands.add_parser('show')
    args = parser.parse_args(argv)
    try:
        if args.command == 'show':
            root = resolve_data_root()
        else:
            read_config()  # Do not modify a dataset if its selection cannot be saved.
            if args.command == 'init':
                root = initialise(args.path)
            elif args.command == 'clone':
                root = clone(args.url, args.path)
            else:
                root = args.path
            root = select(root)
        print(json.dumps({'data_root': str(root), 'config': str(config_path())}))
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
