"""Compatibility module for :mod:`knot.writing.authoring`."""

import sys

from knot.writing import authoring as _implementation

sys.modules[__name__] = _implementation
