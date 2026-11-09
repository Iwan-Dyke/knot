"""Compatibility module for :mod:`knot.ingestion.migrate`."""

import sys

from knot.ingestion import migrate as _implementation

if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
