"""Compatibility module for :mod:`knot.writing.navigation`."""

import sys

from knot.writing import navigation as _implementation

sys.modules[__name__] = _implementation
