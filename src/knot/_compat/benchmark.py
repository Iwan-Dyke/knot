"""Compatibility module for :mod:`knot.diagnostics.benchmark`."""

import sys

from knot.diagnostics import benchmark as _implementation

if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
