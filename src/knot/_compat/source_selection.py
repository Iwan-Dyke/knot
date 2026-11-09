"""Compatibility module for :mod:`knot.retrieval_engine.source_selection`."""

import sys

from knot.retrieval_engine import source_selection as _implementation

# Keep module-level instrumentation working at the historical import path.
sys.modules[__name__] = _implementation
