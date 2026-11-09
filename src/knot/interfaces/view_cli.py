"""Open the Graph and Library together, or explicitly select the legacy viewer."""

import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--legacy', action='store_true')
    args, remaining = parser.parse_known_args(argv)
    if args.legacy:
        from knot.presentation.visualise import main as view_main
    else:
        from knot.presentation.library import main as view_main
    return view_main(remaining, open_browser=True)


if __name__ == '__main__':
    main()
