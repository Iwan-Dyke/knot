"""Compatibility module for :mod:`knot.graph.knowledge`."""

import sys

from knot.graph import knowledge as _implementation

if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
