"""Compatibility module for :mod:`knot.presentation.visualise`."""

import sys

from knot.presentation import visualise as _implementation

if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
