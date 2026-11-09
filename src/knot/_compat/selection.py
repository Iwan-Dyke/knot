"""Compatibility module for :mod:`knot.retrieval_engine.selection`."""

import sys

from knot.retrieval_engine import selection as _implementation

# Keep module-level instrumentation working at the historical import path.
sys.modules[__name__] = _implementation
