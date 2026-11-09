"""Local, source-backed knowledge with feature-owned implementations."""

from pathlib import Path

# Resolve historical knot.<module> imports and -m commands without root-level shims.
# Implementations import feature packages directly; compatibility is only for callers.
__path__.append(str(Path(__file__).with_name('_compat')))
