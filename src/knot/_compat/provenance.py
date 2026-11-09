"""Compatibility module for :mod:`knot.curating.provenance`."""

import sys

from knot.curating import provenance as _implementation

sys.modules[__name__] = _implementation
