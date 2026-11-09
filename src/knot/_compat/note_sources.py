"""Compatibility module for :mod:`knot.writing.sources`."""

import sys

from knot.writing import sources as _implementation

sys.modules[__name__] = _implementation
