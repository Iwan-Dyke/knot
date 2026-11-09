"""Compatibility module for :mod:`knot.diagnostics.quality`."""

import sys

from knot.diagnostics import quality as _implementation

if __name__ == '__main__':
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
