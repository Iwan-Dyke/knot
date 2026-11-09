"""Compatibility module for :mod:`knot.retrieval_engine.service`."""

import sys

from knot.retrieval_engine import service as _implementation

if __name__ == '__main__':
    _implementation.main()
else:
    sys.modules[__name__] = _implementation
