"""Compatibility module for :mod:`knot.retrieval_engine.discovery`."""

import sys

from knot.retrieval_engine import discovery as _implementation

# Keep module-level instrumentation working at the historical import path.
sys.modules[__name__] = _implementation
