"""Compatibility module for :mod:`knot.writing.notes`."""

import sys

from knot.writing import notes as _implementation

sys.modules[__name__] = _implementation
