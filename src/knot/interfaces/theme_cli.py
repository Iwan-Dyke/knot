"""List, add or import knowledge themes in the selected dataset."""

import argparse
import json
from pathlib import Path

from knot.shared.datasets import cli_data_root
from knot.writing.themes import add_themes, read_catalogue


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    adding = commands.add_parser('add')
    adding.add_argument('id', help='Unique lowercase slug')
    adding.add_argument('--label', required=True)
    adding.add_argument('--description', default='')
    adding.add_argument('--keyword', action='append', default=[])
    adding.add_argument('--include-frameworks', action='store_true')
    commands.add_parser('import').add_argument('file', type=Path, help='JSON array of definitions')
    args = parser.parse_args(argv)
    root = cli_data_root(parser, args.data_root)
    try:
        if args.command == 'list':
            result = read_catalogue(root)['themes']
        else:
            definitions = (
                json.loads(args.file.read_bytes())
                if args.command == 'import'
                else [
                    {
                        'id': args.id,
                        'label': args.label,
                        'description': args.description,
                        'keywords': args.keyword,
                        'include_frameworks': args.include_frameworks,
                    }
                ]
            )
            result = add_themes(root, definitions)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
