"""Compatibility module for :mod:`knot.reviewing.writer`."""

import sys

from knot.reviewing import writer as _implementation

# Keep module-level instrumentation working at the historical import path.
if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
