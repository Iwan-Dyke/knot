"""Compatibility module for :mod:`knot.graph.themes`."""

import sys

from knot.graph import themes as _implementation

sys.modules[__name__] = _implementation
