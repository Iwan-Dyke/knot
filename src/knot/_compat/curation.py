"""Compatibility module for :mod:`knot.curating.candidates`."""

import sys

from knot.curating import candidates as _implementation

if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
