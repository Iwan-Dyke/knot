"""Compatibility module for :mod:`knot.graph.rdf`."""

import sys

from knot.graph import rdf as _implementation

sys.modules[__name__] = _implementation
