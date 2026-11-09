"""Compatibility module for :mod:`knot.curating.evidence_accounts`."""

import sys

from knot.curating import evidence_accounts as _implementation

sys.modules[__name__] = _implementation
