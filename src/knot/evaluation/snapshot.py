"""Detect changed inputs before publishing an evaluation receipt."""

from __future__ import annotations

import json
import platform
from importlib.metadata import version
from pathlib import Path
from typing import Any

from knot.graph.resources import ONTOLOGY_PATH
from knot.retrieval_engine.evidence import _Evidence
from knot.shared.storage import digest, managed_path


def canonical_hash(value: Any) -> str:
    return digest(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    )


def input_files(root: Path) -> dict[str, str]:
    # Include membership and review inputs, not just witnesses: new accepted
    # assertions must also change a previously negative receipt.
    patterns = (
        'graph/*.trig',
        'reviews/events/*.trig',
        'reviews/explanations/*/*.json',
        'notes/registry.json',
        'notes/revisions/*.json',
        'curation/*.json',
        'organisation/*.json',
        'migration/conversion.json',
    )
    paths = sorted(
        {path.relative_to(root).as_posix() for pattern in patterns for path in root.glob(pattern)}
    )
    return {path: digest(managed_path(root, path).read_bytes()) for path in paths}


def implementation() -> dict[str, Any]:
    package = Path(__file__).resolve().parents[1]
    # Pin shared loaders/verification too; a rule version alone cannot identify
    # uncommitted code or changes in a supporting verifier.
    code = {
        p.relative_to(package).as_posix(): digest(p.read_bytes())
        for p in sorted(package.rglob('*.py'))
    }
    return {
        'code_sha256': canonical_hash(code),
        'ontology_sha256': digest(ONTOLOGY_PATH.read_bytes()),
        'python': platform.python_version(),
        'pyoxigraph': version('pyoxigraph'),
    }


class Snapshot:
    def __init__(self, root: Path):
        self.root = root
        self.files = input_files(root)
        self.implementation = implementation()
        self.sources: dict[str, str] = {}

    def verify(self) -> None:
        if self.files != input_files(self.root) or self.implementation != implementation():
            raise ValueError('Inputs changed during evaluation; retry with stable inputs')
        self.verify_sources()

    def verify_sources(self) -> None:
        for path, expected in self.sources.items():
            if digest(managed_path(self.root, path).read_bytes()) != expected:
                raise ValueError('Inputs changed during evaluation; retry with stable inputs')

    def manifest(self) -> dict[str, Any]:
        return {'input_files': self.files, 'verified_files': dict(sorted(self.sources.items()))}


class Evidence(_Evidence):
    def __init__(self, snapshot: Snapshot, store: Any, max_revisions: int):
        super().__init__(snapshot.root, store, max_revisions=max_revisions)
        self.snapshot = snapshot

    def read(self, path: str, expected: str) -> bytes:
        data = super().read(path, expected)
        previous = self.snapshot.sources.setdefault(path, expected)
        if previous != expected:
            raise ValueError('Inputs changed during evaluation; inconsistent source pins')
        return data
