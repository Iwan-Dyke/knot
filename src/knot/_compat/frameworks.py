"""Compatibility module for :mod:`knot.ingestion.frameworks`."""

import sys

from knot.ingestion import frameworks as _implementation

sys.modules[__name__] = _implementation
