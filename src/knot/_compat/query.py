"""Compatibility module for :mod:`knot.graph.query`."""

import sys

from knot.graph import query as _implementation

if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
