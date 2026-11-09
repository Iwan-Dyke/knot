"""Select a visual theme or create an editable palette in the user theme folder."""

import argparse
import json

from knot.presentation.styles import (
    create_theme,
    load_theme,
    select_theme,
    selected_theme,
    theme_directory,
    theme_path,
    theme_paths,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    commands.add_parser('show')
    commands.add_parser('use').add_argument('theme', help='Theme name or CSS/JSON path')
    creating = commands.add_parser('create')
    creating.add_argument('name', help='New lowercase slug')
    creating.add_argument('--from', dest='source', default='matrix', help='Palette to copy')
    args = parser.parse_args(argv)
    try:
        if args.command == 'create':
            result = {
                'created': str(create_theme(args.name, args.source)),
                'directory': str(theme_directory()),
            }
        else:
            selected = select_theme(args.theme) if args.command == 'use' else selected_theme()
            result = {'selected': selected, 'directory': str(theme_directory())}
            if args.command == 'list':
                result['themes'] = sorted(theme_paths())
            else:
                result.update(name=load_theme(selected)['name'], path=str(theme_path(selected)))
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
